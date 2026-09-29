"""Guardrails for the saved, independent Sevor Finder evaluation corpus.

The Finder application never reads this file.  Keeping it separate prevents a
future router from special-casing its wording just to make a score look good.
Functional assertions against the real HTTP/service flow live in
``tests.test_finder``.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest


CORPUS_PATH = Path(__file__).parent / "fixtures" / "finder_quality_evaluation.json"


class FinderQualityCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with CORPUS_PATH.open(encoding="utf-8") as stream:
            cls.corpus = json.load(stream)

    def test_minimum_case_count_unique_ids_and_independent_holdout(self) -> None:
        cases = self.corpus["single_turn_cases"]
        dialogues = self.corpus["multi_turn_dialogues"]
        self.assertGreaterEqual(len(cases), 120)
        self.assertGreaterEqual(len(dialogues), 20)
        all_ids = [row["id"] for row in cases] + [row["id"] for row in dialogues]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        holdout = [row for row in cases if row.get("split") == "holdout"]
        self.assertGreaterEqual(len(holdout), 24)
        self.assertTrue(all(row["expected"]["focus"] for row in holdout))

    def test_languages_catalog_breadth_and_search_safety_are_present(self) -> None:
        cases = self.corpus["single_turn_cases"]
        self.assertTrue({"ar", "fr", "en", "mixed"}.issubset({row["language"] for row in cases}))
        text = "\n".join(row["text"].casefold() for row in cases)
        # These are coverage signals, not production category allow-lists.
        for options in (
            ("honda",), ("camera", "caméra", "كاميرا"), ("bus", "حافلة"),
            ("apartment", "appartement", "شقة"), ("rug", "tapis", "سجادة"),
            ("chair", "chaise", "كرسي"), ("shoe", "sneaker", "chaussure", "حذاء"),
            ("dress", "robe", "فستان"), ("tent", "tente", "خيمة"), ("other",),
        ):
            self.assertTrue(any(term in text for term in options), options)
        focus = {topic for row in cases for topic in row["expected"]["focus"]}
        self.assertIn("prompt injection treated as data", focus)
        self.assertIn("hard budget", focus)
        self.assertIn("RAM distinction", focus)
        self.assertIn("explicit attribute", focus)

    def test_dialogues_cover_state_updates_pagination_and_support_boundary(self) -> None:
        turns = [turn["user"] for dialogue in self.corpus["multi_turn_dialogues"] for turn in dialogue["turns"]]
        self.assertGreaterEqual(len(turns), 55)
        expected = "\n".join(" ".join(dialogue["expected"]) for dialogue in self.corpus["multi_turn_dialogues"]).casefold()
        for required in ("budget", "pagination", "support", "mixed-language", "availability"):
            self.assertIn(required, expected)
        self.assertIn("compare", "\n".join(turns).casefold())
        self.assertTrue(all(len(dialogue["turns"]) >= 2 for dialogue in self.corpus["multi_turn_dialogues"]))


if __name__ == "__main__":
    unittest.main()
