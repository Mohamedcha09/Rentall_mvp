"""Offline regression checks for SEVOR's dynamic listing hierarchy.

The resolver test uses a separate Python process and an isolated SQLite file.
That is deliberate: ``models.py`` detects schema columns when it imports, so
the assertions exercise the real server-side validator against actual nullable
third-level columns instead of a test-only literal fallback.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from app.catalog_taxonomy import (
    CATEGORY_TREE,
    DIGITAL_ACCOUNTS_CATEGORY,
    DIGITAL_ACCOUNTS_SERVICES,
    OTHER_VALUE,
    catalog_tree_payload,
    listing_hierarchy,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _project_site_packages() -> str:
    """Return the project dependency directory when the venv launcher is stale."""
    for candidate in (
        REPOSITORY_ROOT / "venv" / "Lib" / "site-packages",
        REPOSITORY_ROOT / ".venv" / "Lib" / "site-packages",
    ):
        if candidate.exists():
            return str(candidate)
    return ""


class ItemTaxonomyCatalogTests(unittest.TestCase):
    def test_digital_catalog_is_central_complete_and_every_type_has_other(self):
        expected_types = {
            "Movies & Streaming", "Sports", "Gaming", "Music & Audio", "AI Tools",
            "Software & Productivity", "Design / Photo / Video", "Cloud & Storage",
            "Education", "News & Reading", "Social & Creator", "Business & Marketing",
            "Hosting & Developer", "VPN & Security", "Regional TV & Entertainment", "General", "Other",
        }
        self.assertEqual(set(DIGITAL_ACCOUNTS_SERVICES), expected_types)
        self.assertIs(CATEGORY_TREE[DIGITAL_ACCOUNTS_CATEGORY], DIGITAL_ACCOUNTS_SERVICES)
        for service_list in DIGITAL_ACCOUNTS_SERVICES.values():
            self.assertIn(OTHER_VALUE, service_list)

        # Representative services ensure easily confused Amazon offerings stay
        # in their intended type rather than becoming one generic service.
        self.assertIn("Amazon Prime Video", DIGITAL_ACCOUNTS_SERVICES["Movies & Streaming"])
        self.assertIn("Amazon Prime", DIGITAL_ACCOUNTS_SERVICES["General"])
        self.assertIn("Amazon Music Unlimited", DIGITAL_ACCOUNTS_SERVICES["Music & Audio"])
        self.assertIn("Amazon Luna", DIGITAL_ACCOUNTS_SERVICES["Gaming"])
        self.assertIn("Audible", DIGITAL_ACCOUNTS_SERVICES["News & Reading"])
        self.assertIn("Kindle Unlimited", DIGITAL_ACCOUNTS_SERVICES["News & Reading"])
        self.assertIn("beIN Sports", DIGITAL_ACCOUNTS_SERVICES["Sports"])
        self.assertIn("ChatGPT", DIGITAL_ACCOUNTS_SERVICES["AI Tools"])

    def test_payload_is_two_levels_for_normal_categories_and_three_for_configured_branch(self):
        categories = [
            SimpleNamespace(id=1, name="Baby & Kids"),
            SimpleNamespace(id=2, name=DIGITAL_ACCOUNTS_CATEGORY),
        ]
        subcategories = [
            SimpleNamespace(id=11, category_id=1, name="Car Seats"),
            SimpleNamespace(id=21, category_id=2, name="Sports"),
        ]
        payload = catalog_tree_payload(categories, subcategories, "ar")
        baby, digital = payload["categories"]
        self.assertEqual(baby["label"], "Baby & Kids")
        self.assertEqual(baby["subcategories"][0]["third_levels"], [])
        self.assertEqual(digital["label"], "الحسابات الرقمية")
        self.assertIn("beIN Sports", [row["name"] for row in digital["subcategories"][0]["third_levels"]])
        self.assertEqual(digital["level2_placeholder"], "اختر النوع الرقمي")

    def test_another_configured_three_level_category_uses_generic_type_without_route_code(self):
        categories = [SimpleNamespace(id=30, name="Seasonal Passes")]
        subcategories = [SimpleNamespace(id=301, category_id=30, name="Winter")]
        with patch.dict(
            CATEGORY_TREE,
            {"Seasonal Passes": {"Winter": ("Lift Pass", OTHER_VALUE)}},
            clear=False,
        ):
            payload = catalog_tree_payload(categories, subcategories, "en")
        category = payload["categories"][0]
        self.assertEqual(category["level_labels"]["level2"], "Type")
        self.assertEqual(category["level2_placeholder"], "Select type")
        self.assertEqual(category["level3_placeholder"], "Select a type first")
        self.assertEqual(
            [row["name"] for row in category["subcategories"][0]["third_levels"]],
            ["Lift Pass", OTHER_VALUE],
        )

    def test_display_uses_custom_name_only_for_explicit_other(self):
        item = SimpleNamespace(
            category=DIGITAL_ACCOUNTS_CATEGORY,
            subcategory="Movies & Streaming",
            third_level="Other",
            custom_third_level="NewStreamingPlatform",
        )
        hierarchy = listing_hierarchy(item, "en")
        self.assertEqual(
            [(row["kind"], row["value"]) for row in hierarchy],
            [
                ("Category", DIGITAL_ACCOUNTS_CATEGORY),
                ("Digital Type", "Movies & Streaming"),
                ("Service / Platform", "NewStreamingPlatform"),
            ],
        )


class ItemTaxonomyBackendValidationTests(unittest.TestCase):
    def test_real_resolver_rejects_forged_or_stale_children_and_clears_level_three(self):
        with tempfile.TemporaryDirectory(prefix="sevor-item-taxonomy-") as temp_dir:
            database_path = Path(temp_dir) / "taxonomy.sqlite3"
            script = r'''
import os
import sqlite3
import sys
from pathlib import Path

site_packages = os.environ.get("SEVOR_TEST_SITE_PACKAGES", "")
if site_packages:
    sys.path.insert(0, site_packages)

path = Path(os.environ["TAXONOMY_TEST_DB"])
conn = sqlite3.connect(path)
conn.executescript("""
CREATE TABLE items (
  id INTEGER PRIMARY KEY, owner_id INTEGER, title VARCHAR(200), description TEXT,
  website_url VARCHAR(2048), city VARCHAR(120), currency VARCHAR(3), price NUMERIC,
  status VARCHAR(20), admin_feedback TEXT, reviewed_at DATETIME,
  latitude REAL, longitude REAL, price_per_day INTEGER,
  category VARCHAR(80), subcategory VARCHAR(120), third_level VARCHAR(160),
  custom_third_level VARCHAR(200), image_path VARCHAR(500), is_active VARCHAR(10),
  created_at DATETIME
);
CREATE TABLE users (id INTEGER PRIMARY KEY);
CREATE TABLE categories (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE);
CREATE TABLE subcategories (id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL, name VARCHAR(120) NOT NULL);
""")
conn.commit()
conn.close()

from app.database import SessionLocal
from app.models import Category, Subcategory
from app.catalog_taxonomy import TaxonomyValidationError, resolve_listing_hierarchy
import app.items as item_routes

# Listing-index work is covered independently.  This isolates the real form
# handlers' taxonomy persistence from Finder's public-listing lifecycle.
item_routes.sync_listing_index = lambda *_args, **_kwargs: None

class Request:
    session = {"user": {"id": 41, "role": "user", "status": "approved"}}

db = SessionLocal()
try:
    digital = Category(name="Digital Accounts")
    baby = Category(name="Baby & Kids")
    db.add_all([digital, baby])
    db.flush()
    sports = Subcategory(category_id=digital.id, name="Sports")
    movies = Subcategory(category_id=digital.id, name="Movies & Streaming")
    seats = Subcategory(category_id=baby.id, name="Car Seats")
    db.add_all([sports, movies, seats])
    db.commit()

    normal = resolve_listing_hierarchy(
        db, category_name="Baby & Kids", subcategory_id=seats.id,
        third_level="", custom_third_level="",
    )
    assert normal == {
        "category": "Baby & Kids", "subcategory": "Car Seats",
        "third_level": None, "custom_third_level": None,
    }

    digital_row = resolve_listing_hierarchy(
        db, category_name="Digital Accounts", subcategory_id=sports.id,
        third_level="beIN Sports", custom_third_level="",
    )
    assert digital_row["subcategory"] == "Sports"
    assert digital_row["third_level"] == "beIN Sports"
    assert digital_row["custom_third_level"] is None

    other = resolve_listing_hierarchy(
        db, category_name="Digital Accounts", subcategory_id=movies.id,
        third_level="Other", custom_third_level="NewStreamingPlatform",
    )
    assert other["third_level"] == "Other"
    assert other["custom_third_level"] == "NewStreamingPlatform"

    for kwargs in (
        dict(category_name="Digital Accounts", subcategory_id=seats.id, third_level="beIN Sports", custom_third_level=""),
        dict(category_name="Digital Accounts", subcategory_id=sports.id, third_level="Netflix", custom_third_level=""),
        dict(category_name="Baby & Kids", subcategory_id=seats.id, third_level="beIN Sports", custom_third_level=""),
        dict(category_name="Digital Accounts", subcategory_id=movies.id, third_level="Other", custom_third_level=""),
    ):
        try:
            resolve_listing_hierarchy(db, **kwargs)
        except TaxonomyValidationError:
            pass
        else:
            raise AssertionError(f"forged or incomplete hierarchy accepted: {kwargs}")

    # Exercise the actual create and edit handlers.  A pending digital item
    # first changes Digital Type/Service, then changes to a normal category;
    # both dependent fields must be persisted or cleared atomically.
    item_routes.item_new_post(
        Request(), db,
        subcategory_id=sports.id,
        third_level="beIN Sports",
        custom_third_level="",
        title="Sports account",
        category="Digital Accounts",
        description="Test listing",
        city="Montréal",
        website_url="",
        no_website=True,
        price="10",
        currency="CAD",
        images=[],
        latitude="",
        longitude="",
    )
    created = db.query(item_routes.Item).filter(item_routes.Item.title == "Sports account").one()
    assert (created.category, created.subcategory, created.third_level, created.custom_third_level) == (
        "Digital Accounts", "Sports", "beIN Sports", None,
    )

    item_routes.item_edit_post(
        Request(), created.id, db,
        title="Movie account",
        category="Digital Accounts",
        subcategory_id=movies.id,
        third_level="Netflix",
        custom_third_level="",
        description="Updated test listing",
        city="Montréal",
        website_url="",
        no_website=True,
        price="10",
        currency="CAD",
        images=None,
        latitude="",
        longitude="",
    )
    db.refresh(created)
    assert (created.subcategory, created.third_level, created.custom_third_level) == (
        "Movies & Streaming", "Netflix", None,
    )

    item_routes.item_edit_post(
        Request(), created.id, db,
        title="Car seat",
        category="Baby & Kids",
        subcategory_id=seats.id,
        third_level="",
        custom_third_level="",
        description="Updated test listing",
        city="Montréal",
        website_url="",
        no_website=True,
        price="10",
        currency="CAD",
        images=None,
        latitude="",
        longitude="",
    )
    db.refresh(created)
    assert (created.category, created.subcategory, created.third_level, created.custom_third_level) == (
        "Baby & Kids", "Car Seats", None, None,
    )
finally:
    db.close()
'''
            environment = os.environ.copy()
            environment["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
            environment["TAXONOMY_TEST_DB"] = str(database_path)
            site_packages = _project_site_packages()
            if site_packages:
                environment["SEVOR_TEST_SITE_PACKAGES"] = site_packages
                environment["PYTHONPATH"] = os.pathsep.join(
                    part for part in (site_packages, environment.get("PYTHONPATH", "")) if part
                )
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=REPOSITORY_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


class ItemTaxonomyIntegrationSurfaceTests(unittest.TestCase):
    def test_create_edit_explore_search_detail_and_admin_use_the_shared_hierarchy(self):
        templates = REPOSITORY_ROOT / "app" / "templates"
        new_form = (templates / "items_new.html").read_text(encoding="utf-8")
        edit_form = (templates / "items_edit.html").read_text(encoding="utf-8")
        explore = (templates / "items.html").read_text(encoding="utf-8")
        detail = (templates / "items_detail.html").read_text(encoding="utf-8")
        admin = (templates / "admin_items_pending.html").read_text(encoding="utf-8")
        search = (REPOSITORY_ROOT / "app" / "routes_search.py").read_text(encoding="utf-8")

        for template in (new_form, edit_form):
            self.assertIn("taxonomy_payload | tojson", template)
            self.assertIn('name="third_level"', template)
            self.assertIn('name="custom_third_level"', template)
            self.assertIn("resetThird", template)
            self.assertIn("third_levels", template)
            self.assertIn("level2_placeholder", template)
            self.assertIn("level3_placeholder", template)
        self.assertIn("&amp;service=", explore)
        self.assertIn("third_levels", explore)
        self.assertIn("item_hierarchy", detail)
        self.assertIn("it.taxonomy_hierarchy", admin)
        self.assertIn("data-delete-form", admin)
        self.assertIn("min-width: 0", admin)
        self.assertIn("env(safe-area-inset", admin)
        self.assertIn("@media (max-width: 440px)", admin)
        self.assertIn("overflow-x:auto", explore)
        for field in ("Item.category.ilike(pattern)", "Item.subcategory.ilike(pattern)", "Item.third_level.ilike(pattern)", "Item.custom_third_level.ilike(pattern)"):
            self.assertIn(field, search)


if __name__ == "__main__":
    unittest.main()
