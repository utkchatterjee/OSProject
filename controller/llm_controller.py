"""
SchedAI Main Controller
Bridges natural language interpretation, policy validation, and xv6 execution.
"""

import os
import time
from typing import Dict, Any, Tuple, Optional
from controller.mock_llm import MockLLMEngine
from controller.live_llm import LiveLLMEngine
from controller.policy import PolicyEngine


class SchedAIController:
    def __init__(self, log_path: str = "controller/sched.log", mode: str = "mock"):
        self.mode = mode
        if mode == "live":
            self.llm = LiveLLMEngine()
        else:
            self.llm = MockLLMEngine()
        self.policy_engine = PolicyEngine()
        self.log_path = log_path

    def process_instruction(self, instruction: str) -> Dict[str, Any]:
        """
        End-to-end processing:
        1. Translate instruction via LLM -> raw JSON
        2. Validate against kernel policy
        3. Record to decision log
        4. Return execution result
        """
        # Step 1: LLM Inference
        raw_recommendation = self.llm.infer(instruction)

        if "error" in raw_recommendation:
            result = {
                "success": False,
                "error": raw_recommendation["error"],
                "raw_recommendation": raw_recommendation,
                "command": None,
                "status": "REJECTED"
            }
            self._log_decision("N/A", "N/A", "REJECTED", raw_recommendation["error"], instruction)
            return result

        # Step 2: Policy Engine Validation
        valid, update, message = self.policy_engine.validate_and_apply_policy(raw_recommendation)

        if not valid:
            result = {
                "success": False,
                "error": message,
                "raw_recommendation": raw_recommendation,
                "command": None,
                "status": "REJECTED"
            }
            self._log_decision(
                raw_recommendation.get("pid", "N/A"),
                raw_recommendation.get("weight", "N/A"),
                "REJECTED",
                message,
                instruction
            )
            return result

        # Step 3: Format xv6 Command
        cmd = self.policy_engine.format_xv6_command(update, use_schedctl=True)

        result = {
            "success": True,
            "pid": update["pid"],
            "weight": update["weight"],
            "reason": update["reason"],
            "command": cmd,
            "status": "ACCEPTED"
        }

        # Step 4: Audit Logging
        self._log_decision(update["pid"], update["weight"], "ACCEPTED", update["reason"], instruction)
        return result

    def _log_decision(self, pid: Any, weight: Any, status: str, reason: str, user_prompt: str) -> None:
        """Appends decision record to the persistent host-side audit log."""
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"[{timestamp}] PID={pid} | WEIGHT={weight} | STATUS={status} | "
            f"PROMPT=\"{user_prompt}\" | REASON=\"{reason}\"\n"
        )
        with open(self.log_path, "a") as f:
            f.write(entry)
