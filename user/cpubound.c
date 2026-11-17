#include "kernel/types.h"
#include "kernel/stat.h"
#include "user/user.h"

int
main(int argc, char *argv[])
{
  int iters = 40000000;
  if (argc > 1) {
    iters = atoi(argv[1]);
  }

  int pid = getpid();
  int start_t = uptime();
  printf("cpubound [%d]: started (iters=%d, start_tick=%d)\n", pid, iters, start_t);

  volatile unsigned long long acc = 0;
  for (int i = 0; i < iters; i++) {
    acc += (i * 3ULL + 7ULL);
  }

  int end_t = uptime();
  printf("cpubound [%d]: finished (acc=%d, elapsed_ticks=%d)\n", pid, (int)(acc & 0xffff), end_t - start_t);
  exit(0);
}
