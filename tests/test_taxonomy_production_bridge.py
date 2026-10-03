"""Regression coverage for the scoped production taxonomy bridge."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _site_packages() -> str:
    for candidate in (
        REPOSITORY_ROOT / "venv" / "Lib" / "site-packages",
        REPOSITORY_ROOT / ".venv" / "Lib" / "site-packages",
    ):
        if candidate.exists():
            return str(candidate)
    return ""


class TaxonomyProductionBridgeTests(unittest.TestCase):
    def test_base_bridge_remains_scoped_and_frozen(self):
        """The first bridge remains a small, independently deployable release."""
        with tempfile.TemporaryDirectory(prefix="sevor-taxonomy-base-bridge-") as temp_dir:
            database_path = Path(temp_dir) / "production-base.sqlite3"
            script = r'''
import os
import sqlite3
import sys
from pathlib import Path

site_packages = os.environ.get("SEVOR_TEST_SITE_PACKAGES", "")
if site_packages:
    sys.path.insert(0, site_packages)

database_path = Path(os.environ["TAXONOMY_BRIDGE_DB"])
connection = sqlite3.connect(database_path)
connection.executescript("""
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
INSERT INTO alembic_version(version_num) VALUES ('msg_attach_storage_20260927');
CREATE TABLE items (id INTEGER PRIMARY KEY, category VARCHAR(50) NOT NULL);
INSERT INTO items (id, category) VALUES (1, 'vehicle');
CREATE TABLE categories (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE);
CREATE TABLE subcategories (id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL, name VARCHAR(120) NOT NULL);
""")
connection.commit()
connection.close()

from alembic import command
from alembic.config import Config

root = Path(os.environ["TAXONOMY_BRIDGE_ROOT"])
config = Config(str(root / "alembic.ini"))
config.set_main_option("script_location", str(root / "db_migrations"))
command.upgrade(config, "taxonomy_bridge_20261004")

connection = sqlite3.connect(database_path)
try:
    assert connection.execute("SELECT category FROM items WHERE id=1").fetchone()[0] == 'vehicle'
    assert connection.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 21
    assert connection.execute("SELECT COUNT(*) FROM subcategories").fetchone()[0] == 121
    assert connection.execute(
        "SELECT COUNT(*) FROM categories WHERE name='Test & Measurement Equipment'"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='finder_conversations'"
    ).fetchone()[0] == 0
    assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == 'taxonomy_bridge_20261004'
finally:
    connection.close()
'''
            environment = os.environ.copy()
            environment.update(
                {
                    "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
                    "TAXONOMY_BRIDGE_DB": str(database_path),
                    "TAXONOMY_BRIDGE_ROOT": str(REPOSITORY_ROOT),
                    "SEVOR_TAXONOMY_BRIDGE_STRICT": "1",
                }
            )
            site_packages = _site_packages()
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

    def test_scoped_research_bridge_from_production_base_seeds_only_taxonomy(self):
        with tempfile.TemporaryDirectory(prefix="sevor-taxonomy-bridge-") as temp_dir:
            database_path = Path(temp_dir) / "production-base.sqlite3"
            script = r'''
import os
import sqlite3
import sys
from pathlib import Path

site_packages = os.environ.get("SEVOR_TEST_SITE_PACKAGES", "")
if site_packages:
    sys.path.insert(0, site_packages)

database_path = Path(os.environ["TAXONOMY_BRIDGE_DB"])
connection = sqlite3.connect(database_path)
connection.executescript("""
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
INSERT INTO alembic_version(version_num) VALUES ('msg_attach_storage_20260927');
CREATE TABLE items (id INTEGER PRIMARY KEY, category VARCHAR(50) NOT NULL);
INSERT INTO items (id, category) VALUES (1, 'vehicle');
CREATE TABLE categories (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE);
CREATE TABLE subcategories (
  id INTEGER PRIMARY KEY,
  category_id INTEGER NOT NULL,
  name VARCHAR(120) NOT NULL,
  FOREIGN KEY(category_id) REFERENCES categories(id)
);
""")
connection.commit()
connection.close()

from alembic import command
from alembic.config import Config
import importlib.util

root = Path(os.environ["TAXONOMY_BRIDGE_ROOT"])
config = Config(str(root / "alembic.ini"))
config.set_main_option("script_location", str(root / "db_migrations"))
command.upgrade(config, "research_bridge_20261005")

connection = sqlite3.connect(database_path)
try:
    item_columns = {row[1] for row in connection.execute("PRAGMA table_info('items')")}
    assert {"category", "subcategory", "third_level", "custom_third_level"}.issubset(item_columns)
    assert connection.execute("SELECT category FROM items WHERE id = 1").fetchone()[0] == 'vehicle'
    assert connection.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 22
    assert connection.execute("SELECT COUNT(*) FROM subcategories").fetchone()[0] == 135
    assert connection.execute(
        "SELECT COUNT(*) FROM subcategories s JOIN categories c ON c.id=s.category_id "
        "WHERE c.name='Digital Accounts'"
    ).fetchone()[0] == 17
    assert connection.execute(
        "SELECT COUNT(*) FROM subcategories s JOIN categories c ON c.id=s.category_id "
        "WHERE c.name='Vehicles' AND s.name='Buses'"
    ).fetchone()[0] == 1
    # The scoped path applies the immutable base bridge and then the immutable
    # research delta, without traversing the unrelated Finder lineage.
    migration_path = root / "db_migrations" / "versions" / "20261004_taxonomy_production_bridge.py"
    spec = importlib.util.spec_from_file_location("taxonomy_bridge_snapshot", migration_path)
    bridge = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(bridge)
    expected_tree = {
        category_name: set(children)
        for category_name, _aliases, children in bridge.RENTAL_CATEGORY_SEED
    }
    expected_tree[bridge.DIGITAL_CATEGORY] = set(bridge.DIGITAL_TYPES)
    research_path = root / "db_migrations" / "versions" / "20261005_research_taxonomy_production_bridge.py"
    research_spec = importlib.util.spec_from_file_location("research_bridge_snapshot", research_path)
    research = importlib.util.module_from_spec(research_spec)
    assert research_spec.loader is not None
    research_spec.loader.exec_module(research)
    for category_name, _aliases, children in research.CATEGORY_SEED:
        expected_tree.setdefault(category_name, set()).update(children)
    actual_tree = {
        category_name: {
            row[0]
            for row in connection.execute(
                "SELECT s.name FROM subcategories s JOIN categories c ON c.id=s.category_id "
                "WHERE c.name=?", (category_name,)
            )
        }
        for category_name in expected_tree
    }
    assert actual_tree == expected_tree
    test_measurement = connection.execute(
        "SELECT id FROM categories WHERE name='Test & Measurement Equipment'"
    ).fetchone()
    assert test_measurement is not None
    assert {
        row[0] for row in connection.execute(
            "SELECT name FROM subcategories WHERE category_id=?", (test_measurement[0],)
        )
    } == {'Electrical Test Instruments', 'Environmental Monitoring'}
    assert connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='finder_conversations'"
    ).fetchone()[0] == 0
    assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
        'research_bridge_20261005'
    )
finally:
    connection.close()
'''
            environment = os.environ.copy()
            environment.update(
                {
                    "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
                    "TAXONOMY_BRIDGE_DB": str(database_path),
                    "TAXONOMY_BRIDGE_ROOT": str(REPOSITORY_ROOT),
                    "SEVOR_TAXONOMY_BRIDGE_STRICT": "1",
                }
            )
            site_packages = _site_packages()
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
