"""Runtime guardrails for the SEVOR AI quality corpus.

Unlike ``test_chatbot_quality_corpus.py``, these tests execute the actual
``support_ai`` guest service flow and the real context-classification helpers.
They intentionally do not treat a guest response as a successful private-tool
lookup or durable human handoff; those behaviors are covered by the isolated
authenticated endpoint tests in ``test_chatbot_support.py``.
"""

from __future__ import annotations

import unittest

from app.chatbot_evaluation import evaluate_quality_corpus


class ChatbotQualityRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = evaluate_quality_corpus()

    def test_every_single_turn_reaches_the_actual_guest_service_path(self) -> None:
        single = self.result["single_turn"]
        self.assertEqual(single["total"], 128)
        self.assertEqual(single["service_calls_completed"], single["total"])
        self.assertEqual(single["service_call_failures"], [])
        self.assertTrue(all(row["answer_present"] for row in single["observations"]))

    def test_security_and_sensitive_data_cases_do_not_reach_tools_or_a_provider(self) -> None:
        single = self.result["single_turn"]
        by_id = {row["id"]: row for row in single["observations"]}
        for case_id in ("Q116", "Q117", "Q118", "Q119"):
            self.assertEqual(by_id[case_id]["response_mode"], "security_blocked")
            self.assertEqual(by_id[case_id]["tool_names"], [])
            self.assertEqual(by_id[case_id]["provider"], "blocked")
        for case_id in ("Q077", "Q123", "Q124"):
            self.assertEqual(by_id[case_id]["response_mode"], "sensitive_data_safety")

    def test_all_multi_turn_user_turns_exercise_real_context_analysis(self) -> None:
        multi = self.result["multi_turn"]
        self.assertEqual(multi["dialogues"], 20)
        self.assertGreaterEqual(multi["user_turns"], 40)
        self.assertGreaterEqual(multi["follow_up_context_cases"], 5)
        # This is a non-regression floor for the current service behavior;
        # the printed report gives the exact numerator/denominator and makes
        # remaining continuation misses reviewable rather than invisible.
        self.assertGreaterEqual(multi["follow_up_context_signal_matches"], 3)

    def test_report_distinguishes_provider_and_endpoint_limits(self) -> None:
        self.assertIn(self.result["provider_readiness"], {"llm_configured", "knowledge_only_fallback"})
        self.assertFalse(self.result["provider_called"])
        self.assertGreater(self.result["single_turn"]["authenticated_endpoint_cases"], 0)
        self.assertIn("authenticated_endpoint", self.result["limits"])


if __name__ == "__main__":
    unittest.main()
