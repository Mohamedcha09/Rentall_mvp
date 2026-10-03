"""Regression coverage for the durable direct-message attachment schema.

This starts from the same Alembic baseline currently recorded by Production:
``add_reports_and_is_mod_20251025``.  It proves that the additive migrations
can reach the storage-metadata head without rebuilding legacy attachments.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.catalog_taxonomy import DIGITAL_ACCOUNTS_CATEGORY, DIGITAL_ACCOUNTS_SERVICES


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_CONFIG = REPOSITORY_ROOT / "alembic.ini"
MIGRATIONS_PATH = REPOSITORY_ROOT / "db_migrations"
EXPECTED_HEAD = "item_subcat_taxonomy_20261002"
STORAGE_COLUMNS = (
    "storage_backend",
    "storage_key",
    "storage_resource_type",
    "storage_delivery_type",
    "storage_format",
)


class MessageAttachmentStorageMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_legacy_rows_and_reaches_storage_head(self):
        with tempfile.TemporaryDirectory(prefix="sevor-attachment-migration-") as temp_dir:
            database_path = Path(temp_dir) / "legacy.sqlite"
            self._create_production_baseline(database_path)

            previous_url = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
            try:
                config = Config(str(ALEMBIC_CONFIG))
                config.set_main_option("script_location", str(MIGRATIONS_PATH))
                command.upgrade(config, "head")
                # A second run must be a no-op rather than attempting duplicate DDL.
                command.upgrade(config, "head")
            finally:
                if previous_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = previous_url

            connection = sqlite3.connect(database_path)
            try:
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info('message_attachments')")
                }
                self.assertTrue(set(STORAGE_COLUMNS).issubset(columns))
                item_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info('items')")
                }
                self.assertTrue({"subcategory", "third_level", "custom_third_level"}.issubset(item_columns))
                self.assertLessEqual(len(EXPECTED_HEAD), 32)
                self.assertEqual(
                    connection.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                    EXPECTED_HEAD,
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT id, storage_backend, storage_key,
                               storage_resource_type, storage_delivery_type, storage_format
                        FROM message_attachments
                        ORDER BY id
                        """
                    ).fetchall(),
                    [
                        (1, "local", "legacy.png", None, None, None),
                        (2, "cloudinary", None, None, None, None),
                    ],
                )
                category = connection.execute(
                    "SELECT id, name FROM categories WHERE name = ?",
                    (DIGITAL_ACCOUNTS_CATEGORY,),
                ).fetchone()
                self.assertIsNotNone(category)
                seeded_types = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM subcategories WHERE category_id = ?",
                        (category[0],),
                    )
                }
                self.assertEqual(seeded_types, set(DIGITAL_ACCOUNTS_SERVICES))
                legacy_category = connection.execute(
                    "SELECT id FROM categories WHERE name = ?",
                    ("Baby & Kids",),
                ).fetchone()
                self.assertIsNotNone(legacy_category)
                self.assertEqual(
                    connection.execute(
                        "SELECT name FROM subcategories WHERE category_id = ?",
                        (legacy_category[0],),
                    ).fetchone()[0],
                    "Car Seats",
                )
            finally:
                connection.close()

    @staticmethod
    def _create_production_baseline(database_path: Path) -> None:
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                """
                CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
                INSERT INTO alembic_version(version_num)
                VALUES ('add_reports_and_is_mod_20251025');
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY,
                    category VARCHAR(80),
                    subcategory VARCHAR(120)
                );
                INSERT INTO items (id, category, subcategory)
                VALUES (99, 'Baby & Kids', 'Car Seats');
                CREATE TABLE categories (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(80) NOT NULL UNIQUE
                );
                CREATE TABLE subcategories (
                    id INTEGER PRIMARY KEY,
                    category_id INTEGER NOT NULL,
                    name VARCHAR(120) NOT NULL
                );
                CREATE TABLE users (id INTEGER PRIMARY KEY);
                CREATE TABLE support_tickets (id INTEGER PRIMARY KEY);
                CREATE TABLE support_messages (id INTEGER PRIMARY KEY);
                CREATE TABLE message_threads (id INTEGER PRIMARY KEY);
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    thread_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    client_message_id VARCHAR(72)
                );
                CREATE TABLE online_sessions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    last_seen DATETIME NOT NULL
                );
                CREATE TABLE message_attachments (
                    id INTEGER PRIMARY KEY,
                    thread_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    uploader_id INTEGER NOT NULL,
                    kind VARCHAR(16) NOT NULL,
                    original_name VARCHAR(180) NOT NULL,
                    stored_name VARCHAR(96) NOT NULL UNIQUE,
                    content_type VARCHAR(100) NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    duration_ms INTEGER,
                    created_at DATETIME NOT NULL
                );
                INSERT INTO message_attachments
                VALUES (1, 1, 1, 1, 'image', 'legacy.png', 'legacy.png',
                        'image/png', 10, NULL, CURRENT_TIMESTAMP);
                INSERT INTO message_attachments
                VALUES (2, 1, 2, 1, 'voice', 'legacy.m4a', 'cld1:v:abc123.m4a',
                        'audio/mp4', 20, NULL, CURRENT_TIMESTAMP);
                """
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
