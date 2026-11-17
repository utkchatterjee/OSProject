#include "kernel/types.h"
#include "kernel/stat.h"
#include "user/user.h"

int
main(int argc, char *argv[])
{
  if (argc != 3) {
    fprintf(2, "usage: setweight <pid> <weight (1-5)>\n");
    exit(1);
  }

  int pid = atoi(argv[1]);
  int weight = atoi(argv[2]);

  if (weight < 1 || weight > 5) {
    fprintf(2, "setweight: weight must be between 1 and 5\n");
    exit(1);
  }

  if (setweight(pid, weight) < 0) {
    fprintf(2, "setweight: failed to set weight for pid %d\n", pid);
    exit(1);
  }

  printf("setweight: pid %d weight set to %d successfully\n", pid, weight);
  exit(0);
}
