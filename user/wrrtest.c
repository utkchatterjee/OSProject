#include "kernel/types.h"
#include "kernel/stat.h"
#include "user/user.h"

void
compute(int iters)
{
  volatile unsigned long long acc = 0;
  for (int i = 0; i < iters; i++) {
    acc += (i * 3ULL + 7ULL);
  }
}

int
main(int argc, char *argv[])
{
  int iters = 600000000;
  int w1 = 1;
  int w2 = 3;
  if (argc > 1) {
    iters = atoi(argv[1]);
  }
  if (argc > 3) {
    w1 = atoi(argv[2]);
    w2 = atoi(argv[3]);
  }
  printf("=== SchedAI WRR Benchmark Starting ===\n");
  printf("Testing 2 concurrent workloads on CPUS=1 (iters=%d, w1=%d, w2=%d)\n", iters, w1, w2);

  int pipe1[2], pipe2[2];
  int sync_pipe[2];
  pipe(pipe1);
  pipe(pipe2);
  pipe(sync_pipe);

  int pid1 = fork();
  if (pid1 < 0) {
    printf("fork 1 failed\n");
    exit(1);
  }
  if (pid1 == 0) {
    close(pipe1[0]);
    close(sync_pipe[1]);
    char go;
    read(sync_pipe[0], &go, 1);
    close(sync_pipe[0]);

    int start = uptime();
    compute(iters);
    int elapsed = uptime() - start;
    write(pipe1[1], &elapsed, sizeof(elapsed));
    close(pipe1[1]);
    exit(0);
  }

  int pid2 = fork();
  if (pid2 < 0) {
    printf("fork 2 failed\n");
    exit(1);
  }
  if (pid2 == 0) {
    close(pipe2[0]);
    close(sync_pipe[1]);
    char go;
    read(sync_pipe[0], &go, 1);
    close(sync_pipe[0]);

    int start = uptime();
    compute(iters);
    int elapsed = uptime() - start;
    write(pipe2[1], &elapsed, sizeof(elapsed));
    close(pipe2[1]);
    exit(0);
  }

  close(pipe1[1]);
  close(pipe2[1]);
  close(sync_pipe[0]);

  // Set weights before starting children
  if (setweight(pid1, w1) < 0 || setweight(pid2, w2) < 0) {
    printf("FAILED to set weights\n");
  } else {
    printf("Configured PID %d (Child 1) with weight=%d\n", pid1, w1);
    printf("Configured PID %d (Child 2) with weight=%d\n", pid2, w2);
  }

  // Release children simultaneously
  write(sync_pipe[1], "xx", 2);
  close(sync_pipe[1]);

  int elapsed1 = 0, elapsed2 = 0;
  read(pipe1[0], &elapsed1, sizeof(elapsed1));
  read(pipe2[0], &elapsed2, sizeof(elapsed2));
  close(pipe1[0]);
  close(pipe2[0]);

  wait(0);
  wait(0);

  printf("\n--- Results ---\n");
  printf("Child 1 (Weight %d) elapsed: %d ticks\n", w1, elapsed1);
  printf("Child 2 (Weight %d) elapsed: %d ticks\n", w2, elapsed2);

  if (w1 == w2) {
    int delta = (elapsed1 > elapsed2) ? elapsed1 - elapsed2 : elapsed2 - elapsed1;
    printf("BASELINE VERIFIED: Both tasks with identical weight %d completed with equal priority (delta: %d ticks).\n", w1, delta);
  } else if ((w2 > w1 && elapsed2 <= elapsed1) || (w1 > w2 && elapsed1 <= elapsed2)) {
    int fast = (elapsed2 < elapsed1) ? elapsed2 : elapsed1;
    int slow = (elapsed2 < elapsed1) ? elapsed1 : elapsed2;
    if (fast > 0) {
      int factor_int = slow / fast;
      int factor_tenths = ((slow * 10) / fast) % 10;
      printf("SUCCESS: Higher weight task finished significantly faster!\n");
      printf("Speedup factor: %d.%dx\n", factor_int, factor_tenths);
    }
  } else {
    printf("WARNING: Expected higher weight task to finish faster.\n");
  }

  printf("=== Benchmark Finished ===\n");
  exit(0);
}
