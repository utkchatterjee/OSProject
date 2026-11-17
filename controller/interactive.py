#!/usr/bin/env python3
"""
SchedAI Interactive Demo Console
Run this script to interactively test natural-language scheduling instructions.
"""

import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from controller.llm_controller import SchedAIController


def main():
    controller = SchedAIController()

    print("=" * 60)
    print("      SchedAI: LLM-Guided Scheduling Controller Console")
    print("=" * 60)
    print("Type a natural-language scheduling instruction.")
    print("Examples:")
    print("  - 'Give process 4 more CPU time'")
    print("  - 'Prioritize PID 2 heavily'")
    print("  - 'Throttle process 3'")
    print("  - 'Set weight of process 4 to 2'")
    print("  - 'Reset process 4'")
    print("Type 'exit' or 'quit' to leave.\n")

    while True:
        try:
            line = input("SchedAI Prompt > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not line:
            continue
        if line.lower() in ["exit", "quit", "q"]:
            print("Exiting.")
            break

        res = controller.process_instruction(line)

        print("\n--- Controller Evaluation ---")
        if res["success"]:
            print(f"[STATUS]   : ACCEPTED")
            print(f"[TARGET]   : PID {res['pid']}")
            print(f"[WEIGHT]   : {res['weight']}")
            print(f"[REASON]   : {res['reason']}")
            print(f"[XV6 CMD]  : {res['command']}")
            print("\nCopy & paste the [XV6 CMD] into the xv6 console to apply.\n")
        else:
            print(f"[STATUS]   : REJECTED")
            print(f"[ERROR]    : {res.get('error')}")
            print(f"[RAW REQ]  : {res.get('raw_recommendation')}\n")


if __name__ == "__main__":
    main()
