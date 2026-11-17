#include "kernel/types.h"
#include "kernel/stat.h"
#include "kernel/fcntl.h"
#include "user/user.h"

int
main(int argc, char *argv[])
{
  if (argc < 3) {
    fprintf(2, "usage: schedctl <pid> <weight> [reason...]\n");
    exit(1);
  }

  int pid = atoi(argv[1]);
  int weight = atoi(argv[2]);
  char *reason = (argc >= 4) ? argv[3] : "manual update";

  int res = setweight(pid, weight);
  int cur_ticks = uptime();

  // Open and append to sched.log
  int fd = open("sched.log", O_CREATE | O_RDWR);
  if (fd >= 0) {
    char tmp[64];
    while (read(fd, tmp, sizeof(tmp)) > 0)
      ;

    fprintf(fd, "[ticks=%d] PID %d: weight -> %d | %s | reason: ",
            cur_ticks, pid, weight, (res == 0 ? "ACCEPTED" : "REJECTED"));
    if (argc >= 4) {
      for (int i = 3; i < argc; i++) {
        fprintf(fd, "%s%s", argv[i], (i == argc - 1 ? "" : " "));
      }
    } else {
      fprintf(fd, "%s", reason);
    }
    fprintf(fd, "\n");
    close(fd);
  }

  if (res < 0) {
    fprintf(2, "schedctl: rejected (invalid pid or weight out of bounds)\n");
    exit(1);
  }

  printf("schedctl: PID %d weight set to %d (logged to /sched.log)\n", pid, weight);
  exit(0);
}
