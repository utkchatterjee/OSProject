"""
SchedAI Policy Engine
Validates and constrains LLM-generated scheduling recommendations
before passing them to the xv6 kernel.
"""

from typing import Dict, Any, Tuple, Optional
import json
import os

MIN_WEIGHT = 1
MAX_WEIGHT = 5
DEFAULT_WEIGHT = 1


class PolicyEngine:
    def __init__(self, config_path: Optional[str] = "config/policy.json", min_weight: int = MIN_WEIGHT, max_weight: int = MAX_WEIGHT):
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.config_path = config_path
        if config_path and os.path.exists(config_path):
            self.load_config(config_path)

    def load_config(self, path: str) -> None:
        """Loads policy bounds dynamically from configuration file."""
        try:
            with open(path, "r") as f:
                cfg = json.load(f)
                self.min_weight = int(cfg.get("min_weight", self.min_weight))
                self.max_weight = int(cfg.get("max_weight", self.max_weight))
        except Exception:
            pass

    def validate_and_apply_policy(self, update: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        """
        Validates an LLM recommendation dictionary:
        Expected schema: {"pid": int, "weight": int, "reason": str}
        Returns: (is_valid, sanitized_update, message)
        """
        if not isinstance(update, dict):
            return False, {}, "Recommendation must be a JSON object"

        if "pid" not in update or "weight" not in update:
            return False, {}, "Missing required fields 'pid' or 'weight'"

        # Validate PID
        try:
            pid = int(update["pid"])
            if pid <= 0:
                return False, {}, f"Invalid PID {pid}: must be a positive integer"
        except (ValueError, TypeError):
            return False, {}, f"PID {update.get('pid')} is not a valid integer"

        # Validate Weight
        try:
            weight = int(update["weight"])
        except (ValueError, TypeError):
            return False, {}, f"Weight {update.get('weight')} is not a valid integer"

        reason = str(update.get("reason", "No reason provided"))

        # Policy bounds check
        if weight < self.min_weight or weight > self.max_weight:
            return False, {
                "pid": pid,
                "weight": weight,
                "reason": reason
            }, f"Weight {weight} out of bounds [{self.min_weight}, {self.max_weight}]"

        sanitized = {
            "pid": pid,
            "weight": weight,
            "reason": reason,
            "status": "ACCEPTED"
        }
        return True, sanitized, "Policy update accepted"

    def format_xv6_command(self, validated_update: Dict[str, Any], use_schedctl: bool = True) -> str:
        """Generates the command string to be sent to xv6 shell."""
        pid = validated_update["pid"]
        weight = validated_update["weight"]
        reason = validated_update.get("reason", "policy_update").replace('"', "").replace("'", "")

        if use_schedctl:
            # schedctl logs decision into /sched.log inside xv6
            words = reason.split()
            if len(words) > 6:
                reason = " ".join(words[:6])
            return f"schedctl {pid} {weight} {reason}"
        return f"setweight {pid} {weight}"
