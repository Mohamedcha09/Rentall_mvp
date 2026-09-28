"""Focused regression tests for the country-picker persistence flow.

Run this module on its own.  It uses an isolated SQLite database and verifies
the rendered base template rather than only the JSON endpoints.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


TEST_DB = Path(tempfile.gettempdir()) / "sevor_geo_picker_tests.sqlite3"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SECRET_KEY"] = "geo-picker-test-secret"
os.environ["COOKIE_DOMAIN"] = "sevor.net"
os.environ["HTTPS_ONLY_COOKIES"] = "0"
os.environ["SITE_URL"] = ""
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient

import app.main as main_module


main_module._fx_schedule_daily_sync = lambda: None


class GeoPickerTests(unittest.TestCase):
    def _client(self) -> TestClient:
        # The matching canonical host is important: a permissive test client
        # alone would not reproduce a browser rejecting a foreign cookie.
        return TestClient(main_module.app, base_url="https://sevor.net")

    def test_each_region_persists_currency_and_hides_picker_on_next_page(self):
        for loc, expected_currency in (("CA", "CAD"), ("US", "USD"), ("FR", "EUR"), ("WORLD", "USD")):
            with self.subTest(loc=loc), self._client() as client:
                first_page = client.get("/welcome")
                self.assertEqual(first_page.status_code, 200)
                self.assertIn('id="geo-overlay"', first_page.text)

                selected = client.get(f"/geo/set?loc={loc}")
                self.assertEqual(selected.status_code, 200)
                self.assertTrue(selected.json()["ok"])
                self.assertEqual(selected.json()["currency"], expected_currency)
                self.assertIn("geo_manual_done=1", selected.headers.get("set-cookie", ""))
                self.assertEqual(client.cookies.get("geo_manual_done"), "1")

                debug = client.get("/geo/debug")
                self.assertEqual(debug.json()["session_geo"]["source"], "manual")
                self.assertEqual(debug.json()["session_geo"]["currency"], expected_currency)

                next_page = client.get("/welcome?after=region-choice")
                self.assertEqual(next_page.status_code, 200)
                self.assertNotIn('id="geo-overlay"', next_page.text)

    def test_not_now_is_persisted_and_geo_clear_allows_a_future_prompt(self):
        with self._client() as client:
            self.assertIn('id="geo-overlay"', client.get("/welcome").text)

            dismissed = client.post("/geo/dismiss")
            self.assertEqual(dismissed.status_code, 200)
            self.assertEqual(dismissed.json(), {"ok": True})
            self.assertIn("geo_manual_done=1", dismissed.headers.get("set-cookie", ""))
            self.assertEqual(client.cookies.get("geo_manual_done"), "1")
            self.assertIn("ra_session=", dismissed.headers.get("set-cookie", ""))

            self.assertNotIn('id="geo-overlay"', client.get("/welcome?after=dismiss").text)

            # The server-side session marker is deliberately a second durable
            # source of truth.  This covers Android WebView cases where a
            # process closes before it flushes the standalone preference
            # cookie from the dismiss response.
            for cookie in list(client.cookies.jar):
                if cookie.name == "geo_manual_done":
                    client.cookies.delete(cookie.name, domain=cookie.domain, path=cookie.path)
            self.assertNotIn(
                'id="geo-overlay"',
                client.get("/welcome?after=session-only-dismiss").text,
            )

            cleared = client.get("/geo/clear")
            self.assertEqual(cleared.status_code, 200)
            self.assertIn('geo_manual_done=""', cleared.headers.get("set-cookie", ""))
            self.assertIn('id="geo-overlay"', client.get("/welcome?after=clear").text)

    def test_picker_script_has_immediate_hide_and_failure_recovery_guards(self):
        template = (Path(__file__).resolve().parents[1] / "app" / "templates" / "geo_pick.html").read_text(encoding="utf-8")
        self.assertIn('let pending = false;', template)
        self.assertIn('root.style.display = "none";', template)
        self.assertIn('restoreAfterFailure();', template)
        self.assertIn('"/geo/dismiss"', template)


if __name__ == "__main__":
    unittest.main()
