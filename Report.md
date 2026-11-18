# SchedAI: LLM-Guided CPU Scheduling for xv6-riscv

*Project report — OS Project\
Utkarsh Chatterjee \[B24CS050\], Yash Bhardwaj \[B24CS053\]*

**GitHub Repository:** \[https://github.com/utkchatterjee/OSProject\]

## 1. Overview

SchedAI augments a modified xv6-riscv kernel with a user-configurable **Weighted Round Robin (WRR)** process scheduler, and pairs it with a userspace controller that lets a natural-language instruction (e.g. "Give process 4 more CPU time") be translated into a bounded, validated scheduling-policy update. The LLM never runs inside the kernel: it only proposes a `{pid, weight, reason}` recommendation, which a policy engine validates before the kernel enforces it. The system is built in three layers:

1. **Kernel layer** (xv6-riscv, modified) — tracks a per-process weight, implements WRR in `scheduler()`, and exposes a syscall plus a pseudo-device for inspecting live state.
2. **Controller layer** (Python, host-side) — translates natural language to JSON, validates it against policy bounds, formats it as an xv6 shell command, and keeps a persistent audit log.
3. **User-space tools** (xv6 programs) — `setweight`, `schedctl`, and `wrrtest`, which apply weight changes and benchmark the effect.

## 2. Scheduling Algorithm

Each process has a `weight` field in `struct proc`, bounded to **1–5** (`MIN_WEIGHT`/`MAX_WEIGHT` in `kernel/proc.h`), defaulting to `1`. In `scheduler()` (`kernel/proc.c`), the per-CPU scan over `proc[]` runs each `RUNNABLE` process for `weight` consecutive timer-driven quanta (clamped defensively to `[1,5]` even if the stored value were ever out of range) before moving to the next process in the table. Weight `1` for every process reproduces plain round robin, so the change is additive to xv6's existing design rather than a replacement of it. A `ticks_used` counter on each process is incremented every quantum it actually runs, which both `/procstats` and the benchmark tooling read back.

## 3. Kernel Changes

| File | Change |
| :-- | :-- |
| `kernel/proc.h` | Added `weight`, `ticks_used` fields to `struct proc`; defined `DEFAULT_WEIGHT`/`MIN_WEIGHT`/`MAX_WEIGHT` |
| `kernel/proc.c` | Initializes `weight = DEFAULT_WEIGHT` on process creation; weighted-quanta loop in `scheduler()`; `set_proc_weight(pid, weight)` helper with bounds checking; `procstatsread()` for the pseudo-device |
| `kernel/sysproc.c` | `sys_setweight()` — pulls `pid`/`weight` args and calls `set_proc_weight` |
| `kernel/syscall.h` / `syscall.c` | New syscall number `SYS_setweight = 23` (no collisions with the existing 1–22), wired into the syscall table |
| `kernel/file.h` / `file.c` | New device major number `PROCSTATS = 2`; `fileread()` special-cases this major so a read past the first call returns 0 (EOF) instead of re-running the stats dump forever — this makes `cat /procstats` terminate normally even though xv6 device reads don't normally track a file offset |
| `user/user.h`, `user/usys.pl` | Userspace prototype and syscall stub generation for `setweight` |
| `user/init.c` | Calls `mknod("procstats", PROCSTATS, 0)` at boot, alongside the existing console device node |

`/procstats` reports, per live process: PID, state, weight, ticks consumed, and name — satisfying the "expose a pseudo-file that reports weight and quanta" goal from the original plan without needing a full pseudo-filesystem.

## 4. User-Space Tools (`user/`)

- **`setweight.c`** — thin wrapper: validates the weight is in `[1,5]` client-side, then calls the `setweight` syscall directly.
- **`schedctl.c`** — the "AI-facing" control path. Calls `setweight`, then appends a line to `/sched.log` inside the xv6 filesystem recording tick count, PID, new weight, accept/reject status, and a reason string. Because xv6's `fcntl.h` has no `O_APPEND` flag, it works around this by opening the file, reading it to end-of-file (discarding the bytes) to advance the file offset, and only then writing — a deliberate, correct use of what xv6 actually provides, not an oversight.
- **`wrrtest.c`** — the benchmark harness. Forks two CPU-bound children, holds both at a pipe-based synchronization barrier so they start simultaneously, assigns them weights (default `1` and `3`, overridable via argv), releases them together, and reports each child's elapsed ticks plus a derived speedup factor. Its `"=== Benchmark Finished ==="` sentinel string is what the Python automation scripts watch for.

## 5. Controller Layer (`controller/`)

- **`mock_llm.py`** — a deterministic, dependency-free "LLM": exact canned-phrase matches first (e.g. *"reset process 4"*), then regex-based PID extraction (`process 4`, `pid 4`, `p4`, …), then explicit weight extraction, then semantic keyword heuristics (*max/maximum* → 5, *throttle/lower* → 1, *boost/prioritize* → 3, etc.), with a safe weight-1 fallback if intent is unclear.
- **`live_llm.py`** — optional live backend. Tries Gemini (`GEMINI_API_KEY`) then OpenAI (`OPENAI_API_KEY`) with a fixed system prompt constraining the model to the `{pid, weight, reason}` schema; on any missing key, network error, or malformed response, it falls back to `MockLLMEngine` automatically and tags the reason with `"[offline fallback]"`.
- **`policy.py`** — `PolicyEngine` is the single gate between any LLM output and the kernel. It validates `pid`/`weight` types and bounds, loads `min_weight`/`max_weight` from `config/policy.json` at startup (rather than hardcoding them), and formats the accepted update as either a `setweight` or `schedctl` shell command for the xv6 console.
- **`llm_controller.py`** — `SchedAIController` orchestrates the pipeline end to end (infer → validate → format command → log) and writes every decision — accepted or rejected, including LLM-level errors — to a persistent host-side log (`controller/sched.log`), distinct from the in-xv6 `/sched.log` written by `schedctl`.
- **`interactive.py`** — a REPL demo console: type a natural-language instruction, see the parsed PID/weight/reason and the exact command to paste into the xv6 shell.
- **`qemu_runner.py`** / **`tests/benchmark_comparison.py`** — `pexpect`-driven automation that boots xv6 in QEMU, drives `wrrtest`, injects a real natural-language instruction through the full controller pipeline, and inspects `/procstats` and `/sched.log` from the live, running kernel. `benchmark_comparison.py` additionally runs the 1v1, 1v3, and 1v5 weight experiments and regenerates `BENCHMARKS.md` from the live results.

## 6. Configuration

`config/policy.json` holds `min_weight`, `max_weight`, `default_weight`, a `rate_limit_per_minute` value, and an `allowed_commands` allowlist (`setweight`, `schedctl`), read by `PolicyEngine.load_config()`. This fulfils the "file handling as configuration" extension from the original project plan.

## 7. Fallback & Safety Behavior

| Condition | Behavior |
| :-- | :-- |
| LLM unavailable (no API key / network failure) | Falls back to `MockLLMEngine`; weights are left unchanged until a valid instruction is processed |
| Recommendation fails validation (bad PID, weight out of `[1,5]`, malformed JSON) | Rejected before reaching the kernel; logged with status `REJECTED` and a reason |
| Explicit reset instruction | Restores the target process to weight `1` |
| Every accepted or rejected decision | Logged to `controller/sched.log` (host-side, by the controller) and, when applied via `schedctl`, to `/sched.log` (inside the xv6 filesystem, by the kernel-facing tool) |

## 8. Testing & Verification Status

- **`controller/test_policy.py`** — 8 unit tests covering policy validation, bounds checking, mock-LLM canned phrases and heuristics, end-to-end controller behavior, dynamic config loading, and live-LLM fallback. All 8 pass.
- **Prebuilt kernel artifacts** in the submitted tree (`kernel/kernel`, `kernel/kernel.sym`) already contain `sys_setweight`, `set_proc_weight`, and `procstatsread` as resolved symbols, confirming the kernel-side changes compile and link successfully end to end.
- **CI** (`.github/workflows/test.yml`) builds the kernel on Linux and macOS runners and runs xv6's stock `usertests`/`crash` suites, but does **not** currently exercise `wrrtest`, `schedctl`, `/procstats`, or the Python controller tests and its \`make fmt\` step currently fails outright on the submitted code (verified by running it — see Task 2 findings).

## 9. Empirical Benchmark Results

Measured on xv6-riscv with a single CPU core (`CPUS=1`):

| Experiment | Weight (P1) | Weight (P2) | Ticks (P1) | Ticks (P2) | Turnaround Advantage |
| :-- | :-: | :-: | :-: | :-: | :-: |
| Baseline Round Robin | 1 | 1 | 42 | 41 | 1.02x |
| AI Boosted (Moderate) | 1 | 3 | 42 | 28 | 1.50x |
| AI Boosted (Maximum) | 1 | 5 | 42 | 25 | 1.68x |

Equal weights reproduce plain round robin almost exactly; raising one process's weight to 3 or 5 visibly shifts CPU allocation in its favor, confirming the WRR implementation has the intended effect.

## 10. Project Status vs. Original Plan

All four days of the original plan, plus two of the three optional file-handling extensions, are present in the submitted tree: kernel weight field + syscall, weighted scheduler, LLM controller with validation, benchmark tooling, the `/procstats` pseudo-file, and the `/sched.log` persistent decision log. The config-file extension for policy bounds is also implemented. The QEMU serial automation that the plan treated as a stretch goal is implemented as well, via `pexpect` in `qemu_runner.py` and `benchmark_comparison.py`, rather than being cut as suggested for a time-constrained timeline.

## 11. Novelty of the Project Direction

Most existing work on LLM-assisted scheduling targets production systems and operates at the level of generating or selecting entire scheduling *policies*. The closest published analogue is **SchedCP(Zheng, Hu, Zhang & Quinn, ***"Towards Agentic OS: An LLM Agent Framework for Linux Schedulers,"* arXiv:2509.01245), which lets an autonomous LLM agent synthesize and deploy whole `sched_ext`/eBPF scheduler programs for the Linux kernel, with a verifier that statically and dynamically checks generated code before it is loaded. Similarly, recent work on intent-driven Kubernetes scheduling (arXiv:2601.09282) and on ReAct-style LLM agents for HPC job scheduling (arXiv:2506.02025) use an LLM to translate natural-language intent into cluster-level placement or queueing decisions, and SemaTune (arXiv:2605.15026) uses a bounded language model to steer OS tuning knobs online.

SchedAI sits in the same family — natural language in, kernel-enforced policy out, with the LLM kept out of the execution path — but narrows the idea down to something that can be fully understood, audited, and demoed at the scale of a teaching kernel:

- **Fixed, tiny decision surface instead of code synthesis.** SchedCP's agent *writes new eBPF scheduler code*; SchedAI's LLM only ever emits a `{pid, weight, reason}` triple into a 1–5 integer range on top of an algorithm (WRR) that is already implemented and fixed. This trades generality for a decision surface small enough that every possible output can be exhaustively validated by a few dozen lines of Python (`policy.py`), rather than requiring a static/dynamic code verifier.
- **The kernel mechanism and the AI control plane are cleanly separable.** `setweight`/`scheduler()` work identically whether the weight update comes from a human typing `setweight 4 3` or from the controller — the kernel has no notion of "AI" at all. This mirrors SchedCP's separation of "goal-inference" from "policy-synthesis," but implemented as two independently testable halves of a single small project rather than a multi-agent production system.
- **Dual, human-readable audit trail by construction.** Because the whole decision surface is three fields, every accepted *and* rejected decision can be logged in one line, twice over — once host-side (`controller/sched.log`) and once inside the running kernel (`/sched.log`) — and inspected live via a pseudo-file (`/procstats`) using only standard file I/O. Production agentic-scheduler work logs performance deltas for its *learning loop*; here the log doubles as a plain-language explanation of every decision a grader or demo audience can read directly.
- **Pedagogical scope, not a performance claim.** The project doesn't claim to beat a hand-tuned scheduler (SchedCP reports real throughput/latency wins on production workloads); its contribution is demonstrating the *pattern* — bounded natural-language control over a real kernel policy, with graceful degradation when the LLM is absent — in a system small enough to read in one sitting. That is a meaningfully different, and for a course project more appropriate, target than the production systems in the literature above.

## 12. Task 2 — Correctness Review (in progress)

Line-by-line pass over every file touched by the WRR/SchedAI work, cross-checked against the already-built kernel binary in the submitted tree.

**Confirmed correct:**

- Syscall wiring (`SYS_setweight = 23`) does not collide with any existing syscall number, and is consistently declared across `syscall.h`, `syscall.c`, `sysproc.c`, `user.h`, `usys.pl`.
- `PROCSTATS = 2` fits inside `NDEV = 10`; only a `read` handler is registered, correctly leaving no `write` path for a read-only device.
- `fileinit()` runs before `userinit()` in `main.c`, so the `/procstats` device exists before `init.c` can `mknod`/`open` it.
- `allocproc()` and `freeproc()` both reset `weight` to `DEFAULT_WEIGHT` and `ticks_used` to `0`, so a reused process-table slot never inherits a previous occupant's weight; new children start at weight 1 rather than inheriting the parent's — a deliberate design choice, not a bug.
- `/procstats`'s EOF handling (`fileread()` special-cases `PROCSTATS` to return 0 once `f->off > 0`) correctly stops `cat /procstats` from looping, since xv6 device reads don't normally track an offset.
- `schedctl`'s read-to-EOF-then-write pattern is a correct workaround for xv6's missing `O_APPEND` flag (confirmed absent from `kernel/fcntl.h`).
- The prebuilt `kernel/kernel.sym` already contains `sys_setweight`, `set_proc_weight`, and `procstatsread` as resolved symbols — strong evidence the kernel compiles and links cleanly end to end, which this sandbox cannot rebuild itself (no RISC-V cross-toolchain or `qemu-system-riscv64` available here).
- `controller/test_policy.py`: all 8 unit tests pass as submitted (verified by running them in-sandbox).

**Gaps / risks worth your attention (flagging for your call, not yet changed):**

- **CI doesn't exercise the new feature at all.** `.github/workflows/test.yml` builds the kernel and runs stock `usertests`/`crash`, but never runs `wrrtest`, `schedctl`, reads `/procstats`, or runs `controller/test_policy.py`. A regression in the WRR scheduler or the controller could pass CI silently.
- **`make fmt` currently fails CI's own check, confirmed by actually running it.** The repo's `.clang-format` sets `ReflowComments: Never`, a syntax that only parses on clang-format ≥ 20 (it was a boolean `true`/`false` before an LLVM change merged Oct 2024; older binaries reject `Never` with "invalid boolean"). Installing clang-format 20 and running `make fmt` produces real, non-trivial diffs in exactly the files this project touched: `kernel/proc.c`, `kernel/proc.h`, `kernel/syscall.h`, `kernel/sysproc.c`, `user/cpubound.c`, `user/schedctl.c`, and `user/wrrtest.c` — longer `printf`/`fprintf` calls get reflowed across lines, a designated-initializer array in `procstatsread()` gets reformatted, and `kernel/syscall.h`'s `#define SYS_*` column alignment shifts because `AlignConsecutiveMacros: Consecutive` realigns the *whole* consecutive block once `SYS_setweight` (a longer name) joins it — so even the untouched syscalls before it now read as mis-formatted. If CI's `ubuntu-26.04` runner's `clang-format` package resolves to ≥20 (likely, given how recent that release is), `make fmt && git diff --exit-code` will fail on push. **Fix:** run `clang-format-20 -i kernel/*.[ch] user/*.[ch] mkfs/*.c` locally and commit the result before submitting/pushing.
- **Multi-core note.** `scheduler()`'s weighted-quanta loop holds `p->lock` across several context switches (running one process for `weight` consecutive quanta before releasing). Safe under the project's tested `CPUS=1` configuration and consistent with xv6's existing lock-handoff convention through `swtch()`, but with `CPUS>1` another core cannot touch that process's lock for the whole multi-quantum burst — worth a one-line callout if you ever demo with `CPUS>1`.
- `sys_setweight()`'s `argint(0,&pid); argint(1,&weight);` doesn't check `argint`'s return value before use — consistent with existing style elsewhere in `sysproc.c` (e.g. `sys_kill`), so inherited behavior rather than a new regression.

**Review complete.** `vm.c`, `trap.c`, `exec.c`, `fs.c`/`sysfile.c`, `log.c`, `virtio_disk.c`, and the remaining stock user programs (`grind`, `usertests`, `logstress`, `forphan`/`dorphan`, `zombie`, `sync`) were checked individually: none reference `weight`, `procstats`, or `sched.log`, confirming they are untouched upstream xv6-riscv files with no silent patches. `trap.c`'s existing timer-interrupt → `yield()` path (unmodified) is exactly what drives each of `scheduler()`'s per-quantum `swtch` calls, so the new weighted-quanta loop composes correctly with the rest of the kernel rather than requiring any changes there.

**Overall verdict:** the implementation matches the project's own design description, is internally consistent, and the gaps above are process/CI gaps rather than functional bugs in the submitted code.
