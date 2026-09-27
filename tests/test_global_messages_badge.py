"""Regression guards for the shared direct-message unread badge."""

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class GlobalMessagesBadgeTemplateTests(unittest.TestCase):
    def test_shared_tabbar_owns_the_direct_message_badge(self):
        """Every tabbar page must render the same badge placeholder and updater."""
        base = (REPOSITORY_ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        inbox = (REPOSITORY_ROOT / "app" / "templates" / "inbox.html").read_text(encoding="utf-8")

        self.assertIn('data-messages-unread-badge', base)
        self.assertIn('initGlobalMessagesUnreadBadge', base)
        self.assertIn("'/api/unread_summary'", base)
        self.assertIn("window.SevorMessagesUnread", base)
        self.assertIn("setInterval(pollOnce, 20000)", base)
        self.assertIn("window.SevorMessagesUnread?.refresh?.();", base)

        # The badge must use the SEVOR purple → blue → cyan identity, not the
        # previous Inbox-only red presentation.
        self.assertIn("linear-gradient(135deg, var(--primary, #7C4DFF), #4F6FFF, #28B8F5)", base)
        self.assertIn("total > 99 ? '99+'", base)
        self.assertIn("if (!hasSessionUser || !navLink || !badge) return;", base)

        # Inbox must not be the only place that creates or fetches this badge.
        self.assertNotIn("hydrateMessagesNavBadge", inbox)
        self.assertNotIn("renderMessagesNavBadge", inbox)
        self.assertNotIn("data-direct-unread-total", inbox)
        self.assertNotIn("background:#ee5368", inbox)


if __name__ == "__main__":
    unittest.main()
