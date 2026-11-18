# SchedAI: LLM-Guided CPU Scheduling for xv6-riscv

*Project report — OS Project\
Utkarsh Chatterjee \[B24CS050\], Yash Bhardwaj \[B24CS053\]*

**GitHub Repository:** \[https://github.com/utkchatterjee/OSProject\]

## 1. Overview

**This operating-systems project is, at its core : a modified process scheduler inside the xv6-riscv kernel.** Contains — a new per-process `weight` field, a Weighted Round Robin (WRR) dispatch loop in `scheduler()`, a new syscall, and a new pseudo-device for inspecting live scheduler state — lives inside `kernel/` and is fully functional and independently demonstrable with nothing but the stock xv6 shell: `setweight <pid> <weight>` and `wrrtest` exercise the real mechanism with zero Python involved. Sections 2–4 below describe this kernel mechanism and section 5 proves it works empirically.

On top of that kernel mechanism, a host-side Python layer (Section 6 onward) lets a natural-language instruction (e.g. "Give process 4 more CPU time") drive the same `setweight` syscall instead of a human typing it directly. This layer is a convenience interface : `scheduler()` and `setweight` have no notion of "AI" and behave identically regardless of whether the weight change came from a human at the console or from the controller. The LLM never runs inside the kernel, and never executes anything directly — it only proposes a `{pid, weight, reason}` triple, which a policy engine validates before anything is applied.

The system is built in three layers:

1. **Kernel layer** (xv6-riscv, modified) — tracks a per-process weight, implements WRR in `scheduler()`, and exposes a syscall plus a pseudo-device for inspecting live state.
2. **User-space tools** (xv6 programs) — `setweight`, `schedctl`, and `wrrtest`, which apply weight changes and benchmark the effect directly against the kernel, independent of any Python layer.
3. **Controller layer** (Python, host-side, optional) — translates natural language to JSON, validates it against policy bounds, formats it as an xv6 shell command, and keeps a persistent audit log.

## 2. Core OS Contribution: The WRR Scheduling Algorithm

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

These are plain xv6 C programs that talk to the kernel mechanism directly — none of them depend on or invoke any part of the Python layer.

- **`setweight.c`** — thin wrapper: validates the weight is in `[1,5]` client-side, then calls the `setweight` syscall directly.
- **`schedctl.c`** — the "AI-facing" control path, but usable identically from the shell by hand. Calls `setweight`, then appends a line to `/sched.log` inside the xv6 filesystem recording tick count, PID, new weight, accept/reject status, and a reason string. Because xv6's `fcntl.h` has no `O_APPEND` flag, it works around this by opening the file, reading it to end-of-file (discarding the bytes) to advance the file offset, and only then writing — a deliberate, correct use of what xv6 actually provides, not an oversight.
- **`wrrtest.c`** — the benchmark harness, and the simplest way to see the WRR mechanism work with nothing else running. Forks two CPU-bound children, holds both at a pipe-based synchronization barrier so they start simultaneously, assigns them weights (default `1` and `3`, overridable via argv), releases them together, and reports each child's elapsed ticks plus a derived speedup factor. Its `"=== Benchmark Finished ==="` sentinel string is what the Python automation scripts watch for — an optional convenience.

## 5. Empirical Benchmark Results — Proof the Kernel Mechanism Works

Measured on xv6-riscv with a single CPU core (`CPUS=1`), using `wrrtest` :

| Experiment | Weight (P1) | Weight (P2) | Ticks (P1) | Ticks (P2) | Turnaround Advantage |
| :-- | :-: | :-: | :-: | :-: | :-: |
| Baseline Round Robin | 1 | 1 | 42 | 41 | 1.02x |
| AI Boosted (Moderate) | 1 | 3 | 42 | 28 | 1.50x |
| AI Boosted (Maximum) | 1 | 5 | 42 | 25 | 1.68x |

Equal weights reproduce plain round robin almost exactly; raising one process's weight to 3 or 5 visibly shifts CPU allocation in its favor, confirming the WRR implementation has the intended effect.

## 6. Convenience Layer: Natural-Language Control Plane (Python, host-side)


- **`mock_llm.py`** — a deterministic, dependency-free "LLM": exact canned-phrase matches first (e.g. *"reset process 4"*), then regex-based PID extraction (`process 4`, `pid 4`, `p4`, …), then explicit weight extraction, then semantic keyword heuristics (*max/maximum* → 5, *throttle/lower* → 1, *boost/prioritize* → 3, etc.), with a safe weight-1 fallback if intent is unclear.
- **`live_llm.py`** — optional live backend. Tries Gemini (`GEMINI_API_KEY`) then OpenAI (`OPENAI_API_KEY`) with a fixed system prompt constraining the model to the `{pid, weight, reason}` schema; on any missing key, network error, or malformed response, it falls back to `MockLLMEngine` automatically and tags the reason with `"[offline fallback]"`.
- **`policy.py`** — `PolicyEngine` is the single gate between any LLM output and the kernel. It validates `pid`/`weight` types and bounds, loads `min_weight`/`max_weight` from `config/policy.json` at startup (rather than hardcoding them), and formats the accepted update as either a `setweight` or `schedctl` shell command for the xv6 console.
- **`llm_controller.py`** — `SchedAIController` orchestrates the pipeline end to end (infer → validate → format command → log) and writes every decision — accepted or rejected, including LLM-level errors — to a persistent host-side log (`controller/sched.log`), distinct from the in-xv6 `/sched.log` written by `schedctl`.
- **`interactive.py`** — a REPL demo console: type a natural-language instruction, see the parsed PID/weight/reason and the exact command to paste into the xv6 shell.
- **`qemu_runner.py`** / **`tests/benchmark_comparison.py`** — `pexpect`-driven automation that boots xv6 in QEMU, drives `wrrtest`, injects a real natural-language instruction through the full controller pipeline, and inspects `/procstats` and `/sched.log` from the live, running kernel. `benchmark_comparison.py` additionally runs the 1v1, 1v3, and 1v5 weight experiments and regenerates `BENCHMARKS.md` from the live results.

## 7. Configuration

`config/policy.json` holds `min_weight`, `max_weight`, `default_weight`, a `rate_limit_per_minute` value, and an `allowed_commands` allowlist (`setweight`, `schedctl`), read by `PolicyEngine.load_config()`. This fulfils the "file handling as configuration" extension from the original project plan.

## 8. Fallback & Safety Behavior

| Condition | Behavior |
| :-- | :-- |
| LLM unavailable (no API key / network failure) | Falls back to `MockLLMEngine`; weights are left unchanged until a valid instruction is processed |
| Recommendation fails validation (bad PID, weight out of `[1,5]`, malformed JSON) | Rejected before reaching the kernel; logged with status `REJECTED` and a reason |
| Explicit reset instruction | Restores the target process to weight `1` |
| Every accepted or rejected decision | Logged to `controller/sched.log` (host-side, by the controller) and, when applied via `schedctl`, to `/sched.log` (inside the xv6 filesystem, by the kernel-facing tool) |

## 9. Testing & Verification Status

- **`controller/test_policy.py`** — 8 unit tests covering policy validation, bounds checking, mock-LLM canned phrases and heuristics, end-to-end controller behavior, dynamic config loading, and live-LLM fallback. All 8 pass.
- **Prebuilt kernel artifacts** in the submitted tree (`kernel/kernel`, `kernel/kernel.sym`) already contain `sys_setweight`, `set_proc_weight`, and `procstatsread` as resolved symbols, confirming the kernel-side changes compile and link successfully end to end.

## 10. Novelty

Most existing work on LLM-assisted scheduling targets production systems and operates at the level of generating or selecting entire scheduling *policies*. The closest published analogue is **SchedCP** (Zheng, Hu, Zhang & Quinn, *"Towards Agentic OS: An LLM Agent Framework for Linux Schedulers,"* arXiv:2509.01245), which lets an autonomous LLM agent synthesize and deploy whole `sched_ext`/eBPF scheduler programs for the Linux kernel, with a verifier that statically and dynamically checks generated code before it is loaded. Similarly, recent work on intent-driven Kubernetes scheduling (arXiv:2601.09282) and on ReAct-style LLM agents for HPC job scheduling (arXiv:2506.02025) use an LLM to translate natural-language intent into cluster-level placement or queueing decisions, and SemaTune (arXiv:2605.15026) uses a bounded language model to steer OS tuning knobs online.

SchedAI sits in the same family — natural language in, kernel-enforced policy out, with the LLM kept out of the execution path — but narrows the idea down to something that can be fully understood, audited, and demoed at the scale of a teaching kernel:

- **Fixed, tiny decision surface instead of code synthesis.** SchedCP's agent *writes new eBPF scheduler code*; SchedAI's LLM only ever emits a `{pid, weight, reason}` triple into a 1–5 integer range on top of an algorithm (WRR) that is already implemented and fixed in the kernel. This trades generality for a decision surface small enough that every possible output can be exhaustively validated by a few dozen lines of Python (`policy.py`), rather than requiring a static/dynamic code verifier.
- **The kernel mechanism and the AI control plane are cleanly separable.** `setweight`/`scheduler()` work identically whether the weight update comes from a human typing `setweight 4 3` or from the controller — the kernel has no notion of "AI" at all. This mirrors SchedCP's separation of "goal-inference" from "policy-synthesis," but implemented as two independently testable halves of a single small project rather than a multi-agent production system.
- **Dual, human-readable audit trail by construction.** Because the whole decision surface is three fields, every accepted *and* rejected decision can be logged in one line, twice over — once host-side (`controller/sched.log`) and once inside the running kernel (`/sched.log`) — and inspected live via a pseudo-file (`/procstats`) using only standard file I/O. Production agentic-scheduler work logs performance deltas for its *learning loop*; here the log doubles as a plain-language explanation of every decision a grader or demo audience can read directly.
- **Pedagogical scope, not a performance claim.** The project doesn't claim to beat a hand-tuned scheduler (SchedCP reports real throughput/latency wins on production workloads); its contribution is demonstrating the *pattern* — bounded natural-language control over a real kernel policy, with graceful degradation when the LLM is absent — in a system small enough to read in one sitting. That is a meaningfully different, and for a course project more appropriate, target than the production systems in the literature above.

## 11. Future Scope: Deepening the Kernel Mechanism

The natural-language layer is close to feature-complete; the highest-value next steps are all inside the kernel, and would strengthen the project.

- **Fix the multi-core locking gap.** `scheduler()` currently holds `p->lock` across a process's entire multi-quantum burst, which is safe only under the tested `CPUS=1` configuration (see Task 2). Reworking the loop to release and re-acquire `p->lock` once per quantum — re-checking `RUNNABLE` state and weight each time — would make WRR correct under `CPUS>1`
- **Starvation protection via weight aging.** A long-starved low-weight process currently has no mechanism to catch up. Tracking wait time per process and temporarily boosting effective weight the longer a `RUNNABLE` process goes without running (similar in spirit to xv6's original `MLFQS`-style aging, or Linux's old O(1) scheduler's interactive bonus) would turn WRR into something closer to a *fair* scheduler rather than a strictly static-weight one.
- **Virtual-runtime-based fairness (CFS-style) instead of fixed quanta bursts.** Replacing "run for `weight` consecutive quanta" with a per-process virtual runtime that advances inversely proportional to weight (the core idea behind Linux's CFS) would let the scheduler interleave weighted processes far more smoothly than running one for several whole quanta at a time, and would be a substantially deeper OS contribution to describe and defend.
- **Priority inheritance for locks.** If a high-weight process blocks on a spinlock or sleep-lock held by a low-weight process, the low-weight holder should temporarily inherit the waiter's weight to avoid priority inversion — a classic OS problem (famously relevant to the Mars Pathfinder incident) that xv6's current lock implementation does not address at all.
- **Group-based weights instead of per-PID weights.** Extending `set_proc_weight` to apply to a process *group* (e.g. all children of a session leader) rather than a single PID would move the mechanism closer to a real resource-control model (cgroups-lite), and would require kernel-side bookkeeping of process relationships beyond what the current `parent` pointer already tracks.
- **Access control on `setweight`.** Any process can currently raise or lower any other process's weight. Restricting `setweight` to root or to a process's own descendants — enforced inside `sys_setweight()`, not in the Python layer — would close an obvious kernel-level security gap and is a natural extension of xv6's existing (minimal) permission model.
- **Richer `/procstats` accounting.** Exposing per-process wall-clock run time, average wait time, and a context-switch count (not just raw tick counts) would make `/procstats` a real scheduling-observability tool rather than a demo pseudo-file, and would require deeper instrumentation inside `scheduler()` and `yield()`.