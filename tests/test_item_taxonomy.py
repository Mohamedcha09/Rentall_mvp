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
    taxonomy_label,
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
            "Hosting & Developer", "VPN & Security", "Regional TV & Entertainment", "General Subscriptions", "Other",
        }
        self.assertEqual(set(DIGITAL_ACCOUNTS_SERVICES), expected_types)
        self.assertIs(CATEGORY_TREE[DIGITAL_ACCOUNTS_CATEGORY], DIGITAL_ACCOUNTS_SERVICES)
        for service_list in DIGITAL_ACCOUNTS_SERVICES.values():
            self.assertIn(OTHER_VALUE, service_list)

        # Representative services ensure easily confused Amazon offerings stay
        # in their intended type rather than becoming one generic service.
        self.assertIn("Amazon Prime Video", DIGITAL_ACCOUNTS_SERVICES["Movies & Streaming"])
        self.assertIn("Amazon Prime", DIGITAL_ACCOUNTS_SERVICES["General Subscriptions"])
        self.assertIn("Amazon Music Unlimited", DIGITAL_ACCOUNTS_SERVICES["Music & Audio"])
        self.assertIn("Amazon Luna", DIGITAL_ACCOUNTS_SERVICES["Gaming"])
        self.assertIn("Audible", DIGITAL_ACCOUNTS_SERVICES["News & Reading"])
        self.assertIn("Kindle Unlimited", DIGITAL_ACCOUNTS_SERVICES["News & Reading"])
        self.assertIn("beIN Sports", DIGITAL_ACCOUNTS_SERVICES["Sports"])
        self.assertIn("ChatGPT", DIGITAL_ACCOUNTS_SERVICES["AI Tools"])
        self.assertIn("Epic Games / Fortnite", DIGITAL_ACCOUNTS_SERVICES["Gaming"])
        self.assertIn(
            "BBC-related paid services where available",
            DIGITAL_ACCOUNTS_SERVICES["Movies & Streaming"],
        )
        self.assertIn("Character.AI paid plans", DIGITAL_ACCOUNTS_SERVICES["AI Tools"])
        self.assertIn("Zee5", DIGITAL_ACCOUNTS_SERVICES["Regional TV & Entertainment"])

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
        self.assertEqual(baby["name"], "Baby & Kids")
        self.assertEqual(baby["label"], "الأطفال والرضع")
        self.assertEqual(baby["subcategories"][0]["third_levels"], [])
        self.assertEqual(digital["label"], "الحسابات الرقمية")
        self.assertIn("beIN Sports", [row["name"] for row in digital["subcategories"][0]["third_levels"]])
        self.assertEqual(digital["level2_placeholder"], "اختر النوع الرقمي")
        self.assertEqual(digital["level3_select_placeholder"], "اختر الخدمة / المنصة")

    def test_generic_taxonomy_concepts_translate_without_changing_internal_values(self):
        """FR/AR labels must never create locale-specific database values."""
        categories = [SimpleNamespace(id=1, name=DIGITAL_ACCOUNTS_CATEGORY)]
        subcategories = [
            SimpleNamespace(id=11, category_id=1, name="Movies & Streaming"),
            SimpleNamespace(id=12, category_id=1, name="Sports"),
            SimpleNamespace(id=13, category_id=1, name="Gaming"),
        ]
        french = catalog_tree_payload(categories, subcategories, "fr")["categories"][0]
        arabic = catalog_tree_payload(categories, subcategories, "ar")["categories"][0]
        french_by_name = {row["name"]: row["label"] for row in french["subcategories"]}
        arabic_by_name = {row["name"]: row["label"] for row in arabic["subcategories"]}

        self.assertEqual(french["name"], DIGITAL_ACCOUNTS_CATEGORY)
        self.assertEqual(arabic["name"], DIGITAL_ACCOUNTS_CATEGORY)
        self.assertEqual(french_by_name["Movies & Streaming"], "Films et streaming")
        self.assertEqual(arabic_by_name["Sports"], "الرياضة")
        self.assertEqual(arabic_by_name["Gaming"], "ألعاب الفيديو")
        # Brands are identifiers/presentation names, not translated concepts.
        self.assertEqual(taxonomy_label("beIN Sports", "fr"), "beIN Sports")
        self.assertEqual(taxonomy_label("Netflix", "ar"), "Netflix")

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
        self.assertEqual(category["level3_select_placeholder"], "Select type")
        self.assertEqual(
            [row["name"] for row in category["subcategories"][0]["third_levels"]],
            ["Lift Pass", OTHER_VALUE],
        )

    def test_create_payload_exposes_every_configured_path_in_every_supported_language(self):
        """The actual Create-form payload must not omit a configured node.

        The HTML form serializes this exact server-produced payload.  Build
        lookup-like rows for the entire central tree and compare every L1/L2/L3
        value in English, French, and Arabic so a future catalog expansion
        cannot land only in Explore or only in the validator.
        """
        categories = []
        subcategories = []
        next_category_id = 1
        next_subcategory_id = 1000
        for category_name, branches in CATEGORY_TREE.items():
            category_id = next_category_id
            next_category_id += 1
            categories.append(SimpleNamespace(id=category_id, name=category_name))
            for subcategory_name in branches:
                subcategories.append(
                    SimpleNamespace(
                        id=next_subcategory_id,
                        category_id=category_id,
                        name=subcategory_name,
                    )
                )
                next_subcategory_id += 1

        expected_category_names = set(CATEGORY_TREE)
        expected_subcategory_count = sum(len(branches) for branches in CATEGORY_TREE.values())
        expected_third_level_count = sum(
            len(third_levels)
            for branches in CATEGORY_TREE.values()
            for third_levels in branches.values()
        )

        for language in ("en", "fr", "ar"):
            payload = catalog_tree_payload(categories, subcategories, language)
            for copy_key in (
                "choose_category",
                "choose_subcategory",
                "choose_type",
                "enter_custom_type",
            ):
                self.assertTrue(payload["labels"][copy_key])
            by_category = {category["name"]: category for category in payload["categories"]}
            self.assertEqual(set(by_category), expected_category_names)
            self.assertEqual(
                sum(len(category["subcategories"]) for category in payload["categories"]),
                expected_subcategory_count,
            )
            self.assertEqual(
                sum(
                    len(subcategory["third_levels"])
                    for category in payload["categories"]
                    for subcategory in category["subcategories"]
                ),
                expected_third_level_count,
            )
            for category_name, branches in CATEGORY_TREE.items():
                payload_branches = {
                    branch["name"]: branch
                    for branch in by_category[category_name]["subcategories"]
                }
                self.assertEqual(set(payload_branches), set(branches))
                for subcategory_name, expected_third_levels in branches.items():
                    self.assertEqual(
                        [level["name"] for level in payload_branches[subcategory_name]["third_levels"]],
                        list(expected_third_levels),
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
from io import BytesIO
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
from app.catalog_taxonomy import CATEGORY_TREE, OTHER_VALUE, TaxonomyValidationError, resolve_listing_hierarchy
import app.items as item_routes

# Listing-index work is covered independently.  This isolates the real form
# handlers' taxonomy persistence from Finder's public-listing lifecycle.
item_routes.sync_listing_index = lambda *_args, **_kwargs: None
item_routes.cloudinary.uploader.upload = lambda *_args, **_kwargs: {"secure_url": "https://example.test/taxonomy.png"}

class Request:
    session = {"user": {"id": 41, "role": "user", "status": "approved"}}

db = SessionLocal()
try:
    digital = Category(name="Digital Accounts")
    baby = Category(name="Baby & Kids")
    vehicles = Category(name="Vehicles")
    legacy_vehicle = Category(name="vehicle")
    food = Category(name="Food & Concession Equipment")
    housing = Category(name="Housing & Stays")
    db.add_all([digital, baby, vehicles, legacy_vehicle, food, housing])
    db.flush()
    sports = Subcategory(category_id=digital.id, name="Sports")
    movies = Subcategory(category_id=digital.id, name="Movies & Streaming")
    seats = Subcategory(category_id=baby.id, name="Car Seats")
    buses = Subcategory(category_id=vehicles.id, name="Buses")
    cars = Subcategory(category_id=vehicles.id, name="Cars")
    legacy_vehicle_cars = Subcategory(category_id=legacy_vehicle.id, name="Cars")
    popcorn = Subcategory(category_id=food.id, name="Popcorn Equipment")
    parking = Subcategory(category_id=housing.id, name="Parking & Storage")
    db.add_all([sports, movies, seats, buses, cars, legacy_vehicle_cars, popcorn, parking])
    db.commit()

    # The old lookup parent can remain as the alias `vehicle`, while newer
    # L2 choices are attached to it.  A title-only edit of an L1-only item
    # must remain possible without inventing a Cars/L3 classification.
    legacy_l1 = resolve_listing_hierarchy(
        db,
        category_name="vehicle",
        subcategory_id=None,
        third_level="",
        custom_third_level="",
        legacy_blank_path=("vehicle", None),
    )
    assert legacy_l1 == {
        "category": "vehicle", "subcategory": None,
        "third_level": None, "custom_third_level": None,
    }

    # Expand the isolated lookup rows to the complete central tree.  This is
    # intentionally data-driven: a future category/branch added to the
    # catalog must be accepted by the same resolver that the POST handler
    # uses, without adding a special test branch or route condition.
    all_subcategory_ids = {}
    for category_name, branches in CATEGORY_TREE.items():
        category = db.query(Category).filter(Category.name == category_name).first()
        if category is None:
            category = Category(name=category_name)
            db.add(category)
            db.flush()
        for subcategory_name in branches:
            subcategory = (
                db.query(Subcategory)
                .filter(
                    Subcategory.category_id == category.id,
                    Subcategory.name == subcategory_name,
                )
                .first()
            )
            if subcategory is None:
                subcategory = Subcategory(category_id=category.id, name=subcategory_name)
                db.add(subcategory)
                db.flush()
            all_subcategory_ids[(category_name, subcategory_name)] = subcategory.id
    db.commit()

    two_level_paths = 0
    third_level_values = 0
    for category_name, branches in CATEGORY_TREE.items():
        for subcategory_name, third_levels in branches.items():
            subcategory_id = all_subcategory_ids[(category_name, subcategory_name)]
            if not third_levels:
                resolved = resolve_listing_hierarchy(
                    db,
                    category_name=category_name,
                    subcategory_id=subcategory_id,
                    third_level="",
                    custom_third_level="",
                )
                assert resolved == {
                    "category": category_name,
                    "subcategory": subcategory_name,
                    "third_level": None,
                    "custom_third_level": None,
                }
                two_level_paths += 1
                continue
            for third_level in third_levels:
                custom_name = "Catalog-specific other" if third_level == OTHER_VALUE else ""
                resolved = resolve_listing_hierarchy(
                    db,
                    category_name=category_name,
                    subcategory_id=subcategory_id,
                    third_level=third_level,
                    custom_third_level=custom_name,
                )
                assert resolved == {
                    "category": category_name,
                    "subcategory": subcategory_name,
                    "third_level": third_level,
                    "custom_third_level": custom_name or None,
                }
                third_level_values += 1
    # The research expansion deliberately keeps ordinary two-level branches
    # intact while adding active, parent-scoped type choices where they are
    # useful.  These totals make a dropped branch or an accidental duplicate
    # visible to the generic resolver test rather than testing only a sample.
    assert two_level_paths == 19
    assert third_level_values == 951

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

    school_bus = resolve_listing_hierarchy(
        db, category_name="Vehicles", subcategory_id=buses.id,
        third_level="School Buses", custom_third_level="",
    )
    assert school_bus == {
        "category": "Vehicles", "subcategory": "Buses",
        "third_level": "School Buses", "custom_third_level": None,
    }

    popcorn_machine = resolve_listing_hierarchy(
        db, category_name="Food & Concession Equipment", subcategory_id=popcorn.id,
        third_level="Popcorn Machines", custom_third_level="",
    )
    assert popcorn_machine["third_level"] == "Popcorn Machines"

    equipment_other = resolve_listing_hierarchy(
        db, category_name="Food & Concession Equipment", subcategory_id=popcorn.id,
        third_level="Other", custom_third_level="Vintage Popcorn Cart",
    )
    assert equipment_other["custom_third_level"] == "Vintage Popcorn Cart"

    new_two_level = resolve_listing_hierarchy(
        db, category_name="Housing & Stays", subcategory_id=parking.id,
        third_level="", custom_third_level="",
    )
    assert new_two_level == {
        "category": "Housing & Stays", "subcategory": "Parking & Storage",
        "third_level": None, "custom_third_level": None,
    }

    # A browser may send an accepted legacy L1 alias even when the lookup
    # table has only its canonical parent.  New paths must persist the lookup
    # value, not the caller-controlled alias spelling.
    normalized_alias = resolve_listing_hierarchy(
        db, category_name="housing", subcategory_id=parking.id,
        third_level="", custom_third_level="",
    )
    assert normalized_alias == {
        "category": "Housing & Stays", "subcategory": "Parking & Storage",
        "third_level": None, "custom_third_level": None,
    }

    # Cars gained useful L3 types after older listings already existed.  The
    # resolver must preserve an unchanged legacy two-level path rather than
    # guessing a vehicle type or making the edit impossible.
    legacy_cars = resolve_listing_hierarchy(
        db, category_name="Vehicles", subcategory_id=cars.id,
        third_level="", custom_third_level="",
        legacy_blank_path=("Vehicles", "Cars"),
    )
    assert legacy_cars == {
        "category": "Vehicles", "subcategory": "Cars",
        "third_level": None, "custom_third_level": None,
    }

    for kwargs in (
        dict(category_name="Digital Accounts", subcategory_id=seats.id, third_level="beIN Sports", custom_third_level=""),
        dict(category_name="Digital Accounts", subcategory_id=sports.id, third_level="Netflix", custom_third_level=""),
        dict(category_name="Baby & Kids", subcategory_id=seats.id, third_level="beIN Sports", custom_third_level=""),
        dict(category_name="Digital Accounts", subcategory_id=movies.id, third_level="Other", custom_third_level=""),
        dict(category_name="Vehicles", subcategory_id=buses.id, third_level="", custom_third_level=""),
        dict(category_name="Food & Concession Equipment", subcategory_id=popcorn.id, third_level="School Buses", custom_third_level=""),
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
        images=[type("TestImage", (), {"filename": "taxonomy.png", "file": BytesIO(b"png")})()],
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

    # This is an existing listing, not a new create.  Editing only its title
    # through the real POST handler must leave the newly-expanded Cars branch
    # untyped until its owner deliberately chooses a vehicle type.
    legacy_item = item_routes.Item(
        owner_id=41,
        title="Legacy car",
        description="Created before Cars acquired L3 types",
        city="Montréal",
        currency="CAD",
        price=10,
        price_per_day=10,
        category="Vehicles",
        subcategory="Cars",
        status="approved",
        is_active="yes",
    )
    db.add(legacy_item)
    db.commit()
    item_routes.item_edit_post(
        Request(), legacy_item.id, db,
        title="Legacy car updated",
        category="Vehicles",
        subcategory_id=cars.id,
        third_level="",
        custom_third_level="",
        description="Only title changed",
        city="Montréal",
        website_url="",
        no_website=True,
        price="10",
        currency="CAD",
        images=None,
        latitude="",
        longitude="",
    )
    db.refresh(legacy_item)
    assert (legacy_item.category, legacy_item.subcategory, legacy_item.third_level, legacy_item.custom_third_level) == (
        "Vehicles", "Cars", None, None,
    )

    legacy_l1_item = item_routes.Item(
        owner_id=41,
        title="Legacy vehicle",
        description="Created before this category gained subcategories",
        city="Montréal",
        currency="CAD",
        price=10,
        price_per_day=10,
        category="vehicle",
        subcategory=None,
        status="approved",
        is_active="yes",
    )
    db.add(legacy_l1_item)
    db.commit()
    item_routes.item_edit_post(
        Request(), legacy_l1_item.id, db,
        title="Legacy vehicle updated",
        category="vehicle",
        subcategory_id=None,
        third_level="",
        custom_third_level="",
        description="Only title changed",
        city="Montréal",
        website_url="",
        no_website=True,
        price="10",
        currency="CAD",
        images=None,
        latitude="",
        longitude="",
    )
    db.refresh(legacy_l1_item)
    assert (legacy_l1_item.category, legacy_l1_item.subcategory, legacy_l1_item.third_level, legacy_l1_item.custom_third_level) == (
        "vehicle", None, None, None,
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
    def test_rendered_taxonomy_routes_cover_empty_explore_create_edit_and_admin(self):
        """Exercise real rendered routes and Jinja templates, not helpers.

        The lookup tables intentionally start with no Digital Accounts rows.
        All surfaces must consistently omit that unseeded branch rather than
        rendering a browse-only choice that Create cannot validate. The same
        isolated database is then seeded to prove the database-backed create,
        edit and admin pages render all hierarchy shapes without using a real
        developer or production database.
        """
        with tempfile.TemporaryDirectory(prefix="sevor-explore-taxonomy-") as temp_dir:
            database_path = Path(temp_dir) / "explore.sqlite3"
            script = r'''
import os
import sqlite3
import sys
from pathlib import Path

site_packages = os.environ.get("SEVOR_TEST_SITE_PACKAGES", "")
if site_packages:
    sys.path.insert(0, site_packages)

path = Path(os.environ["EXPLORE_TAXONOMY_TEST_DB"])
conn = sqlite3.connect(path)
conn.executescript("""
CREATE TABLE users (
  id INTEGER PRIMARY KEY, first_name VARCHAR(100), last_name VARCHAR(100),
  email VARCHAR(200), phone VARCHAR(50), password_hash VARCHAR(255),
  role VARCHAR(20), status VARCHAR(20), created_at TIMESTAMP, updated_at TIMESTAMP,
  is_verified BOOLEAN, verified_at TIMESTAMP, badge_admin BOOLEAN,
  is_deposit_manager BOOLEAN, is_mod BOOLEAN, is_support BOOLEAN,
  avatar_path VARCHAR(500), account_type VARCHAR(30)
);
CREATE TABLE items (
  id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, title VARCHAR(200) NOT NULL,
  description TEXT, website_url VARCHAR(2048), city VARCHAR(120), currency VARCHAR(3),
  price NUMERIC, status VARCHAR(20), admin_feedback TEXT, reviewed_at TIMESTAMP,
  latitude REAL, longitude REAL, price_per_day INTEGER, category VARCHAR(80),
  subcategory VARCHAR(120), third_level VARCHAR(160),
  custom_third_level VARCHAR(200), image_path VARCHAR(500), is_active VARCHAR(10),
  created_at TIMESTAMP
);
CREATE TABLE categories (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE);
CREATE TABLE subcategories (id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL, name VARCHAR(120) NOT NULL);
""")
conn.commit()
conn.close()

from fastapi.testclient import TestClient
from fastapi import Request
import app.main as main_module
from app.database import SessionLocal
from app.models import Category, Item, Subcategory, User

# Keep the route test offline and deterministic.
main_module._fx_schedule_daily_sync = lambda: None

@main_module.app.get("/_test_taxonomy_login/{role}")
def _test_taxonomy_login(role: str, request: Request):
    request.session["user"] = {"id": 901, "role": role, "status": "approved"}
    return {"ok": True}

db = SessionLocal()
try:
    assert db.query(Category).filter(Category.name == "Digital Accounts").count() == 0
finally:
    db.close()

with TestClient(main_module.app) as client:
    root = client.get("/items")
    assert root.status_code == 200, root.text[:1000]
    assert "Digital Accounts" not in root.text

    # Seed only the isolated test DB, then exercise the actual create/edit and
    # admin HTML routes.  This mirrors the result of the additive migration;
    # it does not write the developer's app.db.
    db = SessionLocal()
    try:
        owner = User(
            id=901, first_name="Taxonomy", last_name="Owner",
            email="taxonomy-owner@example.test", phone="1", password_hash="x",
            role="user", status="approved",
        )
        digital = Category(name="Digital Accounts")
        baby = Category(name="Baby & Kids")
        db.add_all([owner, digital, baby])
        db.flush()
        sports_type = Subcategory(category_id=digital.id, name="Sports")
        movies_type = Subcategory(category_id=digital.id, name="Movies & Streaming")
        seats = Subcategory(category_id=baby.id, name="Car Seats")
        db.add_all([sports_type, movies_type, seats])
        db.add_all([
            Item(
                id=900, owner_id=owner.id, title="Pending sports access", city="Montréal",
                currency="CAD", price=10, price_per_day=10,
                category="Digital Accounts", subcategory="Sports",
                third_level="beIN Sports", status="pending", is_active="yes",
            ),
            Item(
                id=904, owner_id=owner.id, title="Published sports access", city="Montréal",
                currency="CAD", price=10, price_per_day=10,
                category="Digital Accounts", subcategory="Sports",
                third_level="beIN Sports", status="approved", is_active="yes",
            ),
            Item(
                id=902, owner_id=owner.id, title="Car seat", city="Montréal",
                currency="CAD", price=10, price_per_day=10,
                category="Baby & Kids", subcategory="Car Seats",
                status="pending", is_active="yes",
            ),
            Item(
                id=903, owner_id=owner.id, title="Custom streaming access", city="Montréal",
                currency="CAD", price=10, price_per_day=10,
                category="Digital Accounts", subcategory="Movies & Streaming",
                third_level="Other", custom_third_level="NewStreamingPlatform",
                status="pending", is_active="yes",
            ),
        ])
        db.commit()
    finally:
        db.close()

    assert client.get("/_test_taxonomy_login/user").status_code == 200
    create = client.get("/owner/items/new")
    assert create.status_code == 200, create.text[:1000]
    assert "Digital Accounts" in create.text
    assert "beIN Sports" in create.text
    assert "Car Seats" in create.text

    edit = client.get("/owner/items/900/edit")
    assert edit.status_code == 200, edit.text[:1000]
    assert "thirdLevelSelect" in edit.text
    assert "beIN Sports" in edit.text

    filtered = client.get(
        "/items?category=Digital%20Accounts&sub=Sports&service=beIN%20Sports"
    )
    assert filtered.status_code == 200, filtered.text[:1000]
    assert "Published sports access" in filtered.text, filtered.text[:4000]
    assert "Custom streaming access" not in filtered.text, filtered.text[:4000]

    assert client.get("/_test_taxonomy_login/admin").status_code == 200
    admin = client.get("/admin/items/pending")
    assert admin.status_code == 200, admin.text[:1000]
    for expected in (
        "Digital Accounts", "Sports", "beIN Sports", "Baby &amp; Kids",
        "Car Seats", "NewStreamingPlatform", "Service / Platform",
        "/admin/items/900/approve", "/admin/items/900/delete",
    ):
        assert expected in admin.text, expected
'''
            environment = os.environ.copy()
            environment["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
            environment["EXPLORE_TAXONOMY_TEST_DB"] = str(database_path)
            environment["SECRET_KEY"] = "explore-taxonomy-test-only"
            environment["COOKIE_DOMAIN"] = "testserver.local"
            environment["HTTPS_ONLY_COOKIES"] = "0"
            environment["SITE_URL"] = ""
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
            self.assertIn("level3_select_placeholder", template)
            self.assertIn("const selectedValue = select.value", template)
            self.assertIn("const keepSelected = option.value === selectedValue", template)
        self.assertIn("&amp;service=", explore)
        self.assertIn("third_levels", explore)
        self.assertIn("item_hierarchy", detail)
        self.assertIn("it.taxonomy_hierarchy", admin)
        self.assertIn("data-delete-form", admin)
        self.assertIn("min-width: 0", admin)
        self.assertIn("env(safe-area-inset", admin)
        self.assertIn("@media (max-width: 440px)", admin)
        self.assertIn("overflow-x:auto", explore)
        self.assertIn("_taxonomy_search_values", search)
        for field in ("Item.category,", "Item.subcategory,", "Item.third_level,", "Item.custom_third_level,"):
            self.assertIn(field, search)
        self.assertIn("taxonomy_payload['labels']['choose_type']", new_form)
        self.assertIn("taxonomy_payload['labels']['enter_custom_type']", new_form)
        self.assertIn('for="catSelect"', edit_form)
        self.assertIn('for="subSelect"', edit_form)


if __name__ == "__main__":
    unittest.main()
