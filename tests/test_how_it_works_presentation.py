"""Static regression checks for the public How Sevor Works guide.

The guide is intentionally presentation-only.  These checks protect its real
screenshots, auth-aware CTA branching, responsive reading order, and scoped
interactive affordances without needing a database or browser.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "app" / "templates" / "how_it_works_steps.html"
TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")


class HowItWorksPresentationTests(unittest.TestCase):
    def test_uses_every_real_guide_screenshot_once(self) -> None:
        screenshots = re.findall(r'<img src="/static/img/(\d+)\.jpg"', TEMPLATE)
        self.assertEqual(screenshots, [str(number) for number in range(1, 13)])
        for number in screenshots:
            self.assertTrue((ROOT / "app" / "static" / "img" / f"{number}.jpg").is_file())

    def test_images_preserve_readability_and_loading_priority(self) -> None:
        self.assertNotIn("object-fit: cover", TEMPLATE)
        self.assertIn("object-fit: contain", TEMPLATE)
        self.assertIn('fetchpriority="high"', TEMPLATE)
        self.assertEqual(TEMPLATE.count('loading="lazy"'), 11)
        self.assertEqual(TEMPLATE.count('data-hiw-lightbox data-src'), 12)
        self.assertEqual(TEMPLATE.count(' width="1179"'), 11)
        self.assertIn('width="1178" height="253"', TEMPLATE)

    def test_auth_aware_real_cta_routes(self) -> None:
        self.assertNotIn('href="/home"', TEMPLATE)
        self.assertIn('href="/items"', TEMPLATE)
        self.assertIn('href="/owner/items/new"', TEMPLATE)
        self.assertIn('{% if session_user %}', TEMPLATE)
        self.assertIn('href="/profile"', TEMPLATE)
        self.assertIn('href="/register"', TEMPLATE)
        self.assertIn('>My Profile<', TEMPLATE)
        self.assertIn('>Create an account<', TEMPLATE)

    def test_mobile_keeps_copy_before_screenshots(self) -> None:
        self.assertIn('grid-template-areas: "copy" "screen"', TEMPLATE)
        self.assertIn('@media (max-width: 900px)', TEMPLATE)
        self.assertIn('@media (prefers-reduced-motion: reduce)', TEMPLATE)
        self.assertIn('env(safe-area-inset-bottom', TEMPLATE)
        self.assertIn('min-height: 100dvh', TEMPLATE)

    def test_page_has_no_obsolete_instructional_chrome(self) -> None:
        self.assertNotIn("Desktop: left/right", TEMPLATE)
        self.assertNotIn("How it works (with screenshots)", TEMPLATE)
        self.assertIn('aria-label="Sevor rental journey, twelve steps"', TEMPLATE)
        self.assertIn('Suggested deposit guidance', TEMPLATE)
        self.assertIn('24h window', TEMPLATE)


if __name__ == "__main__":
    unittest.main()
