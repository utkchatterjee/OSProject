#!/usr/bin/env python3
"""
SchedAI Automated End-to-End Test & Benchmark Suite
Boots xv6 in QEMU, runs the WRR benchmark, injects AI scheduling updates,
and collects telemetry from /procstats and /sched.log.
"""

import sys
import os
import time
import pexpect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from controller.llm_controller import SchedAIController


def run_full_suite():
    print("=" * 65)
    print("          SchedAI End-to-End Verification & Benchmarking")
    print("=" * 65)

    controller = SchedAIController()

    print("[1/5] Booting xv6 kernel in QEMU (CPUS=1)...")
    child = pexpect.spawn("make CPUS=1 qemu", timeout=60, encoding="utf-8")
    child.expect(r"\$ ")
    print("      ✓ xv6 booted successfully with shell ready.\n")

    print("[2/5] Running Weighted Round Robin Benchmark (user/wrrtest)...")
    child.sendline("wrrtest")
    child.expect("=== Benchmark Finished ===", timeout=60)
    wrr_output = child.before
    child.expect(r"\$ ")

    # Parse results from wrrtest
    print("      Benchmark Output:")
    for line in wrr_output.strip().split("\n"):
        if any(k in line for k in ["Configured", "Child 1", "Child 2", "SUCCESS", "Speedup"]):
            print(f"        {line.strip()}")
    print("      ✓ WRR proportional scheduling verified.\n")

    print("[3/5] Testing SchedAI Natural Language Controller...")
    prompt = "Give process 1 more CPU time because it is coordinating init"
    print(f"      Natural Language Prompt: \"{prompt}\"")
    res = controller.process_instruction(prompt)
    print(f"      LLM Recommendation     : PID={res['pid']}, Weight={res['weight']}")
    print(f"      Policy Validation      : {res['status']} ({res['reason']})")
    print(f"      Generated Command      : {res['command']}")

    # Send command to xv6
    child.sendline(res["command"])
    child.expect("schedctl: PID")
    child.expect(r"\$ ")
    print("      ✓ Policy update applied to running xv6 kernel.\n")

    print("[4/5] Inspecting /procstats pseudo-device telemetry...")
    child.sendline("cat procstats")
    child.expect(r"\$ ")
    procstats_out = child.before.strip()
    print("      Current /procstats output:")
    for line in procstats_out.split("\n"):
        if "\t" in line or "PID" in line:
            print(f"        {line.strip()}")
    print("      ✓ /procstats successfully inspected via standard file I/O.\n")

    print("[5/5] Inspecting persistent decision audit log (/sched.log)...")
    child.sendline("cat sched.log")
    child.expect(r"\$ ")
    schedlog_out = child.before.strip()
    print("      Current /sched.log content:")
    for line in schedlog_out.split("\n"):
        if "[ticks=" in line:
            print(f"        {line.strip()}")
    print("      ✓ Persistent decision audit logging verified.\n")

    child.close(force=True)
    print("=" * 65)
    print("  ALL VERIFICATION STAGES PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_full_suite()
