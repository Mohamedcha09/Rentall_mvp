"""Regression checks for the database URL selected by the running app."""
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


class DatabaseConnectionSelectionTests(unittest.TestCase):
    def _run(self, script: str, extra_environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        for name in (
            "DATABASE_URL",
            "DATABASE_URL_FULL",
            "DATABASE_URI",
            "RENDER",
            "RENDER_SERVICE_ID",
            "RENDER_EXTERNAL_URL",
        ):
            environment.pop(name, None)
        environment.update(extra_environment)
        site_packages = _site_packages()
        if site_packages:
            environment["PYTHONPATH"] = os.pathsep.join(
                part for part in (site_packages, environment.get("PYTHONPATH", "")) if part
            )
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_application_uses_database_url_full_before_local_sqlite_fallback(self):
        with tempfile.TemporaryDirectory(prefix="sevor-database-url-") as temp_dir:
            database_path = Path(temp_dir) / "render-like.sqlite3"
            completed = self._run(
                "from app.database import DB_URL, engine; "
                "assert DB_URL.endswith('render-like.sqlite3'); "
                "assert engine.url.get_backend_name() == 'sqlite'",
                {"DATABASE_URL_FULL": f"sqlite:///{database_path.as_posix()}"},
            )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_render_without_any_database_url_fails_closed(self):
        completed = self._run(
            "import app.database",
            {"RENDER_SERVICE_ID": "test-service"},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("No production database URL is configured", completed.stderr)


if __name__ == "__main__":
    unittest.main()
