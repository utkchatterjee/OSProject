"""
Deterministic Mock LLM Engine for SchedAI
Converts natural-language scheduling instructions into constrained JSON updates
without requiring external network or API keys.
"""

import re
from typing import Dict, Any, Optional


class MockLLMEngine:
    def __init__(self):
        # Canned phrase exact matches
        self.canned_prompts = {
            "give process 4 more cpu time": {
                "pid": 4,
                "weight": 3,
                "reason": "Increasing CPU priority based on user request"
            },
            "prioritize process 4": {
                "pid": 4,
                "weight": 3,
                "reason": "Prioritizing process 4"
            },
            "give process 4 maximum cpu": {
                "pid": 4,
                "weight": 5,
                "reason": "Allocating maximum weight (5) to process 4"
            },
            "throttle process 3": {
                "pid": 3,
                "weight": 1,
                "reason": "Throttling process 3 to baseline weight"
            },
            "reset process 4": {
                "pid": 4,
                "weight": 1,
                "reason": "Restoring process 4 to default weight (1)"
            }
        }

    def infer(self, natural_language_prompt: str) -> Dict[str, Any]:
        """Translates user prompt into raw candidate JSON."""
        normalized = natural_language_prompt.strip().lower()

        # 1. Exact canned match check
        if normalized in self.canned_prompts:
            return dict(self.canned_prompts[normalized])

        # 2. Extract PID
        # Matches: process 4, proc 4, pid 4, p4, process #4
        pid_match = re.search(r"(?:process|proc|pid|p)\s*#?\s*(\d+)", normalized)
        if not pid_match:
            return {
                "error": "Could not identify target PID from instruction",
                "raw_input": natural_language_prompt
            }

        pid = int(pid_match.group(1))

        # Remove the matched PID portion from search text so it doesn't collide with weight
        remaining_text = normalized[:pid_match.start()] + " " + normalized[pid_match.end():]

        # 3. Explicit weight match (e.g. "weight 4", "to 5", "weight=3", "set weight ... to 4")
        explicit_w_match = re.search(r"(?:weight|to)\s*=?\s*(\d+)", remaining_text)
        if not explicit_w_match and "weight" in remaining_text:
            explicit_w_match = re.search(r"(\d+)", remaining_text)

        if explicit_w_match:
            weight = int(explicit_w_match.group(1))
            return {
                "pid": pid,
                "weight": weight,
                "reason": f"Explicit weight {weight} requested by user"
            }

        # 4. Semantic heuristics
        if any(w in normalized for w in ["max", "maximum", "highest", "top priority", "heavily", "critical"]):
            return {
                "pid": pid,
                "weight": 5,
                "reason": f"Elevating process {pid} to maximum scheduling weight (5)"
            }

        if any(w in normalized for w in ["reset", "default", "restore", "normal", "baseline"]):
            return {
                "pid": pid,
                "weight": 1,
                "reason": f"Resetting process {pid} to baseline weight (1)"
            }

        if any(w in normalized for w in ["throttle", "less", "lower", "slow down", "deprioritize"]):
            return {
                "pid": pid,
                "weight": 1,
                "reason": f"Throttling process {pid} to minimum weight (1)"
            }

        if any(w in normalized for w in ["more", "boost", "higher", "prioritize", "favor", "speed up", "faster"]):
            return {
                "pid": pid,
                "weight": 3,
                "reason": f"Boosting process {pid} CPU share to weight 3"
            }

        # Fallback if intent is unclear
        return {
            "pid": pid,
            "weight": 1,
            "reason": f"Unrecognized intent; defaulting process {pid} to weight 1"
        }
