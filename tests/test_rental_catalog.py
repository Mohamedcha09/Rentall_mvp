"""Topology and translation regression checks for the rental catalog.

These are deliberately data-level tests.  Route-flow coverage exercises the
same definitions after they are connected to the persisted category lookup
tables; this module protects the source catalog from accidental node loss,
orphaned branches, a fourth level, or locale-specific identities.
"""
from __future__ import annotations

import unittest

from app.rental_catalog import (
    OTHER,
    RENTAL_CATEGORIES,
    RENTAL_CATEGORY_TREE,
    canonical_rental_category,
    iter_rental_catalog_rows,
    rental_seed_rows,
)


class RentalCatalogTopologyTests(unittest.TestCase):
    def test_catalog_has_stable_three_level_or_shallower_paths(self):
        """Every active node has labels, a parent, and no invalid duplicates."""
        category_names: set[str] = set()
        paths: set[tuple[str, str, str | None]] = set()

        for category in RENTAL_CATEGORIES:
            category_name = category.value.canonical
            self.assertTrue(category_name)
            self.assertLessEqual(len(category_name), 50)
            self.assertNotIn(category_name, category_names)
            category_names.add(category_name)
            self._assert_value_has_all_labels(category.value)

            branch_names: set[str] = set()
            self.assertTrue(category.branches, category_name)
            for branch in category.branches:
                branch_name = branch.value.canonical
                self.assertTrue(branch_name)
                self.assertNotIn(branch_name, branch_names)
                branch_names.add(branch_name)
                self._assert_value_has_all_labels(branch.value)

                third_names = [child.canonical for child in branch.third_levels]
                self.assertEqual(len(third_names), len(set(third_names)))
                if third_names:
                    # An explicit parent-scoped Other is valid only when the
                    # branch has useful sibling choices; it is not a fake L3.
                    self.assertGreater(len(third_names), 1)
                    self.assertEqual(third_names[-1], OTHER.canonical)
                for third in branch.third_levels:
                    self._assert_value_has_all_labels(third)
                    path = (category_name, branch_name, third.canonical)
                    self.assertNotIn(path, paths)
                    paths.add(path)

                if not branch.third_levels:
                    path = (category_name, branch_name, None)
                    self.assertNotIn(path, paths)
                    paths.add(path)

        self.assertIn("Vehicles", category_names)
        self.assertIn("Food & Concession Equipment", category_names)
        self.assertIn("Marine & Watercraft", category_names)
        self.assertIn("Temporary Infrastructure & Site Services", category_names)

    def test_representative_two_and_three_level_paths_are_preserved(self):
        """The requested real rental families have their intended depth."""
        self.assertEqual(
            RENTAL_CATEGORY_TREE["Vehicles"]["Buses"],
            (
                "School Buses",
                "City / Transit Buses",
                "Shuttle Buses",
                "Minibuses",
                "Coach / Tour Buses",
                "Party Buses",
                "Other",
            ),
        )
        self.assertIn(
            "Popcorn Machines",
            RENTAL_CATEGORY_TREE["Food & Concession Equipment"]["Popcorn Equipment"],
        )
        self.assertEqual(
            RENTAL_CATEGORY_TREE["Housing & Stays"]["Parking & Storage"],
            (),
        )

        configured_rows = set(iter_rental_catalog_rows())
        self.assertIn(("Vehicles", "Buses", "School Buses"), configured_rows)
        self.assertIn(
            ("Food & Concession Equipment", "Popcorn Equipment", "Popcorn Machines"),
            configured_rows,
        )
        self.assertIn(("Housing & Stays", "Parking & Storage", None), configured_rows)

    def test_aliases_keep_legacy_identities_without_rewriting_listings(self):
        """Legacy persisted category spellings resolve to one catalog parent."""
        self.assertEqual(canonical_rental_category("vehicle"), "Vehicles")
        self.assertEqual(canonical_rental_category("housing"), "Housing & Stays")
        self.assertEqual(canonical_rental_category("Sports Equipment"), "Sports & Outdoors")
        self.assertEqual(canonical_rental_category("Digital Accounts"), "Digital Accounts")
        self.assertEqual(canonical_rental_category("Unconfigured Legacy Value"), "Unconfigured Legacy Value")

    def test_seed_rows_cover_each_l1_l2_and_do_not_persist_l3_as_lookup_rows(self):
        """The migration seed contract is L1/L2 only; L3 remains centralized code."""
        seed_rows = rental_seed_rows()
        self.assertEqual({row[0] for row in seed_rows}, set(RENTAL_CATEGORY_TREE))
        self.assertEqual(len(seed_rows), len(RENTAL_CATEGORY_TREE))

        by_category = {category: (aliases, subcategories) for category, aliases, subcategories in seed_rows}
        self.assertIn("vehicle", by_category["Vehicles"][0])
        self.assertIn("Buses", by_category["Vehicles"][1])
        self.assertIn("Popcorn Equipment", by_category["Food & Concession Equipment"][1])
        self.assertNotIn("School Buses", by_category["Vehicles"][1])
        self.assertNotIn("Popcorn Machines", by_category["Food & Concession Equipment"][1])

    def _assert_value_has_all_labels(self, value) -> None:
        labels = value.labels()
        self.assertEqual(labels["en"], value.canonical)
        self.assertTrue(labels["fr"], value.canonical)
        self.assertTrue(labels["ar"], value.canonical)


if __name__ == "__main__":
    unittest.main()
