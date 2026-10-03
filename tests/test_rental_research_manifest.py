"""Regression coverage for the 47-family rental-research expansion.

The JSON manifest is deliberately an operator-facing artifact rather than
application input.  These tests make it auditable: every supplied reference
must have one outcome, every active target must exist in the same central tree
used by Create/Edit/Explore, and every source wording alias must reach Search
and Finder without a per-product route rule.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import unittest

from app.catalog_taxonomy import CATEGORY_TREE, taxonomy_label, taxonomy_path_aliases
from app.finder_service import _static_catalog_concepts
from app.rental_research_aliases import RESEARCH_PATH_ALIASES
from app.routes_search import _taxonomy_search_values


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "docs" / "rental_research_coverage_2026-10-03.json"
INVENTORY_PATH = REPOSITORY_ROOT / "docs" / "rental_research_expanded_inventory_2026-10-03.json"

# Exact cardinalities supplied in the research brief.  Keeping this separate
# from the JSON catches a missing or duplicated source reference even when a
# total happens to remain 333.
REFERENCE_COUNTS = {
    "R01": 8, "R02": 4, "R03": 6, "R04": 6, "R05": 8, "R06": 2,
    "R07": 6, "R08": 1, "R09": 1, "R10": 3, "R11": 1, "R12": 3,
    "R13": 16, "R14": 13, "R15": 10, "R16": 10, "R17": 5, "R18": 10,
    "R19": 15, "R20": 10, "R21": 13, "R22": 10, "R23": 6, "R24": 12,
    "R25": 7, "R26": 8, "R27": 9, "R28": 14, "R29": 9, "R30": 6,
    "R31": 6, "R32": 7, "R33": 8, "R34": 5, "R35": 3, "R36": 10,
    "R37": 11, "R38": 4, "R39": 8, "R40": 2, "R41": 5, "R42": 9,
    "R43": 7, "R44": 7, "R45": 1, "R46": 4, "R47": 4,
}
ACTIVE_STATUSES = {"ADDED", "EXISTING", "ALIAS_MAPPED"}
ALL_STATUSES = ACTIVE_STATUSES | {
    "KIT_COMPONENT_MAPPED",
    "RENTAL_MODE_MAPPED",
    "REVIEW_REQUIRED",
    "BLOCKED_WITH_REASON",
}


def _load_rows() -> list[dict[str, object]]:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return document["rows"]


def _path(row: dict[str, object]) -> tuple[str, ...]:
    return tuple(
        part.strip()
        for part in str(row["canonical_path"] or "").split("→")
        if part.strip()
    )


class RentalResearchManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = _load_rows()

    def test_every_supplied_reference_has_one_complete_outcome(self) -> None:
        self.assertEqual(sum(REFERENCE_COUNTS.values()), 333)
        self.assertEqual(len(self.rows), 333)

        references = [str(row["source_reference"]) for row in self.rows]
        self.assertEqual(len(references), len(set(references)))
        expected = {
            f"{family}-{number:02d}"
            for family, count in REFERENCE_COUNTS.items()
            for number in range(1, count + 1)
        }
        self.assertEqual(set(references), expected)
        self.assertEqual(
            Counter(reference.split("-", 1)[0] for reference in references),
            Counter(REFERENCE_COUNTS),
        )

        for row in self.rows:
            self.assertIn(row["final_status"], ALL_STATUSES, row)
            self.assertTrue(str(row["source_label"]).strip(), row)
            self.assertTrue(str(row["research_family"]).strip(), row)
            self.assertTrue(list(row["source_urls"]), row)
            self.assertTrue(str(row["reason"]).strip(), row)
            self.assertTrue(str(row["test_reference_or_blocker"]).strip(), row)

    def test_exported_inventory_is_the_current_central_tree(self) -> None:
        """The review JSON must not become a second stale catalog copy."""
        document = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(document["source_of_truth"], "app/catalog_taxonomy.py::CATEGORY_TREE")
        self.assertEqual(document["tree"], CATEGORY_TREE)
        self.assertEqual(
            document["counts"],
            {
                "level1": len(CATEGORY_TREE),
                "level2": sum(len(branches) for branches in CATEGORY_TREE.values()),
                "level3": sum(
                    len(third_levels)
                    for branches in CATEGORY_TREE.values()
                    for third_levels in branches.values()
                ),
            },
        )

    def test_active_manifest_paths_resolve(self) -> None:
        """A report row is not accepted unless its runtime target exists."""
        mapped_rows = [row for row in self.rows if row["final_status"] != "REVIEW_REQUIRED"]
        self.assertTrue(mapped_rows)
        for row in mapped_rows:
            path = _path(row)
            self.assertIn(len(path), {2, 3}, row)
            category, subcategory = path[:2]
            self.assertIn(category, CATEGORY_TREE, row)
            self.assertIn(subcategory, CATEGORY_TREE[category], row)
            if len(path) == 3:
                self.assertIn(path[2], CATEGORY_TREE[category][subcategory], row)
                self.assertEqual(row["actual_level"], "third_level", row)
            else:
                self.assertEqual(row["actual_level"], "subcategory", row)
            for value in path:
                self.assertTrue(taxonomy_label(value, "fr"), row)
                self.assertTrue(taxonomy_label(value, "ar"), row)

        gated_rows = [row for row in self.rows if row["final_status"] == "REVIEW_REQUIRED"]
        self.assertTrue(gated_rows)
        for row in gated_rows:
            self.assertEqual(row["activation_state"], "review_required_not_active", row)
            self.assertIsNone(row["actual_level"], row)
            self.assertIn("review", str(row["test_reference_or_blocker"]).casefold(), row)

    def test_source_aliases_are_central_and_reach_search_and_finder(self) -> None:
        """All non-canonical source wording resolves without route-specific lists."""
        expected: dict[tuple[str, ...], set[str]] = defaultdict(set)
        for row in self.rows:
            if row["activation_state"] != "active" or row["final_status"] not in ACTIVE_STATUSES:
                continue
            path = _path(row)
            if len(path) not in {2, 3}:
                continue
            source_label = str(row["source_label"]).strip()
            if source_label.casefold() != path[-1].casefold():
                expected[path].add(source_label)

        self.assertEqual(set(RESEARCH_PATH_ALIASES), set(expected))
        for path, aliases in expected.items():
            self.assertEqual(set(RESEARCH_PATH_ALIASES[path]), aliases, path)
            self.assertEqual(set(taxonomy_path_aliases(*path)), aliases, path)
            for alias in aliases:
                self.assertIn(path[-1], _taxonomy_search_values(alias), (path, alias))

        concepts = _static_catalog_concepts()
        for path, aliases in expected.items():
            if len(path) == 2:
                candidates = [
                    concept
                    for concept in concepts
                    if concept.kind == "subcategory"
                    and (concept.category, concept.subcategory) == path
                ]
            else:
                candidates = [
                    concept
                    for concept in concepts
                    if concept.kind == "service"
                    and (concept.category, concept.subcategory, concept.service) == path
                ]
            self.assertTrue(candidates, path)
            discovered = {alias for concept in candidates for alias in concept.aliases}
            self.assertTrue(aliases.issubset(discovered), path)


if __name__ == "__main__":
    unittest.main()
