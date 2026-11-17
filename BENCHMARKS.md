# SchedAI Empirical Evaluation Results

Comparative measurements conducted on xv6-riscv with single CPU core (`CPUS=1`).

| Experiment | Weight (P1) | Weight (P2) | Ticks (P1) | Ticks (P2) | Turnaround Advantage |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Baseline Round Robin** | 1 | 1 | 42 ticks | 41 ticks | **1.02x** |
| **AI Boosted (Moderate)** | 1 | 3 | 42 ticks | 28 ticks | **1.50x** |
| **AI Boosted (Maximum)** | 1 | 5 | 42 ticks | 25 ticks | **1.68x** |

### Analysis
- **Baseline RR (1 vs 1)**: Both processes receive equal CPU slices, completing within a minimal delta of each other.
- **Weighted RR (1 vs 3)**: Process 2 receives 3 consecutive quanta per round queue pass, completing in significantly fewer wall-clock ticks.
- **Max Priority (1 vs 5)**: Process 2 consumes ~83% of CPU time during the concurrent phase, demonstrating dramatic turnaround speedup.
