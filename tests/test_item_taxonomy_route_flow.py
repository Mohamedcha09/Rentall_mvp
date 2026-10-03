"""End-to-end regression coverage for the persisted listing taxonomy.

This test intentionally starts from the Alembic revision immediately before
the taxonomy migration.  It proves that the migration seeds the lookup rows
needed by the *real* Create Listing form, then submits the actual HTTP routes
through Create → Pending → Approve → Explore → Details → Edit.  It never uses
the developer database or an external service.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _project_site_packages() -> str:
    """Find dependencies when the checked-in virtualenv launcher is stale."""
    for candidate in (
        REPOSITORY_ROOT / "venv" / "Lib" / "site-packages",
        REPOSITORY_ROOT / ".venv" / "Lib" / "site-packages",
    ):
        if candidate.exists():
            return str(candidate)
    return ""


class ItemTaxonomyRouteFlowTests(unittest.TestCase):
    def test_follow_up_migration_repairs_a_schema_without_subcategory(self):
        """Older schemas must gain the persisted second level safely."""
        with tempfile.TemporaryDirectory(prefix="sevor-taxonomy-subcategory-") as temp_dir:
            database_path = Path(temp_dir) / "missing-subcategory.sqlite3"
            script = r'''
import os
import sqlite3
import sys
from pathlib import Path

site_packages = os.environ.get("SEVOR_TEST_SITE_PACKAGES", "")
if site_packages:
    sys.path.insert(0, site_packages)

database_path = Path(os.environ["TAXONOMY_SUBCATEGORY_DB"])
connection = sqlite3.connect(database_path)
connection.executescript("""
CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL);
INSERT INTO alembic_version(version_num) VALUES ('item_taxonomy_20261002');
CREATE TABLE items (
  id INTEGER PRIMARY KEY, category VARCHAR(80), third_level VARCHAR(160),
  custom_third_level VARCHAR(200)
);
""")
connection.commit()
connection.close()

from alembic import command
from alembic.config import Config

root = Path(os.environ["TAXONOMY_SUBCATEGORY_ROOT"])
config = Config(str(root / "alembic.ini"))
config.set_main_option("script_location", str(root / "db_migrations"))
command.upgrade(config, "head")

connection = sqlite3.connect(database_path)
try:
    columns = {row[1] for row in connection.execute("PRAGMA table_info('items')")}
    assert "subcategory" in columns
    assert connection.execute(
        "SELECT version_num FROM alembic_version"
    ).fetchone()[0] == "item_subcat_taxonomy_20261002"
    index = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
        ("ix_items_category_subcategory_third_level",),
    ).fetchone()
    assert index is not None
finally:
    connection.close()
'''
            environment = os.environ.copy()
            environment.update(
                {
                    "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
                    "TAXONOMY_SUBCATEGORY_DB": str(database_path),
                    "TAXONOMY_SUBCATEGORY_ROOT": str(REPOSITORY_ROOT),
                }
            )
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

    def test_migrated_catalog_drives_real_create_to_edit_flow(self):
        with tempfile.TemporaryDirectory(prefix="sevor-taxonomy-route-flow-") as temp_dir:
            database_path = Path(temp_dir) / "route-flow.sqlite3"
            script = r'''
import os
import sqlite3
import sys
from pathlib import Path

site_packages = os.environ.get("SEVOR_TEST_SITE_PACKAGES", "")
if site_packages:
    sys.path.insert(0, site_packages)

database_path = Path(os.environ["TAXONOMY_ROUTE_FLOW_DB"])
connection = sqlite3.connect(database_path)
connection.executescript("""
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
INSERT INTO alembic_version(version_num) VALUES ('sevor_finder_20260929');
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
  subcategory VARCHAR(120), image_path VARCHAR(500), is_active VARCHAR(10),
  created_at TIMESTAMP
);
CREATE TABLE categories (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE);
CREATE TABLE subcategories (id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL, name VARCHAR(120) NOT NULL);
-- This legacy row supplies an existing normal two-level branch.  The
-- migration must backfill its lookup records without changing the Item.
INSERT INTO items (
  id, owner_id, title, description, city, currency, price, status,
  price_per_day, category, subcategory, is_active, created_at
) VALUES (
  1, 901, 'Legacy car seat', 'legacy', 'Montréal', 'CAD', 10, 'approved',
  10, 'Baby & Kids', 'Car Seats', 'yes', CURRENT_TIMESTAMP
);
""")
connection.commit()
connection.close()

# Upgrade only from the preceding revision.  No application model has been
# imported yet, so its physical-column compatibility detection sees the final
# schema rather than the legacy one.
from alembic import command
from alembic.config import Config

root = Path(os.environ["TAXONOMY_ROUTE_FLOW_ROOT"])
config = Config(str(root / "alembic.ini"))
config.set_main_option("script_location", str(root / "db_migrations"))
command.upgrade(config, "head")

connection = sqlite3.connect(database_path)
try:
    item_columns = {row[1] for row in connection.execute("PRAGMA table_info('items')")}
    assert {"subcategory", "third_level", "custom_third_level"}.issubset(item_columns)
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert revision == "item_subcat_taxonomy_20261002", revision
    digital = connection.execute(
        "SELECT id FROM categories WHERE name = ?", ("Digital Accounts",)
    ).fetchone()
    assert digital is not None
    seeded_types = {
        row[0] for row in connection.execute(
            "SELECT name FROM subcategories WHERE category_id = ?", (digital[0],)
        )
    }
    assert {"Movies & Streaming", "Sports"}.issubset(seeded_types)
    # There is deliberately no digital listing before the first form request.
    assert connection.execute(
        "SELECT COUNT(*) FROM items WHERE category = ?", ("Digital Accounts",)
    ).fetchone()[0] == 0
finally:
    connection.close()

from fastapi import Request
from fastapi.testclient import TestClient
import app.admin_items as admin_item_routes
import app.items as item_routes
import app.main as main_module
from app.database import SessionLocal
from app.models import Category, Item, Subcategory, User

# The route flow must not contact Cloudinary, Finder, or notification delivery.
# Those side effects are covered in their own tests and are outside taxonomy
# persistence; the database writes below remain real.
main_module._fx_schedule_daily_sync = lambda: None
item_routes.sync_listing_index = lambda *_args, **_kwargs: None
item_routes.cloudinary.uploader.upload = lambda *_args, **_kwargs: {"secure_url": "https://example.test/taxonomy.png"}
admin_item_routes.sync_listing_index = lambda *_args, **_kwargs: None
admin_item_routes.push_notification = lambda *_args, **_kwargs: None

@main_module.app.get("/_test_taxonomy_route_login/{role}")
def _test_taxonomy_route_login(role: str, request: Request):
    request.session["user"] = {"id": 901 if role == "user" else 902, "role": role, "status": "approved"}
    return {"ok": True}

db = SessionLocal()
try:
    db.add_all([
        User(
            id=901, first_name="Taxonomy", last_name="Owner",
            email="taxonomy-owner@example.test", phone="1", password_hash="x",
            role="user", status="approved",
        ),
        User(
            id=902, first_name="Taxonomy", last_name="Admin",
            email="taxonomy-admin@example.test", phone="2", password_hash="x",
            role="admin", status="approved",
        ),
    ])
    db.commit()
    digital = db.query(Category).filter(Category.name == "Digital Accounts").one()
    movies = db.query(Subcategory).filter(
        Subcategory.category_id == digital.id, Subcategory.name == "Movies & Streaming"
    ).one()
    sports = db.query(Subcategory).filter(
        Subcategory.category_id == digital.id, Subcategory.name == "Sports"
    ).one()
    gaming = db.query(Subcategory).filter(
        Subcategory.category_id == digital.id, Subcategory.name == "Gaming"
    ).one()
    baby = db.query(Category).filter(Category.name == "Baby & Kids").one()
    seats = db.query(Subcategory).filter(
        Subcategory.category_id == baby.id, Subcategory.name == "Car Seats"
    ).one()
    ids = {
        "movies": movies.id,
        "sports": sports.id,
        "gaming": gaming.id,
        "seats": seats.id,
        "digital": digital.id,
    }
finally:
    db.close()

def listing_form(*, title, subcategory_id, third_level="", custom_third_level="", category="Digital Accounts"):
    return {
        "title": title,
        "category": category,
        "subcategory_id": str(subcategory_id),
        "third_level": third_level,
        "custom_third_level": custom_third_level,
        "description": "Route-level taxonomy regression listing",
        "city": "Montréal",
        "no_website": "true",
        "price": "10",
        "currency": "CAD",
        "latitude": "",
        "longitude": "",
    }

def listing_image():
    return {"images": ("taxonomy.png", b"test-image", "image/png")}

with TestClient(main_module.app) as client:
    assert client.get("/_test_taxonomy_route_login/user").status_code == 200

    # The same seeded lookup source reaches Explore and Create even though
    # there are still zero Digital Accounts listings.
    empty_explore = client.get("/items?category=Digital%20Accounts")
    assert empty_explore.status_code == 200, empty_explore.text[:1000]
    assert "Movies &amp; Streaming" in empty_explore.text
    assert "Sports" in empty_explore.text
    assert "No items found" in empty_explore.text

    # The real creation page includes a persisted Category id rather than a
    # presentation-only option with no parent record for server validation.
    create = client.get("/owner/items/new")
    assert create.status_code == 200, create.text[:1000]
    assert f'value="Digital Accounts" data-id="{ids["digital"]}"' in create.text
    assert "Movies \\u0026 Streaming" in create.text
    assert "beIN Sports" in create.text

    # A server validation failure is a real form response, not a redirect; it
    # retains the submitted valid taxonomy so the client JS can rebuild it.
    missing_title = client.post(
        "/owner/items/new",
        data=listing_form(title="", subcategory_id=ids["movies"], third_level="Amazon Prime Video"),
    )
    assert missing_title.status_code == 422, missing_title.text[:1000]
    assert "Enter a title for your listing." in missing_title.text
    assert f'value="Digital Accounts" data-id="{ids["digital"]}" selected' in missing_title.text
    assert f'subcategoryId: "{ids["movies"]}"' in missing_title.text
    assert "Amazon Prime Video" in missing_title.text

    # A forged third-level value is rejected and does not create a row.
    forged = client.post(
        "/owner/items/new",
        data=listing_form(title="Forged service", subcategory_id=ids["sports"], third_level="Netflix"),
    )
    assert forged.status_code == 422, forged.text[:1000]
    assert "Choose a valid service for the selected type." in forged.text

    amazon_response = client.post(
        "/owner/items/new",
        data=listing_form(
            title="Amazon Prime Video edit source",
            subcategory_id=ids["movies"],
            third_level="Amazon Prime Video",
        ),
        files=listing_image(),
        follow_redirects=False,
    )
    assert amazon_response.status_code == 303, amazon_response.text[:1000]

    db = SessionLocal()
    try:
        amazon = db.query(Item).filter(Item.title == "Amazon Prime Video edit source").one()
        assert (amazon.category, amazon.subcategory, amazon.third_level, amazon.custom_third_level, amazon.status) == (
            "Digital Accounts", "Movies & Streaming", "Amazon Prime Video", None, "pending",
        )
        amazon_id = amazon.id
    finally:
        db.close()

    # Edit uses the same form payload.  Change its branch to Sports/beIN, then
    # change it to a normal two-level category and verify stale service fields
    # are cleared on the actual POST route.
    edit = client.get(f"/owner/items/{amazon_id}/edit")
    assert edit.status_code == 200, edit.text[:1000]
    assert "Amazon Prime Video" in edit.text
    invalid_edit = client.post(
        f"/owner/items/{amazon_id}/edit",
        data=listing_form(title="", subcategory_id=ids["movies"], third_level="Amazon Prime Video"),
    )
    assert invalid_edit.status_code == 422, invalid_edit.text[:1000]
    assert "Enter a title for your listing." in invalid_edit.text
    assert f'value="Digital Accounts" data-id="{ids["digital"]}" selected' in invalid_edit.text
    assert f'subcategoryId: "{ids["movies"]}"' in invalid_edit.text
    assert "Amazon Prime Video" in invalid_edit.text
    moved_to_sports = client.post(
        f"/owner/items/{amazon_id}/edit",
        data=listing_form(
            title="beIN Sports access",
            subcategory_id=ids["sports"],
            third_level="beIN Sports",
        ),
        follow_redirects=False,
    )
    assert moved_to_sports.status_code == 303
    db = SessionLocal()
    try:
        amazon = db.get(Item, amazon_id)
        assert (amazon.subcategory, amazon.third_level, amazon.custom_third_level) == (
            "Sports", "beIN Sports", None,
        )
    finally:
        db.close()
    moved_to_normal = client.post(
        f"/owner/items/{amazon_id}/edit",
        data=listing_form(
            title="Car seat after taxonomy change",
            category="Baby & Kids",
            subcategory_id=ids["seats"],
        ),
        follow_redirects=False,
    )
    assert moved_to_normal.status_code == 303
    db = SessionLocal()
    try:
        amazon = db.get(Item, amazon_id)
        assert (amazon.category, amazon.subcategory, amazon.third_level, amazon.custom_third_level) == (
            "Baby & Kids", "Car Seats", None, None,
        )
    finally:
        db.close()

    # Create an independently pending Digital listing, an Other service, and
    # a normal listing through the form route so each display shape is real.
    bein_response = client.post(
        "/owner/items/new",
        data=listing_form(
            title="Approved beIN Sports access",
            subcategory_id=ids["sports"],
            third_level="beIN Sports",
        ),
        files=listing_image(),
        follow_redirects=False,
    )
    assert bein_response.status_code == 303
    other_response = client.post(
        "/owner/items/new",
        data=listing_form(
            title="Custom streaming access",
            subcategory_id=ids["movies"],
            third_level="Other",
            custom_third_level="NewStreamingPlatform",
        ),
        files=listing_image(),
        follow_redirects=False,
    )
    assert other_response.status_code == 303
    normal_response = client.post(
        "/owner/items/new",
        data=listing_form(
            title="New car seat",
            category="Baby & Kids",
            subcategory_id=ids["seats"],
        ),
        files=listing_image(),
        follow_redirects=False,
    )
    assert normal_response.status_code == 303
    netflix_response = client.post(
        "/owner/items/new",
        data=listing_form(
            title="Netflix access",
            subcategory_id=ids["movies"],
            third_level="Netflix",
        ),
        files=listing_image(),
        follow_redirects=False,
    )
    assert netflix_response.status_code == 303
    amazon_lifecycle_response = client.post(
        "/owner/items/new",
        data=listing_form(
            title="Amazon Prime Video access",
            subcategory_id=ids["movies"],
            third_level="Amazon Prime Video",
        ),
        files=listing_image(),
        follow_redirects=False,
    )
    assert amazon_lifecycle_response.status_code == 303
    playstation_response = client.post(
        "/owner/items/new",
        data=listing_form(
            title="PlayStation Plus Premium access",
            subcategory_id=ids["gaming"],
            third_level="PlayStation Plus Premium",
        ),
        files=listing_image(),
        follow_redirects=False,
    )
    assert playstation_response.status_code == 303

    db = SessionLocal()
    try:
        bein = db.query(Item).filter(Item.title == "Approved beIN Sports access").one()
        other = db.query(Item).filter(Item.title == "Custom streaming access").one()
        normal = db.query(Item).filter(Item.title == "New car seat").one()
        netflix = db.query(Item).filter(Item.title == "Netflix access").one()
        amazon_lifecycle = db.query(Item).filter(Item.title == "Amazon Prime Video access").one()
        playstation = db.query(Item).filter(Item.title == "PlayStation Plus Premium access").one()
        assert (bein.category, bein.subcategory, bein.third_level, bein.custom_third_level) == (
            "Digital Accounts", "Sports", "beIN Sports", None,
        )
        assert (other.third_level, other.custom_third_level) == ("Other", "NewStreamingPlatform")
        assert (normal.category, normal.subcategory, normal.third_level, normal.custom_third_level) == (
            "Baby & Kids", "Car Seats", None, None,
        )
        assert (netflix.category, netflix.subcategory, netflix.third_level, netflix.custom_third_level) == (
            "Digital Accounts", "Movies & Streaming", "Netflix", None,
        )
        assert (amazon_lifecycle.category, amazon_lifecycle.subcategory, amazon_lifecycle.third_level, amazon_lifecycle.custom_third_level) == (
            "Digital Accounts", "Movies & Streaming", "Amazon Prime Video", None,
        )
        assert (playstation.category, playstation.subcategory, playstation.third_level, playstation.custom_third_level) == (
            "Digital Accounts", "Gaming", "PlayStation Plus Premium", None,
        )
        ids.update(
            {
                "bein_item": bein.id,
                "other_item": other.id,
                "normal_item": normal.id,
                "netflix_item": netflix.id,
                "amazon_item": amazon_lifecycle.id,
                "playstation_item": playstation.id,
            }
        )
    finally:
        db.close()

    assert client.get("/_test_taxonomy_route_login/admin").status_code == 200
    pending = client.get("/admin/items/pending")
    assert pending.status_code == 200, pending.text[:1000]
    for expected in (
        "Approved beIN Sports access", "Digital Accounts", "Sports", "beIN Sports",
        "Custom streaming access", "NewStreamingPlatform", "New car seat", "Car Seats",
        "Netflix access", "Amazon Prime Video access", "PlayStation Plus Premium access",
    ):
        assert expected in pending.text, expected

    # Approve every shape through the real admin route.  Approval must leave
    # the persisted hierarchy untouched before Explore reads it back.
    for item_id in (
        ids["bein_item"],
        ids["netflix_item"],
        ids["amazon_item"],
        ids["playstation_item"],
        ids["normal_item"],
        ids["other_item"],
    ):
        approved = client.post(f"/admin/items/{item_id}/approve", follow_redirects=False)
        assert approved.status_code == 302, approved.text[:1000]
    db = SessionLocal()
    try:
        assert (db.get(Item, ids["netflix_item"]).category, db.get(Item, ids["netflix_item"]).subcategory, db.get(Item, ids["netflix_item"]).third_level, db.get(Item, ids["netflix_item"]).custom_third_level, db.get(Item, ids["netflix_item"]).status) == (
            "Digital Accounts", "Movies & Streaming", "Netflix", None, "approved",
        )
        assert (db.get(Item, ids["amazon_item"]).category, db.get(Item, ids["amazon_item"]).subcategory, db.get(Item, ids["amazon_item"]).third_level, db.get(Item, ids["amazon_item"]).custom_third_level, db.get(Item, ids["amazon_item"]).status) == (
            "Digital Accounts", "Movies & Streaming", "Amazon Prime Video", None, "approved",
        )
        assert (db.get(Item, ids["bein_item"]).category, db.get(Item, ids["bein_item"]).subcategory, db.get(Item, ids["bein_item"]).third_level, db.get(Item, ids["bein_item"]).custom_third_level, db.get(Item, ids["bein_item"]).status) == (
            "Digital Accounts", "Sports", "beIN Sports", None, "approved",
        )
        assert (db.get(Item, ids["playstation_item"]).category, db.get(Item, ids["playstation_item"]).subcategory, db.get(Item, ids["playstation_item"]).third_level, db.get(Item, ids["playstation_item"]).custom_third_level, db.get(Item, ids["playstation_item"]).status) == (
            "Digital Accounts", "Gaming", "PlayStation Plus Premium", None, "approved",
        )
        assert (db.get(Item, ids["normal_item"]).category, db.get(Item, ids["normal_item"]).subcategory, db.get(Item, ids["normal_item"]).third_level, db.get(Item, ids["normal_item"]).custom_third_level, db.get(Item, ids["normal_item"]).status) == (
            "Baby & Kids", "Car Seats", None, None, "approved",
        )
        assert (db.get(Item, ids["other_item"]).third_level, db.get(Item, ids["other_item"]).custom_third_level, db.get(Item, ids["other_item"]).status) == (
            "Other", "NewStreamingPlatform", "approved",
        )
    finally:
        db.close()

    # Explore must read the same canonical fields at every depth.
    digital_level_one = client.get("/items?category=Digital%20Accounts")
    assert digital_level_one.status_code == 200
    for expected in (
        "Netflix access", "Amazon Prime Video access", "Approved beIN Sports access",
        "PlayStation Plus Premium access", "Custom streaming access",
    ):
        assert expected in digital_level_one.text, expected

    movies_level_two = client.get("/items?category=Digital%20Accounts&sub=Movies%20%26%20Streaming")
    assert movies_level_two.status_code == 200
    assert "Netflix access" in movies_level_two.text
    assert "Amazon Prime Video access" in movies_level_two.text
    assert "Approved beIN Sports access" not in movies_level_two.text
    assert "PlayStation Plus Premium access" not in movies_level_two.text

    def assert_service_filter(title, subcategory, service, excluded):
        response = client.get(
            "/items?category=Digital%20Accounts"
            f"&sub={subcategory}&service={service}"
        )
        assert response.status_code == 200, response.text[:1000]
        assert title in response.text
        for unexpected in excluded:
            assert unexpected not in response.text, unexpected

    assert_service_filter(
        "Netflix access", "Movies%20%26%20Streaming", "Netflix",
        ("Amazon Prime Video access", "Approved beIN Sports access", "PlayStation Plus Premium access"),
    )
    assert_service_filter(
        "Amazon Prime Video access", "Movies%20%26%20Streaming", "Amazon%20Prime%20Video",
        ("Netflix access", "Approved beIN Sports access", "PlayStation Plus Premium access"),
    )
    assert_service_filter(
        "Approved beIN Sports access", "Sports", "beIN%20Sports",
        ("Netflix access", "Amazon Prime Video access", "PlayStation Plus Premium access"),
    )
    assert_service_filter(
        "PlayStation Plus Premium access", "Gaming", "PlayStation%20Plus%20Premium",
        ("Netflix access", "Amazon Prime Video access", "Approved beIN Sports access"),
    )
    assert_service_filter(
        "Custom streaming access", "Movies%20%26%20Streaming", "Other",
        ("Netflix access", "Amazon Prime Video access", "Approved beIN Sports access"),
    )
    normal_explore = client.get("/items?category=Baby%20%26%20Kids&sub=Car%20Seats")
    assert normal_explore.status_code == 200
    assert "New car seat" in normal_explore.text
    assert "Netflix access" not in normal_explore.text

    for item_id, expected_hierarchy in (
        (ids["netflix_item"], ("Digital Accounts", "Movies & Streaming", "Netflix")),
        (ids["amazon_item"], ("Digital Accounts", "Movies & Streaming", "Amazon Prime Video")),
        (ids["bein_item"], ("Digital Accounts", "Sports", "beIN Sports")),
        (ids["playstation_item"], ("Digital Accounts", "Gaming", "PlayStation Plus Premium")),
    ):
        detail = client.get(f"/items/{item_id}")
        assert detail.status_code == 200, detail.text[:1000]
        for expected in expected_hierarchy:
            assert expected.replace("&", "&amp;") in detail.text, expected

    # An approved owner can now edit a listing; saving it sends it back to
    # pending review, keeping public approval meaningful while satisfying the
    # intended lifecycle.
    assert client.get("/_test_taxonomy_route_login/user").status_code == 200
    approved_edit = client.get(f"/owner/items/{ids['bein_item']}/edit", follow_redirects=False)
    assert approved_edit.status_code == 200, approved_edit.text[:1000]
    assert "beIN Sports" in approved_edit.text
    approved_to_normal = client.post(
        f"/owner/items/{ids['bein_item']}/edit",
        data=listing_form(
            title="Approved listing changed to normal category",
            category="Baby & Kids",
            subcategory_id=ids["seats"],
        ),
        follow_redirects=False,
    )
    assert approved_to_normal.status_code == 303
    db = SessionLocal()
    try:
        edited = db.get(Item, ids["bein_item"])
        assert (edited.category, edited.subcategory, edited.third_level, edited.custom_third_level, edited.status) == (
            "Baby & Kids", "Car Seats", None, None, "pending",
        )
    finally:
        db.close()

    # A manually forged stale child cannot reintroduce the old service after
    # a switch to a two-level branch.
    stale_child = client.post(
        f"/owner/items/{ids['bein_item']}/edit",
        data=listing_form(
            title="Approved listing changed to normal category",
            category="Baby & Kids",
            subcategory_id=ids["seats"],
            third_level="DAZN",
        ),
    )
    assert stale_child.status_code == 422
    assert "does not use a service level" in stale_child.text
    db = SessionLocal()
    try:
        edited = db.get(Item, ids["bein_item"])
        assert (edited.category, edited.subcategory, edited.third_level, edited.custom_third_level) == (
            "Baby & Kids", "Car Seats", None, None,
        )
    finally:
        db.close()

    # Exercise the requested edit direction directly: Sports/DAZN becomes
    # Movies & Streaming/Netflix, with the old service fully replaced.
    dazn_response = client.post(
        "/owner/items/new",
        data=listing_form(
            title="DAZN edit source",
            subcategory_id=ids["sports"],
            third_level="DAZN",
        ),
        files=listing_image(),
        follow_redirects=False,
    )
    assert dazn_response.status_code == 303
    db = SessionLocal()
    try:
        dazn = db.query(Item).filter(Item.title == "DAZN edit source").one()
        dazn_id = dazn.id
        assert (dazn.category, dazn.subcategory, dazn.third_level, dazn.custom_third_level) == (
            "Digital Accounts", "Sports", "DAZN", None,
        )
    finally:
        db.close()
    dazn_to_netflix = client.post(
        f"/owner/items/{dazn_id}/edit",
        data=listing_form(
            title="Netflix edited from DAZN",
            subcategory_id=ids["movies"],
            third_level="Netflix",
        ),
        follow_redirects=False,
    )
    assert dazn_to_netflix.status_code == 303
    db = SessionLocal()
    try:
        edited = db.get(Item, dazn_id)
        assert (edited.category, edited.subcategory, edited.third_level, edited.custom_third_level) == (
            "Digital Accounts", "Movies & Streaming", "Netflix", None,
        )
    finally:
        db.close()

    # Rendered French and Arabic forms localize labels only.  The French
    # option assertion demonstrates that the submitted value remains the
    # canonical English identity; Arabic uses the identical payload builder.
    session_cookie = next(cookie for cookie in client.cookies.jar if cookie.name == "ra_session")
    create_fr = client.get(
        "/owner/items/new",
        headers={"Cookie": f"ra_session={session_cookie.value}; lang=fr"},
    )
    assert create_fr.status_code == 200
    assert "Comptes numériques" in create_fr.text
    assert "Films et streaming" in create_fr.text
    assert 'value="Digital Accounts"' in create_fr.text
    create_ar = client.get(
        "/owner/items/new",
        headers={"Cookie": f"ra_session={session_cookie.value}; lang=ar"},
    )
    assert create_ar.status_code == 200
    assert "الحسابات الرقمية" in create_ar.text
'''
            environment = os.environ.copy()
            environment.update(
                {
                    "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
                    "TAXONOMY_ROUTE_FLOW_DB": str(database_path),
                    "TAXONOMY_ROUTE_FLOW_ROOT": str(REPOSITORY_ROOT),
                    "SECRET_KEY": "taxonomy-route-flow-test-only",
                    "COOKIE_DOMAIN": "testserver.local",
                    "HTTPS_ONLY_COOKIES": "0",
                    "SITE_URL": "",
                }
            )
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


if __name__ == "__main__":
    unittest.main()
