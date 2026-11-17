"""
Unit Tests for SchedAI Controller & Policy Engine
"""

import unittest
import os
import shutil
from controller.policy import PolicyEngine, MIN_WEIGHT, MAX_WEIGHT
from controller.mock_llm import MockLLMEngine
from controller.llm_controller import SchedAIController


class TestSchedAIPolicy(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine()
        self.mock_llm = MockLLMEngine()
        self.test_log = "controller/test_sched.log"
        self.controller = SchedAIController(log_path=self.test_log)

    def tearDown(self):
        if os.path.exists(self.test_log):
            os.remove(self.test_log)

    def test_valid_policy_update(self):
        update = {"pid": 4, "weight": 3, "reason": "Boost CPU"}
        valid, sanitized, msg = self.engine.validate_and_apply_policy(update)
        self.assertTrue(valid)
        self.assertEqual(sanitized["pid"], 4)
        self.assertEqual(sanitized["weight"], 3)
        self.assertEqual(sanitized["status"], "ACCEPTED")

    def test_weight_out_of_bounds(self):
        # Above maximum
        valid, _, msg = self.engine.validate_and_apply_policy({"pid": 4, "weight": 10})
        self.assertFalse(valid)
        self.assertIn("out of bounds", msg)

        # Below minimum
        valid, _, msg = self.engine.validate_and_apply_policy({"pid": 4, "weight": 0})
        self.assertFalse(valid)
        self.assertIn("out of bounds", msg)

    def test_invalid_pid(self):
        valid, _, msg = self.engine.validate_and_apply_policy({"pid": -1, "weight": 3})
        self.assertFalse(valid)
        self.assertIn("must be a positive integer", msg)

        valid, _, msg = self.engine.validate_and_apply_policy({"pid": "invalid", "weight": 3})
        self.assertFalse(valid)

    def test_mock_llm_canned_queries(self):
        res = self.mock_llm.infer("Give process 4 more CPU time")
        self.assertEqual(res["pid"], 4)
        self.assertEqual(res["weight"], 3)

        res = self.mock_llm.infer("Throttle process 3")
        self.assertEqual(res["pid"], 3)
        self.assertEqual(res["weight"], 1)

        res = self.mock_llm.infer("Reset process 4")
        self.assertEqual(res["pid"], 4)
        self.assertEqual(res["weight"], 1)

    def test_mock_llm_heuristics(self):
        # Maximum
        res = self.mock_llm.infer("process 2 is critical, give it maximum priority")
        self.assertEqual(res["pid"], 2)
        self.assertEqual(res["weight"], 5)

        # Explicit weight
        res = self.mock_llm.infer("set weight of proc 7 to 4")
        self.assertEqual(res["pid"], 7)
        self.assertEqual(res["weight"], 4)

        # Missing PID
        res = self.mock_llm.infer("make it faster please")
        self.assertIn("error", res)

    def test_end_to_end_controller(self):
        res = self.controller.process_instruction("Give process 4 more CPU time")
        self.assertTrue(res["success"])
        self.assertEqual(res["command"], "schedctl 4 3 Increasing CPU priority based on user")
        self.assertTrue(os.path.exists(self.test_log))

        # Check rejection handling
        res_rej = self.controller.process_instruction("set weight of proc 2 to 99")
        self.assertFalse(res_rej["success"])
        self.assertEqual(res_rej["status"], "REJECTED")

    def test_dynamic_config_loading(self):
        # Verify engine loads bounds from config/policy.json
        engine = PolicyEngine(config_path="config/policy.json")
        self.assertEqual(engine.min_weight, 1)
        self.assertEqual(engine.max_weight, 5)

    def test_live_llm_graceful_fallback(self):
        from controller.live_llm import LiveLLMEngine
        live_engine = LiveLLMEngine()
        # When no API key is provided, infer should gracefully fall back to mock
        res = live_engine.infer("Give process 4 more CPU time")
        self.assertEqual(res["pid"], 4)
        self.assertEqual(res["weight"], 3)
        self.assertIn("fallback", res["reason"])


if __name__ == "__main__":
    unittest.main()
