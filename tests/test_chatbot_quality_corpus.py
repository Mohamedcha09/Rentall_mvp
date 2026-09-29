"""Structural guardrails for the held-out Sevor AI quality corpus.

This does not call the chatbot or a provider. Endpoint-level evaluation should be
run separately with isolated users; this test prevents accidental loss of the
coverage and anti-hallucination cases recorded in the fixture.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


CORPUS_PATH = Path(__file__).parent / "fixtures" / "chatbot_quality_evaluation.json"


class ChatbotQualityCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with CORPUS_PATH.open(encoding="utf-8") as corpus_file:
            cls.corpus = json.load(corpus_file)

    def test_minimum_case_counts_and_unique_ids(self) -> None:
        single_turn = self.corpus["single_turn_cases"]
        dialogues = self.corpus["multi_turn_dialogues"]
        self.assertGreaterEqual(len(single_turn), 120)
        self.assertGreaterEqual(len(dialogues), 20)

        ids = [case["id"] for case in single_turn] + [dialogue["id"] for dialogue in dialogues]
        self.assertEqual(len(ids), len(set(ids)))

    def test_corpus_covers_required_languages_and_safe_routes(self) -> None:
        cases = self.corpus["single_turn_cases"]
        languages = {case["language"] for case in cases}
        self.assertTrue({"ar", "fr", "en", "mixed"}.issubset(languages))

        routes = {case["expected"]["route"] for case in cases}
        self.assertTrue(
            {
                "safe_tool",
                "handoff",
                "unknown_policy_or_handoff",
                "privacy_safe_limit",
                "security_refusal",
                "sensitive_data_safety",
            }.issubset(routes)
        )

    def test_dialogues_exercise_follow_up_context(self) -> None:
        dialogue_routes = {
            turn.get("expected", {}).get("route")
            for dialogue in self.corpus["multi_turn_dialogues"]
            for turn in dialogue["turns"]
        }
        self.assertIn("follow_up_context", dialogue_routes)
        self.assertIn("handoff", dialogue_routes)
        self.assertIn("safe_tool", dialogue_routes)


if __name__ == "__main__":
    unittest.main()
