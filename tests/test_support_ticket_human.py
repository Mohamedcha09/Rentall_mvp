"""Focused offline checks for the dedicated human-support ticket workspace.

These tests deliberately exercise only legacy/human ``/support/ticket``
conversations.  Chatbot tickets have a separate route and must not be mutated
by this page or its upload endpoints.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import Request
from fastapi.testclient import TestClient

# This suite must not share the chatbot suite's fixed SQLite filename.  A
# unique file avoids lock/race failures when test modules are run in parallel.
TEST_DB = Path(tempfile.gettempdir()) / f"sevor_human_ticket_{os.getpid()}_{uuid.uuid4().hex}.sqlite3"
_APP_DATABASE_WAS_PRELOADED = "app.database" in sys.modules


def _bootstrap_schema(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (
          id INTEGER PRIMARY KEY, first_name VARCHAR(100) NOT NULL, last_name VARCHAR(100) NOT NULL,
          email VARCHAR(200) NOT NULL UNIQUE, phone VARCHAR(50) NOT NULL, password_hash VARCHAR(255) NOT NULL,
          role VARCHAR(20), status VARCHAR(20), created_at TIMESTAMP,
          is_verified BOOLEAN DEFAULT 0, verified_at TIMESTAMP,
          badge_admin BOOLEAN DEFAULT 0, is_deposit_manager BOOLEAN DEFAULT 0,
          is_mod BOOLEAN DEFAULT 0, is_support BOOLEAN DEFAULT 0
        );
        CREATE TABLE documents (
          id INTEGER PRIMARY KEY, user_id INTEGER, doc_type VARCHAR(50), country VARCHAR(100),
          expiry_date DATE, file_front_path VARCHAR(500), file_back_path VARCHAR(500),
          review_status VARCHAR(20), review_note TEXT, created_at TIMESTAMP, reviewed_at TIMESTAMP
        );
        CREATE TABLE items (
          id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, title VARCHAR(200) NOT NULL,
          description TEXT, website_url VARCHAR(2048), city VARCHAR(120), currency VARCHAR(3), price NUMERIC,
          status VARCHAR(20), admin_feedback TEXT, reviewed_at TIMESTAMP, price_per_day INTEGER,
          category VARCHAR(50), image_path VARCHAR(500), is_active VARCHAR(10), created_at TIMESTAMP
        );
        CREATE TABLE bookings (
          id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL, renter_id INTEGER NOT NULL, owner_id INTEGER NOT NULL,
          start_date DATE NOT NULL, end_date DATE NOT NULL, days INTEGER, price_per_day_snapshot INTEGER,
          total_amount INTEGER, payment_status VARCHAR(20), deposit_status VARCHAR(30), security_status VARCHAR(30),
          refund_done BOOLEAN, deposit_refund_sent BOOLEAN, owner_payout_status VARCHAR(20), payout_sent BOOLEAN,
          payout_executed BOOLEAN, status VARCHAR(20), created_at TIMESTAMP, updated_at TIMESTAMP,
          loc_country VARCHAR(4), loc_sub VARCHAR(8)
        );
        CREATE TABLE support_tickets (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, subject VARCHAR(200) NOT NULL, channel VARCHAR(20),
          queue VARCHAR(20), status VARCHAR(20), assigned_to_id INTEGER, last_msg_at TIMESTAMP,
          updated_at TIMESTAMP, resolved_at TIMESTAMP, last_from VARCHAR(12), unread_for_user BOOLEAN,
          unread_for_agent BOOLEAN, created_at TIMESTAMP, closed_by VARCHAR, closed_at TIMESTAMP,
          ai_state VARCHAR(24) NOT NULL DEFAULT 'ai_active', ai_summary TEXT
        );
        CREATE TABLE support_messages (
          id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, sender_id INTEGER NOT NULL,
          sender_role VARCHAR(10), body TEXT NOT NULL, channel VARCHAR(20), created_at TIMESTAMP,
          is_read BOOLEAN, client_message_id VARCHAR(72), metadata_json TEXT
        );
        CREATE TABLE message_threads (
          id INTEGER PRIMARY KEY, user_a_id INTEGER NOT NULL, user_b_id INTEGER NOT NULL,
          item_id INTEGER, created_at TIMESTAMP, last_message_at TIMESTAMP
        );
        CREATE TABLE messages (
          id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL, sender_id INTEGER NOT NULL,
          body TEXT NOT NULL, created_at TIMESTAMP, is_read BOOLEAN DEFAULT 0, read_at TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()


if not _APP_DATABASE_WAS_PRELOADED:
    _bootstrap_schema(TEST_DB)
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
    os.environ["SECRET_KEY"] = "test-only-human-support-secret"
    os.environ["COOKIE_DOMAIN"] = "testserver.local"
    os.environ["HTTPS_ONLY_COOKIES"] = "0"
    os.environ["SITE_URL"] = ""
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("SEVOR_AI_MODEL", None)

import app.main as main_module
import app.routes_chatbot as chatbot_routes
import app.support_attachments as attachment_service
from app.database import SessionLocal
from app.models import SupportAttachment, SupportMessage, SupportMessageReceipt, SupportTicket, User


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 48
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"


if not _APP_DATABASE_WAS_PRELOADED:
    main_module._fx_schedule_daily_sync = lambda: None
    chatbot_routes.notify_waiting_agents = lambda db, ticket: None

    @main_module.app.get("/_test_human_support_login/{user_id}")
    def _test_human_support_login(user_id: int, request: Request):
        request.session["user"] = {"id": user_id}
        return {"ok": True}


def _csrf(client: TestClient) -> str:
    page = client.get("/chatbot")
    assert page.status_code == 200
    match = re.search(r"const csrfToken = (?P<token>\"[^\"]+\");", page.text)
    assert match, page.text[:1000]
    return json.loads(match.group("token"))


def _login(client: TestClient, user_id: int) -> str:
    response = client.get(f"/_test_human_support_login/{user_id}")
    assert response.status_code == 200
    return _csrf(client)


@unittest.skipIf(
    _APP_DATABASE_WAS_PRELOADED,
    "Run this isolated human-ticket suite in its own process so it never touches another suite's database.",
)
class HumanSupportTicketTests(unittest.TestCase):
    """Regression coverage for private files, receipts, and ticket-only UI."""

    owner_id = 301
    other_id = 302
    support_id = 303
    md_id = 304
    second_md_id = 305
    mod_id = 306

    @classmethod
    def setUpClass(cls):
        cls.private_root = Path(tempfile.mkdtemp(prefix="sevor-human-ticket-tests-"))
        cls._old_roots = (
            attachment_service.PRIVATE_UPLOAD_ROOT,
            attachment_service.SUPPORT_ATTACHMENT_ROOT,
            attachment_service.SUPPORT_ATTACHMENT_STAGING_ROOT,
        )
        # Never let an automated test write under the application's real
        # private upload directory, even when these tests are run after other
        # modules have imported the attachment service.
        attachment_service.PRIVATE_UPLOAD_ROOT = cls.private_root
        attachment_service.SUPPORT_ATTACHMENT_ROOT = cls.private_root / "support_ticket_attachments"
        attachment_service.SUPPORT_ATTACHMENT_STAGING_ROOT = attachment_service.SUPPORT_ATTACHMENT_ROOT / ".staging"

        db = SessionLocal()
        try:
            fixtures = (
                (cls.owner_id, "Human", "Owner", "human-owner@example.test", False),
                (cls.other_id, "Outside", "User", "outside-human@example.test", False),
                (cls.support_id, "Support", "Reader", "support-reader@example.test", True),
            )
            for user_id, first_name, last_name, email, is_support in fixtures:
                if not db.get(User, user_id):
                    db.add(
                        User(
                            id=user_id,
                            first_name=first_name,
                            last_name=last_name,
                            email=email,
                            phone=str(user_id),
                            password_hash="test-only",
                            role="user",
                            status="approved",
                            is_verified=True,
                            is_support=is_support,
                        )
                    )
            for user_id, first_name, email, role_flag in (
                (cls.md_id, "Deposit", "deposit-reader@example.test", "is_deposit_manager"),
                (cls.second_md_id, "Second Deposit", "deposit-reader-2@example.test", "is_deposit_manager"),
                (cls.mod_id, "Moderator", "moderator-reader@example.test", "is_mod"),
            ):
                if not db.get(User, user_id):
                    user = User(
                        id=user_id,
                        first_name=first_name,
                        last_name="Staff",
                        email=email,
                        phone=str(user_id),
                        password_hash="test-only",
                        role="user",
                        status="approved",
                        is_verified=True,
                    )
                    setattr(user, role_flag, True)
                    db.add(user)
            db.commit()
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        (attachment_service.PRIVATE_UPLOAD_ROOT,
         attachment_service.SUPPORT_ATTACHMENT_ROOT,
         attachment_service.SUPPORT_ATTACHMENT_STAGING_ROOT) = cls._old_roots
        shutil.rmtree(cls.private_root, ignore_errors=True)

    def setUp(self):
        self._purge_owned_tickets()
        if self.private_root.exists():
            shutil.rmtree(self.private_root)
        self.private_root.mkdir(parents=True, exist_ok=True)

    def _purge_owned_tickets(self):
        db = SessionLocal()
        try:
            ticket_ids = [row[0] for row in db.query(SupportTicket.id).filter(SupportTicket.user_id == self.owner_id).all()]
            if ticket_ids:
                message_ids = [row[0] for row in db.query(SupportMessage.id).filter(SupportMessage.ticket_id.in_(ticket_ids)).all()]
                if message_ids:
                    db.query(SupportMessageReceipt).filter(SupportMessageReceipt.message_id.in_(message_ids)).delete(synchronize_session=False)
                db.query(SupportAttachment).filter(SupportAttachment.ticket_id.in_(ticket_ids)).delete(synchronize_session=False)
                db.query(SupportMessage).filter(SupportMessage.ticket_id.in_(ticket_ids)).delete(synchronize_session=False)
                db.query(SupportTicket).filter(SupportTicket.id.in_(ticket_ids)).delete(synchronize_session=False)
                db.commit()
        finally:
            db.close()

    def _create_ticket(
        self,
        *,
        status="open",
        body="I need human support",
        sender_role="user",
        queue="cs",
        assigned_to_id=None,
    ) -> tuple[int, int]:
        now = datetime(2026, 9, 27, 10, 29, 23, 394933)
        db = SessionLocal()
        try:
            ticket = SupportTicket(
                user_id=self.owner_id,
                subject="Private human support issue",
                channel="legacy",
                queue=queue,
                status=status,
                assigned_to_id=assigned_to_id,
                created_at=now,
                updated_at=now,
                last_msg_at=now,
                last_from="user" if sender_role == "user" else "agent",
                unread_for_agent=sender_role == "user",
                unread_for_user=sender_role != "user",
            )
            db.add(ticket)
            db.flush()
            message = SupportMessage(
                ticket_id=ticket.id,
                sender_id=self.owner_id if sender_role == "user" else self.support_id,
                sender_role=sender_role,
                body=body,
                channel="legacy",
                created_at=now,
                is_read=False,
            )
            db.add(message)
            db.commit()
            return ticket.id, message.id
        finally:
            db.close()

    @staticmethod
    def _client_for(user_id: int) -> tuple[TestClient, str]:
        client = TestClient(main_module.app)
        csrf = _login(client, user_id)
        return client, csrf

    def test_human_ticket_page_is_chrome_isolated_and_keeps_history(self):
        ticket_id, _ = self._create_ticket(body="<script>ticket-xss-marker</script>")
        client, _csrf = self._client_for(self.owner_id)

        response = client.get(f"/support/ticket/{ticket_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"Ticket #{ticket_id}", response.text)
        self.assertIn("SEVOR Support", response.text)
        self.assertIn("support-ticket-page", response.text)
        self.assertIn("Write a message...", response.text)
        self.assertIn("&lt;script&gt;ticket-xss-marker&lt;/script&gt;", response.text)
        self.assertNotIn("<script>ticket-xss-marker</script>", response.text)

        # This must remain a dedicated human ticket view, not an AI/chatbot or
        # marketplace page.  The base CSS is allowed to exist, but its actual
        # navigation/banner DOM must not render on this focused route.
        self.assertNotIn("Sevor AI", response.text)
        self.assertNotIn("Quick Help", response.text)
        self.assertNotIn("Popular topics", response.text)
        self.assertNotIn("paypal-callout", response.text)
        self.assertNotIn('<nav class="mobile-tabbar', response.text)
        self.assertNotIn("2026-09-27 10:29:23.394933", response.text)

        updates = client.get(f"/support/ticket/{ticket_id}/updates?after_id=0")
        self.assertEqual(updates.status_code, 200)
        payload = updates.json()
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(payload["messages"][0]["body"], "<script>ticket-xss-marker</script>")

        # The client renderer must keep server text as text nodes and update a
        # receipt only from the persisted polling/read endpoint—not a timeout
        # pretending that support read a message.
        template_source = (Path(__file__).parents[1] / "app" / "templates" / "support_ticket.html").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", template_source)
        self.assertNotIn("setTimeout", template_source)
        self.assertIn("read_by_support_message_ids", template_source)
        self.assertIn("/support/ticket/${config.ticketId}/read", template_source)

    def test_customer_multipart_attachment_is_private_idempotent_and_validated(self):
        ticket_id, _ = self._create_ticket(body="Initial message")
        owner, csrf = self._client_for(self.owner_id)

        with patch("app.support.push_notification", lambda *args, **kwargs: None):
            response = owner.post(
                f"/support/ticket/{ticket_id}/reply",
                data={"body": "Here is the screenshot", "csrf_token": csrf, "client_message_id": "human-attachment-001"},
                files=[("attachments", ("receipt.png", PNG_BYTES, "image/png"))],
                headers={"Accept": "application/json"},
            )
        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertTrue(payload["created"])
        self.assertEqual(payload["message"]["body"], "Here is the screenshot")
        self.assertEqual(len(payload["message"]["attachments"]), 1)
        attachment_payload = payload["message"]["attachments"][0]
        self.assertEqual(attachment_payload["name"], "receipt.png")
        self.assertTrue(attachment_payload["is_image"])
        self.assertTrue(attachment_payload["url"].startswith(f"/support/ticket/{ticket_id}/attachments/"))
        self.assertNotIn("/uploads/", attachment_payload["url"])

        db = SessionLocal()
        try:
            attachment = db.query(SupportAttachment).filter(SupportAttachment.ticket_id == ticket_id).one()
            self.assertEqual(attachment.uploader_id, self.owner_id)
            saved_path = attachment_service.support_attachment_path(attachment)
            self.assertTrue(saved_path.is_file())
            self.assertTrue(str(saved_path).startswith(str(self.private_root)))
            self.assertNotIn("receipt.png", saved_path.name)
        finally:
            db.close()

        downloaded = owner.get(attachment_payload["url"])
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, PNG_BYTES)
        self.assertEqual(downloaded.headers.get("cache-control"), "private, no-store")
        self.assertEqual(downloaded.headers.get("x-content-type-options"), "nosniff")

        # Rendering the persisted history must use the same guarded URL for
        # its thumbnail; this also covers the image/file template branch.
        rendered = owner.get(f"/support/ticket/{ticket_id}")
        self.assertEqual(rendered.status_code, 200)
        self.assertIn("receipt.png", rendered.text)
        self.assertIn(attachment_payload["url"], rendered.text)

        other, _ = self._client_for(self.other_id)
        self.assertEqual(other.get(attachment_payload["url"]).status_code, 404)

        # Same client key must return the persisted message, not duplicate it.
        with patch("app.support.push_notification", lambda *args, **kwargs: None):
            duplicate = owner.post(
                f"/support/ticket/{ticket_id}/reply",
                data={"body": "Here is the screenshot", "csrf_token": csrf, "client_message_id": "human-attachment-001"},
                files=[("attachments", ("receipt.png", PNG_BYTES, "image/png"))],
                headers={"Accept": "application/json"},
            )
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertFalse(duplicate.json()["created"])

        db = SessionLocal()
        try:
            self.assertEqual(db.query(SupportAttachment).filter(SupportAttachment.ticket_id == ticket_id).count(), 1)
            self.assertEqual(
                db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket_id, SupportMessage.client_message_id == "human-attachment-001").count(),
                1,
            )
        finally:
            db.close()

        with patch("app.support.push_notification", lambda *args, **kwargs: None):
            attachment_only = owner.post(
                f"/support/ticket/{ticket_id}/reply",
                data={"body": "", "csrf_token": csrf, "client_message_id": "human-attachment-only-001"},
                files=[("attachments", ("only-file.png", PNG_BYTES, "image/png"))],
                headers={"Accept": "application/json"},
            )
        self.assertEqual(attachment_only.status_code, 201, attachment_only.text)
        self.assertEqual(attachment_only.json()["message"]["body"], "")

        # A friendly extension/content type cannot bypass the server signature
        # validation, and executable-like uploads are never accepted.
        invalid_signature = owner.post(
            f"/support/ticket/{ticket_id}/reply",
            data={"body": "", "csrf_token": csrf, "client_message_id": "human-invalid-png-001"},
            files=[("attachments", ("not-an-image.png", b"not a PNG", "image/png"))],
            headers={"Accept": "application/json"},
        )
        self.assertEqual(invalid_signature.status_code, 422, invalid_signature.text)
        self.assertIn("does not match", invalid_signature.json()["detail"])

        forbidden = owner.post(
            f"/support/ticket/{ticket_id}/reply",
            data={"body": "", "csrf_token": csrf, "client_message_id": "human-exe-001"},
            files=[("attachments", ("unsafe.exe", b"MZ\x00\x00", "application/octet-stream"))],
            headers={"Accept": "application/json"},
        )
        self.assertEqual(forbidden.status_code, 422, forbidden.text)
        self.assertIn("Only JPEG, PNG, WebP, and PDF", forbidden.json()["detail"])

    def test_actual_agent_view_creates_receipt_and_customer_poll_exposes_it(self):
        ticket_id, message_id = self._create_ticket(body="Please read this actual customer message")
        customer, _customer_csrf = self._client_for(self.owner_id)

        before = customer.get(f"/support/ticket/{ticket_id}/updates?after_id={message_id}")
        self.assertEqual(before.status_code, 200)
        self.assertNotIn(message_id, before.json()["read_by_support_message_ids"])

        agent, _agent_csrf = self._client_for(self.support_id)
        agent_view = agent.get(f"/cs/ticket/{ticket_id}")
        self.assertEqual(agent_view.status_code, 200, agent_view.text[:1000])

        db = SessionLocal()
        try:
            receipt = (
                db.query(SupportMessageReceipt)
                .filter(SupportMessageReceipt.message_id == message_id, SupportMessageReceipt.reader_id == self.support_id)
                .one_or_none()
            )
            self.assertIsNotNone(receipt)
            self.assertIsNotNone(receipt.read_at)
            self.assertTrue(db.get(SupportMessage, message_id).is_read)
        finally:
            db.close()

        after = customer.get(f"/support/ticket/{ticket_id}/updates?after_id={message_id}")
        self.assertEqual(after.status_code, 200)
        self.assertIn(message_id, after.json()["read_by_support_message_ids"])

        rendered = customer.get(f"/support/ticket/{ticket_id}")
        self.assertEqual(rendered.status_code, 200)
        self.assertIn("ticket-receipt--read", rendered.text)
        self.assertIn("✓✓", rendered.text)

    def test_support_agent_can_send_private_pdf_and_customer_can_open_it(self):
        ticket_id, _ = self._create_ticket(body="Can you send a document?")
        agent, csrf = self._client_for(self.support_id)

        with patch("app.cs.push_notification", lambda *args, **kwargs: None):
            sent = agent.post(
                f"/cs/ticket/{ticket_id}/reply",
                data={"body": "Attached is the approved document.", "csrf_token": csrf, "client_message_id": "agent-pdf-001"},
                files=[("attachments", ("support-document.pdf", PDF_BYTES, "application/pdf"))],
                follow_redirects=False,
            )
        self.assertEqual(sent.status_code, 303, sent.text)

        db = SessionLocal()
        try:
            attachment = (
                db.query(SupportAttachment)
                .filter(SupportAttachment.ticket_id == ticket_id, SupportAttachment.uploader_id == self.support_id)
                .one()
            )
            self.assertEqual(attachment.content_type, "application/pdf")
            attachment_url = f"/support/ticket/{ticket_id}/attachments/{attachment.id}"
        finally:
            db.close()

        customer, _ = self._client_for(self.owner_id)
        download = customer.get(attachment_url)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, PDF_BYTES)

    def test_closed_ticket_does_not_accept_a_new_message_server_side(self):
        ticket_id, _ = self._create_ticket(status="closed", body="Closed conversation")
        owner, csrf = self._client_for(self.owner_id)

        page = owner.get(f"/support/ticket/{ticket_id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("This ticket is closed.", page.text)
        self.assertIn('id="ticketBody" name="body" rows="1"', page.text)
        self.assertIn("disabled", page.text)

        rejected = owner.post(
            f"/support/ticket/{ticket_id}/reply",
            data={"body": "This must not reopen a closed ticket", "csrf_token": csrf, "client_message_id": "closed-ticket-001"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)

        # The closed-state rule also applies to old staff action URLs.  A
        # valid support session and CSRF token cannot transfer a historical
        # ticket into another queue.
        agent, agent_csrf = self._client_for(self.support_id)
        blocked_transfer = agent.post(
            f"/cs/tickets/{ticket_id}/transfer",
            data={"to": "md", "csrf_token": agent_csrf},
            follow_redirects=False,
        )
        self.assertEqual(blocked_transfer.status_code, 303)
        self.assertEqual(blocked_transfer.headers["location"], f"/cs/ticket/{ticket_id}")
        db = SessionLocal()
        try:
            ticket = db.get(SupportTicket, ticket_id)
            self.assertEqual(ticket.status, "closed")
            self.assertEqual(ticket.queue, "cs")
        finally:
            db.close()

    def test_staff_mutations_require_csrf_and_current_queue_assignment(self):
        """Direct staff URLs cannot bypass the same queue/assignee boundary."""
        ticket_id, _ = self._create_ticket(queue="md")

        # A CS agent cannot close an MD ticket merely by knowing its numeric
        # ID, even with a valid CSRF token.
        cs_agent, cs_csrf = self._client_for(self.support_id)
        wrong_queue_close = cs_agent.post(
            f"/cs/tickets/{ticket_id}/resolve",
            data={"csrf_token": cs_csrf},
            follow_redirects=False,
        )
        self.assertEqual(wrong_queue_close.status_code, 303)
        self.assertEqual(wrong_queue_close.headers["location"], "/cs/inbox")

        # A real unassigned MD-queue ticket remains claimable by an MD, but
        # the claim endpoint rejects a missing CSRF token.
        md_agent, md_csrf = self._client_for(self.md_id)
        missing_csrf = md_agent.post(
            f"/md/tickets/{ticket_id}/assign_self",
            data={},
            follow_redirects=False,
        )
        self.assertEqual(missing_csrf.status_code, 403)
        with patch("app.md.push_notification", lambda *args, **kwargs: None):
            claimed = md_agent.post(
                f"/md/tickets/{ticket_id}/assign_self",
                data={"csrf_token": md_csrf},
                follow_redirects=False,
            )
        self.assertEqual(claimed.status_code, 303, claimed.text)
        self.assertEqual(claimed.headers["location"], f"/md/ticket/{ticket_id}")

        # Once assigned, another MD cannot transfer the ticket, and a MOD
        # cannot claim it through its own direct endpoint while it is in MD.
        second_md, second_md_csrf = self._client_for(self.second_md_id)
        stale_transfer = second_md.post(
            f"/md/tickets/{ticket_id}/transfer_to_mod",
            data={"csrf_token": second_md_csrf},
            follow_redirects=False,
        )
        self.assertEqual(stale_transfer.status_code, 303)
        self.assertEqual(stale_transfer.headers["location"], "/md/inbox")

        mod_agent, mod_csrf = self._client_for(self.mod_id)
        wrong_queue_claim = mod_agent.post(
            f"/mod/tickets/{ticket_id}/assign_self",
            data={"csrf_token": mod_csrf},
            follow_redirects=False,
        )
        self.assertEqual(wrong_queue_claim.status_code, 303)
        self.assertEqual(wrong_queue_claim.headers["location"], "/mod/inbox")

        db = SessionLocal()
        try:
            ticket = db.get(SupportTicket, ticket_id)
            self.assertEqual(ticket.queue, "md")
            self.assertEqual(ticket.assigned_to_id, self.md_id)
            self.assertEqual(ticket.status, "open")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
