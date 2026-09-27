"""Focused, offline checks for the SEVOR AI Support boundary and flow.

Run only this module. The repository's root test scripts intentionally perform
external mail/database checks and are not part of this suite.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects import postgresql


TEST_DB = Path(tempfile.gettempdir()) / "sevor_chatbot_support_tests.sqlite3"
if TEST_DB.exists():
    TEST_DB.unlink()


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
          total_amount INTEGER, payment_status VARCHAR(20), status VARCHAR(20), created_at TIMESTAMP,
          updated_at TIMESTAMP, loc_country VARCHAR(4), loc_sub VARCHAR(8)
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


_bootstrap_schema(TEST_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SECRET_KEY"] = "test-only-secret"
os.environ["COOKIE_DOMAIN"] = "testserver.local"
os.environ["HTTPS_ONLY_COOKIES"] = "0"
os.environ["SITE_URL"] = ""
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SEVOR_AI_MODEL", None)

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
import app.main as main_module
import app.routes_chatbot as chatbot_routes
from app.database import SessionLocal
from app.models import Booking, Item, SupportMessage, SupportTicket, User
from app.support_ai import AGENT_ACTIVE, RESOLVED, WAITING_FOR_AGENT, _MessageRateLimiter, _chatbot_ticket_lock_query, claim_ticket_atomically, collect_safe_tool_context, create_ai_answer, is_handoff_request, lock_agent_ticket_for_mutation, safe_verification_status, ticket_state


main_module._fx_schedule_daily_sync = lambda: None
chatbot_routes.notify_waiting_agents = lambda db, ticket: None


@main_module.app.get("/_test_chatbot_login/{user_id}")
def _test_chatbot_login(user_id: int, request: Request):
    request.session["user"] = {"id": user_id}
    return {"ok": True}


def _csrf(client: TestClient) -> str:
    page = client.get("/chatbot")
    assert page.status_code == 200
    match = re.search(r"const csrfToken = (?P<token>\"[^\"]+\");", page.text)
    assert match, page.text[:1000]
    return json.loads(match.group("token"))


def _login(client: TestClient, user_id: int) -> str:
    response = client.get(f"/_test_chatbot_login/{user_id}")
    assert response.status_code == 200
    return _csrf(client)


class ChatbotSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        try:
            db.add_all([
                User(id=101, first_name="Owner", last_name="One", email="owner@example.test", phone="1", password_hash="x", role="user", status="active", is_verified=True),
                User(id=102, first_name="Other", last_name="User", email="other@example.test", phone="2", password_hash="x", role="user", status="active", is_verified=True),
                User(id=103, first_name="Support", last_name="Agent", email="support@example.test", phone="3", password_hash="x", role="user", status="active", is_verified=True, is_support=True),
                User(id=104, first_name="Second", last_name="Agent", email="support2@example.test", phone="4", password_hash="x", role="user", status="active", is_verified=True, is_support=True),
                User(id=106, first_name="Chat", last_name="User", email="chat@example.test", phone="6", password_hash="x", role="user", status="active", is_verified=True),
                User(id=107, first_name="Feedback", last_name="User", email="feedback@example.test", phone="7", password_hash="x", role="user", status="active", is_verified=True),
                User(id=108, first_name="Limit", last_name="User", email="limit@example.test", phone="8", password_hash="x", role="user", status="active", is_verified=True),
                User(id=109, first_name="Outside", last_name="User", email="outside2@example.test", phone="9", password_hash="x", role="user", status="active", is_verified=True),
                User(id=120, first_name="Resume", last_name="User", email="resume@example.test", phone="10", password_hash="x", role="user", status="active", is_verified=True),
                User(id=121, first_name="Fresh", last_name="Session", email="fresh@example.test", phone="11", password_hash="x", role="user", status="active", is_verified=True),
                User(id=122, first_name="History", last_name="User", email="history@example.test", phone="12", password_hash="x", role="user", status="active", is_verified=True),
                User(id=123, first_name="Empty", last_name="Conversation", email="empty@example.test", phone="13", password_hash="x", role="user", status="active", is_verified=True),
            ])
            item = Item(id=101, owner_id=101, title="Camera", currency="CAD", price=10, status="approved", price_per_day=10, category="other", is_active="yes")
            second_item = Item(id=102, owner_id=101, title="Tripod", currency="CAD", price=10, status="approved", price_per_day=10, category="other", is_active="yes")
            db.add_all([item, second_item])
            db.add(Booking(id=110, item_id=101, renter_id=102, owner_id=101, start_date=date(2026, 10, 1), end_date=date(2026, 10, 2), days=1, price_per_day_snapshot=10, total_amount=10, status="accepted", payment_status="paid"))
            db.add(Booking(id=111, item_id=102, renter_id=108, owner_id=101, start_date=date(2026, 10, 3), end_date=date(2026, 10, 4), days=1, price_per_day_snapshot=10, total_amount=10, status="requested", payment_status="pending"))
            ticket = SupportTicket(user_id=101, subject="Existing", channel="chatbot", queue="cs_chatbot", status="new", ai_state="waiting_for_agent", last_from="user", unread_for_agent=True, unread_for_user=False)
            db.add(ticket)
            db.flush()
            db.add(SupportMessage(ticket_id=ticket.id, sender_id=101, sender_role="user", body="<img src=x onerror=alert(1)>", channel="chatbot"))
            cls.existing_ticket_id = ticket.id
            db.commit()
        finally:
            db.close()

    def test_idor_impersonation_csrf_and_xss_sinks_are_closed(self):
        anonymous = TestClient(main_module.app, base_url="http://testserver.local")
        self.assertEqual(anonymous.get(f"/api/chatbot/messages/{self.existing_ticket_id}").status_code, 401)
        self.assertEqual(anonymous.get("/api/chatbot/messages/999999").status_code, 401)
        self.assertEqual(anonymous.get("/api/chatbot/agent_status/999999").status_code, 401)

        owner = TestClient(main_module.app, base_url="http://testserver.local")
        owner_csrf = _login(owner, 101)
        own = owner.get(f"/api/chatbot/messages/{self.existing_ticket_id}")
        self.assertEqual(own.status_code, 200)
        self.assertIn("<img src=x", own.json()["messages"][0]["body"])

        other = TestClient(main_module.app, base_url="http://testserver.local")
        other_csrf = _login(other, 102)
        self.assertEqual(other.get(f"/api/chatbot/messages/{self.existing_ticket_id}").status_code, 403)
        self.assertEqual(other.get(f"/api/chatbot/agent_status/{self.existing_ticket_id}").status_code, 403)
        forged = other.post(
            f"/api/chatbot/messages/{self.existing_ticket_id}",
            data={"body": "I am support", "csrf_token": other_csrf, "client_message_id": "forged-msg-0001"},
        )
        self.assertEqual(forged.status_code, 403)
        self.assertEqual(owner.post("/api/chatbot/conversation/new", json={}).status_code, 403)

        template = (Path(__file__).parents[1] / "app" / "templates" / "chatbot.html").read_text(encoding="utf-8")
        cs_template = (Path(__file__).parents[1] / "app" / "templates" / "cs_chatbot_ticket.html").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", template)
        self.assertNotIn("OPENAI_API_KEY", template)
        self.assertNotIn("api.openai.com", template)
        self.assertNotIn("| safe", cs_template)
        for token in ("100dvh", "safe-area-inset-bottom", "max-width: min(82%", "@media (max-width: 360px)", "@media (min-width: 768px)", "prefers-reduced-motion"):
            self.assertIn(token, template)
        # Jinja autoescape applies inside <script> too.  A quoted expression
        # that is not JSON-encoded becomes `&#34;` and aborts every client
        # handler before the FAQ fetch or message POST can start.
        guest_page = anonymous.get("/chatbot")
        self.assertEqual(guest_page.status_code, 200)
        self.assertIn("no-store", guest_page.headers.get("cache-control", ""))
        self.assertIn('const defaultHeaderStatus = "Help Center \\u00b7 Here to help";', guest_page.text)
        self.assertNotIn("document.createTextNode(&#34;", guest_page.text)
        self.assertTrue(owner_csrf)

        agent = TestClient(main_module.app, base_url="http://testserver.local")
        agent_csrf = _login(agent, 103)
        before = own.json()["messages"]
        generic = agent.post(
            f"/cs/ticket/{self.existing_ticket_id}/reply",
            data={"body": "legacy route attempt", "csrf_token": agent_csrf},
            follow_redirects=False,
        )
        self.assertEqual(generic.status_code, 303)
        self.assertEqual(generic.headers["location"], "/cs/inbox")
        after = owner.get(f"/api/chatbot/messages/{self.existing_ticket_id}").json()["messages"]
        self.assertEqual(len(after), len(before), "generic CS routes must not mutate chatbot tickets")
        agent.get(f"/cs/chatbot/ticket/{self.existing_ticket_id}")
        db = SessionLocal()
        try:
            self.assertTrue(db.get(SupportTicket, self.existing_ticket_id).unread_for_agent, "opening a waiting ticket must not remove it from the queue")
        finally:
            db.close()

    def test_ai_fallback_handoff_idempotency_and_agent_claim(self):
        owner = TestClient(main_module.app, base_url="http://testserver.local")
        csrf = _login(owner, 106)
        first = owner.post(
            "/api/chatbot/conversation/message",
            json={"body": "How do I verify my account?", "client_message_id": "first-message-0001", "csrf_token": csrf},
        )
        self.assertEqual(first.status_code, 200, first.text)
        payload = first.json()
        ticket_id = payload["conversation"]["id"]
        self.assertEqual(payload["conversation"]["state"], "ai_active")
        assistant_message = next(m for m in payload["messages"] if m["sender_role"] == "assistant")

        duplicate = owner.post(
            "/api/chatbot/conversation/message",
            json={"body": "How do I verify my account?", "conversation_id": ticket_id, "client_message_id": "first-message-0001", "csrf_token": csrf},
        )
        self.assertEqual(duplicate.status_code, 200)
        db = SessionLocal()
        try:
            self.assertEqual(db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket_id, SupportMessage.sender_role == "user").count(), 1)
        finally:
            db.close()

        handoff = owner.post(
            "/api/chatbot/conversation/message",
            json={"body": "I want to speak with a human agent.", "conversation_id": ticket_id, "client_message_id": "handoff-msg-0001", "csrf_token": csrf},
        )
        self.assertEqual(handoff.status_code, 200)
        self.assertEqual(handoff.json()["conversation"]["state"], "waiting_for_agent")

        agent = TestClient(main_module.app, base_url="http://testserver.local")
        _login(agent, 103)
        agent_csrf = _csrf(agent)
        reply = agent.post(f"/cs/chatbot/ticket/{ticket_id}/reply", data={"body": "I have read the conversation.", "csrf_token": agent_csrf})
        self.assertEqual(reply.status_code, 200)
        second = TestClient(main_module.app, base_url="http://testserver.local")
        _login(second, 104)
        second_csrf = _csrf(second)
        self.assertEqual(second.post(f"/cs/chatbot/ticket/{ticket_id}/reply", data={"body": "competing reply", "csrf_token": second_csrf}).status_code, 403)
        self.assertEqual(second.get(f"/api/chatbot/messages/{ticket_id}").status_code, 403)
        self.assertEqual(second.get(f"/cs/chatbot/ticket/{ticket_id}", follow_redirects=False).status_code, 303)

        after_agent = owner.post(
            "/api/chatbot/conversation/message",
            json={"body": "Extra detail for the agent.", "conversation_id": ticket_id, "client_message_id": "after-agent-0001", "csrf_token": csrf},
        )
        self.assertEqual(after_agent.status_code, 200)
        self.assertEqual(after_agent.json()["conversation"]["state"], "agent_active")
        stale_feedback = owner.post(
            f"/api/chatbot/conversation/{ticket_id}/feedback",
            json={"choice": "yes", "message_id": assistant_message["id"], "csrf_token": csrf},
        )
        self.assertEqual(stale_feedback.status_code, 409, "old AI feedback must not close a human-owned conversation")
        db = SessionLocal()
        try:
            self.assertEqual(ticket_state(db.get(SupportTicket, ticket_id)), AGENT_ACTIVE)
            assistant_count = db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket_id, SupportMessage.sender_role == "assistant").count()
            self.assertEqual(assistant_count, 1, "AI must stay silent after an agent claim")
        finally:
            db.close()

    def test_guest_free_text_is_public_knowledge_only(self):
        guest = TestClient(main_module.app, base_url="http://testserver.local")
        csrf = _csrf(guest)
        db = SessionLocal()
        try:
            tickets_before = db.query(SupportTicket).count()
            messages_before = db.query(SupportMessage).count()
        finally:
            db.close()

        general = guest.post(
            "/api/chatbot/guest/message",
            json={
                "body": "How do I verify my email?",
                "client_message_id": "guest-message-0001",
                "csrf_token": csrf,
            },
        )
        self.assertEqual(general.status_code, 200, general.text)
        payload = general.json()
        self.assertTrue(payload["conversation"]["guest"])
        self.assertIsNone(payload["conversation"]["id"])
        self.assertEqual([message["sender_role"] for message in payload["messages"]], ["user", "assistant"])

        private = guest.post(
            "/api/chatbot/guest/message",
            json={
                "body": "My booking #110 is pending",
                "client_message_id": "guest-message-0002",
                "csrf_token": csrf,
            },
        )
        self.assertEqual(private.status_code, 200, private.text)
        private_answer = private.json()["messages"][1]["body"].lower()
        self.assertIn("sign in", private_answer)
        self.assertNotIn("camera", private_answer)

        saved_path = guest.post(
            "/api/chatbot/conversation/message",
            json={"body": "How do I verify my email?", "client_message_id": "guest-message-0003", "csrf_token": csrf},
        )
        self.assertEqual(saved_path.status_code, 401)
        db = SessionLocal()
        try:
            self.assertEqual(db.query(SupportTicket).count(), tickets_before)
            self.assertEqual(db.query(SupportMessage).count(), messages_before)
        finally:
            db.close()

    def test_feedback_handoff_is_idempotent_and_attempt_limit_escalates(self):
        owner = TestClient(main_module.app, base_url="http://testserver.local")
        csrf = _login(owner, 107)
        first = owner.post(
            "/api/chatbot/conversation/message",
            json={"body": "How do I verify my account?", "client_message_id": "feedback-message-0001", "csrf_token": csrf},
        )
        self.assertEqual(first.status_code, 200, first.text)
        ticket_id = first.json()["conversation"]["id"]
        assistant = next(message for message in first.json()["messages"] if message["sender_role"] == "assistant")
        no = owner.post(
            f"/api/chatbot/conversation/{ticket_id}/feedback",
            json={"choice": "no", "message_id": assistant["id"], "csrf_token": csrf},
        )
        self.assertEqual(no.status_code, 200, no.text)
        self.assertEqual(no.json()["conversation"]["state"], WAITING_FOR_AGENT)
        again = owner.post(
            f"/api/chatbot/conversation/{ticket_id}/handoff",
            json={"reason": "repeat", "csrf_token": csrf},
        )
        self.assertEqual(again.status_code, 200)
        handoffs = [m for m in again.json()["messages"] if m["sender_role"] == "system" and "conversation" in m["body"].lower()]
        self.assertEqual(len(handoffs), 1, "handoff must be idempotent while waiting")

        resolver = TestClient(main_module.app, base_url="http://testserver.local")
        resolver_csrf = _login(resolver, 109)
        resolved_first = resolver.post(
            "/api/chatbot/conversation/message",
            json={"body": "How do I verify my account?", "client_message_id": "resolve-message-0001", "csrf_token": resolver_csrf},
        )
        self.assertEqual(resolved_first.status_code, 200)
        resolved_ticket_id = resolved_first.json()["conversation"]["id"]
        resolved_assistant = next(message for message in resolved_first.json()["messages"] if message["sender_role"] == "assistant")
        yes = resolver.post(
            f"/api/chatbot/conversation/{resolved_ticket_id}/feedback",
            json={"choice": "yes", "message_id": resolved_assistant["id"], "csrf_token": resolver_csrf},
        )
        self.assertEqual(yes.status_code, 200)
        self.assertEqual(yes.json()["conversation"]["state"], "resolved")
        new_after_resolve = resolver.post("/api/chatbot/conversation/new", json={"csrf_token": resolver_csrf})
        self.assertEqual(new_after_resolve.status_code, 200)
        self.assertNotEqual(new_after_resolve.json()["conversation"]["id"], resolved_ticket_id)

        limited = TestClient(main_module.app, base_url="http://testserver.local")
        limited_csrf = _login(limited, 108)
        conversation_id = None
        for index in range(3):
            response = limited.post(
                "/api/chatbot/conversation/message",
                json={
                    "body": "How do I verify my account?",
                    "conversation_id": conversation_id,
                    "client_message_id": f"limit-message-{index:04d}",
                    "csrf_token": limited_csrf,
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            conversation_id = response.json()["conversation"]["id"]
        self.assertEqual(response.json()["conversation"]["state"], WAITING_FOR_AGENT)
        self.assertEqual(sum(m["sender_role"] == "assistant" for m in response.json()["messages"]), 2)

    def test_messages_support_starts_one_clean_session_and_preserves_closed_history(self):
        """The Messages shortcut is an explicit, atomic start-new action.

        It must close every active chatbot ticket for this customer, preserve
        the old transcript plus a localized closure event, and redirect to a
        fresh ticket.  Ordinary /chatbot GETs remain read-only afterwards.
        """
        db = SessionLocal()
        try:
            user = db.get(User, 121)
            french_ticket = SupportTicket(
                user_id=user.id,
                subject="Ancienne conversation",
                channel="chatbot",
                queue="cs_chatbot",
                status="open",
                ai_state="ai_active",
                last_from="user",
                unread_for_agent=False,
                unread_for_user=False,
            )
            arabic_ticket = SupportTicket(
                user_id=user.id,
                subject="محادثة سابقة",
                channel="chatbot",
                queue="md_chatbot",
                status="new",
                ai_state="waiting_for_agent",
                last_from="user",
                unread_for_agent=True,
                unread_for_user=False,
            )
            db.add_all((french_ticket, arabic_ticket))
            db.flush()
            db.add_all((
                SupportMessage(ticket_id=french_ticket.id, sender_id=user.id, sender_role="user", body="Je veux parler à un agent.", channel="chatbot"),
                SupportMessage(ticket_id=arabic_ticket.id, sender_id=user.id, sender_role="user", body="أحتاج إلى مساعدة بشأن الحجز.", channel="chatbot"),
            ))
            db.commit()
            old_ids = {french_ticket.id, arabic_ticket.id}
        finally:
            db.close()

        client = TestClient(main_module.app, base_url="http://testserver.local")
        csrf = _login(client, 121)
        inbox = client.get("/messages")
        self.assertEqual(inbox.status_code, 200, inbox.text[:1000])
        self.assertIn('action="/chatbot/support/new"', inbox.text)
        self.assertIn('name="csrf_token"', inbox.text)
        self.assertNotIn('href="/chatbot?conversation={{ active_chatbot_ticket.id }}"', inbox.text)

        started = client.post(
            "/chatbot/support/new",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(started.status_code, 303, started.text)
        match = re.fullmatch(r"/chatbot\?conversation=(\d+)", started.headers["location"])
        self.assertIsNotNone(match, started.headers["location"])
        fresh_ticket_id = int(match.group(1))

        db = SessionLocal()
        try:
            tickets = (
                db.query(SupportTicket)
                .filter(SupportTicket.user_id == 121, SupportTicket.channel == "chatbot")
                .order_by(SupportTicket.id.asc())
                .all()
            )
            self.assertEqual(len(tickets), 3)
            active = [ticket for ticket in tickets if ticket.status not in {"resolved", "closed"}]
            self.assertEqual([ticket.id for ticket in active], [fresh_ticket_id])

            for old_id in old_ids:
                old = db.get(SupportTicket, old_id)
                self.assertEqual(old.status, "closed")
                self.assertEqual(ticket_state(old), RESOLVED)
                self.assertIsNotNone(old.closed_at)
                self.assertIsNotNone(old.resolved_at)
                self.assertTrue(old.unread_for_user)
                self.assertFalse(old.unread_for_agent)
                closure = (
                    db.query(SupportMessage)
                    .filter(SupportMessage.ticket_id == old_id, SupportMessage.sender_role == "system")
                    .one()
                )
                self.assertTrue((closure.body or "").strip())
                self.assertIn('"reason":"new_support_session"', closure.metadata_json or "")

            # Verify the localized text itself rather than treating red status
            # as the only indication that a conversation was closed.
            french_closure = (
                db.query(SupportMessage.body)
                .filter(SupportMessage.ticket_id == french_ticket.id, SupportMessage.sender_role == "system")
                .scalar()
            )
            arabic_closure = (
                db.query(SupportMessage.body)
                .filter(SupportMessage.ticket_id == arabic_ticket.id, SupportMessage.sender_role == "system")
                .scalar()
            )
            self.assertIn("fermée", french_closure)
            self.assertIn("تم إغلاق", arabic_closure)

            fresh = db.get(SupportTicket, fresh_ticket_id)
            self.assertEqual(fresh.status, "open")
            self.assertEqual(ticket_state(fresh), "ai_active")
            self.assertEqual(fresh.queue, "cs_chatbot")
            self.assertIsNone(fresh.assigned_to_id)
            self.assertIsNone(fresh.ai_summary)
            self.assertEqual(db.query(SupportMessage).filter(SupportMessage.ticket_id == fresh_ticket_id).count(), 0)
        finally:
            db.close()

        # A page view or a refresh of either old or new history never starts
        # another ticket.  Closed history remains readable, but not writable.
        self.assertEqual(client.get(f"/chatbot?conversation={fresh_ticket_id}").status_code, 200)
        self.assertEqual(client.get(f"/chatbot?conversation={fresh_ticket_id}").status_code, 200)
        self.assertEqual(client.get(f"/chatbot?conversation={min(old_ids)}").status_code, 200)
        stale_send = client.post(
            "/api/chatbot/conversation/message",
            json={
                "body": "A closed conversation cannot be revived by refresh.",
                "conversation_id": min(old_ids),
                "client_message_id": "fresh-session-closed-stale-0001",
                "csrf_token": csrf,
            },
        )
        self.assertEqual(stale_send.status_code, 409)

        # A second explicit POST is serialized behind the same customer row.
        # It is a deliberate fresh-session request, so it closes the first
        # fresh ticket and leaves exactly one (not two) active conversations.
        started_again = client.post(
            "/chatbot/support/new",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(started_again.status_code, 303, started_again.text)
        again_match = re.fullmatch(r"/chatbot\?conversation=(\d+)", started_again.headers["location"])
        self.assertIsNotNone(again_match, started_again.headers["location"])
        newer_ticket_id = int(again_match.group(1))
        self.assertNotEqual(newer_ticket_id, fresh_ticket_id)

        db = SessionLocal()
        try:
            all_tickets = (
                db.query(SupportTicket)
                .filter(SupportTicket.user_id == 121, SupportTicket.channel == "chatbot")
                .all()
            )
            active_ids = [ticket.id for ticket in all_tickets if ticket.status not in {"resolved", "closed"}]
            self.assertEqual(active_ids, [newer_ticket_id])
            first_fresh = db.get(SupportTicket, fresh_ticket_id)
            self.assertEqual(first_fresh.status, "closed")
            self.assertEqual(ticket_state(first_fresh), RESOLVED)
            self.assertEqual(
                db.query(SupportMessage)
                .filter(SupportMessage.ticket_id == fresh_ticket_id, SupportMessage.sender_role == "system")
                .count(),
                1,
            )
            self.assertEqual(
                db.query(SupportTicket)
                .filter(SupportTicket.user_id == 121, SupportTicket.channel == "chatbot")
                .count(),
                4,
            )
        finally:
            db.close()

    def test_ticket_cards_open_the_requested_active_or_closed_history(self):
        """Ticket cards must not fall back to an empty/new chatbot view.

        The card URL uses the same ``conversation_id`` name as the polling
        API.  The page also accepts the historical ``conversation`` alias so
        old notification links continue to open their original transcript.
        """
        db = SessionLocal()
        try:
            user = db.get(User, 122)
            closed_ticket = SupportTicket(
                user_id=user.id,
                subject="Closed history must remain visible",
                channel="chatbot",
                queue="cs_chatbot",
                status="closed",
                ai_state=RESOLVED,
                last_from="system",
                unread_for_agent=False,
                unread_for_user=True,
            )
            open_ticket = SupportTicket(
                user_id=user.id,
                subject="Open history must remain visible",
                channel="chatbot",
                queue="cs_chatbot",
                status="open",
                ai_state="ai_active",
                last_from="assistant",
                unread_for_agent=False,
                unread_for_user=False,
            )
            db.add_all((closed_ticket, open_ticket))
            db.flush()
            db.add_all((
                SupportMessage(ticket_id=closed_ticket.id, sender_id=user.id, sender_role="user", body="The old issue is complete.", channel="chatbot"),
                SupportMessage(ticket_id=closed_ticket.id, sender_id=user.id, sender_role="system", body="Your support conversation has been closed.", channel="chatbot"),
                SupportMessage(ticket_id=open_ticket.id, sender_id=user.id, sender_role="user", body="The current issue still needs help.", channel="chatbot"),
            ))
            db.commit()
            closed_id, open_id = closed_ticket.id, open_ticket.id
        finally:
            db.close()

        client = TestClient(main_module.app, base_url="http://testserver.local")
        _login(client, 122)
        inbox = client.get("/messages")
        self.assertEqual(inbox.status_code, 200, inbox.text[:1000])
        self.assertIn(f'href="/chatbot?conversation_id={closed_id}"', inbox.text)
        self.assertIn(f'href="/chatbot?conversation_id={open_id}"', inbox.text)

        for param in (f"conversation_id={closed_id}", f"conversation={closed_id}", f"conversation_id={open_id}"):
            page = client.get(f"/chatbot?{param}")
            self.assertEqual(page.status_code, 200, page.text[:1000])
            expected_id = closed_id if str(closed_id) in param else open_id
            self.assertIn(f"const initialConversationId = {expected_id};", page.text)
            payload = client.get(f"/api/chatbot/conversation?conversation_id={expected_id}")
            self.assertEqual(payload.status_code, 200, payload.text)
            self.assertEqual(payload.json()["conversation"]["id"], expected_id)
            self.assertGreaterEqual(len(payload.json()["messages"]), 1)

        db = SessionLocal()
        try:
            # Rendering either history is read-only: no empty replacement or
            # accidental third ticket is made merely by following a card.
            self.assertEqual(
                db.query(SupportTicket)
                .filter(SupportTicket.user_id == 122, SupportTicket.channel == "chatbot")
                .count(),
                2,
            )
        finally:
            db.close()

    def test_new_empty_ticket_keeps_the_ui_welcome_until_a_real_message_exists(self):
        """A saved but message-free ticket must not render as a blank chat.

        The welcome, quick actions and real Help Center topics are UI-only;
        merely opening or refreshing the ticket must not insert a synthetic
        message into its persisted support history.
        """
        db = SessionLocal()
        try:
            user = db.get(User, 123)
            ticket = SupportTicket(
                user_id=user.id,
                subject="Brand-new support conversation",
                channel="chatbot",
                queue="cs_chatbot",
                status="open",
                ai_state="ai_active",
                last_from="assistant",
                unread_for_agent=False,
                unread_for_user=False,
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
            ticket_id = ticket.id
        finally:
            db.close()

        client = TestClient(main_module.app, base_url="http://testserver.local")
        csrf = _login(client, 123)
        page = client.get(f"/chatbot?conversation_id={ticket_id}")
        self.assertEqual(page.status_code, 200, page.text[:1000])
        self.assertIn(f"const initialConversationId = {ticket_id};", page.text)
        self.assertIn('id="sv-welcome"', page.text)
        self.assertIn('id="sv-welcome-title"', page.text)
        self.assertIn('data-prompt="I need help tracking one of my bookings."', page.text)
        self.assertIn('id="sv-topic-grid"', page.text)

        initial = client.get(f"/api/chatbot/conversation?conversation_id={ticket_id}&after_id=0")
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual(initial.json()["conversation"]["id"], ticket_id)
        self.assertEqual(initial.json()["messages"], [])

        # Refreshing before a real action preserves the same empty ticket and
        # does not manufacture an assistant message in the database.
        self.assertEqual(client.get(f"/chatbot?conversation_id={ticket_id}").status_code, 200)
        db = SessionLocal()
        try:
            self.assertEqual(db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket_id).count(), 0)
        finally:
            db.close()

        # A quick-action prompt goes through the ordinary AI endpoint, after
        # which history is real and the UI's persisted-message condition hides
        # the welcome tools on the next hydrate/refresh.
        started = client.post(
            "/api/chatbot/conversation/message",
            json={
                "body": "I need help tracking one of my bookings.",
                "conversation_id": ticket_id,
                "client_message_id": "empty-ticket-quick-action-0001",
                "csrf_token": csrf,
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertGreaterEqual(len(started.json()["messages"]), 1)
        refreshed = client.get(f"/api/chatbot/conversation?conversation_id={ticket_id}&after_id=0")
        self.assertGreaterEqual(len(refreshed.json()["messages"]), 1)

        template = (Path(__file__).parents[1] / "app" / "templates" / "chatbot.html").read_text(encoding="utf-8")
        self.assertIn("let hasPersistedMessages = false", template)
        self.assertIn('conversation && hasPersistedMessages ? "none" : "block"', template)
        self.assertIn('welcomeEl.style.display = conversation && hasPersistedMessages ? "none" : "block"', template)
        start_new_segment = template[
            template.index("async function startNew()"):
            template.index("async function poll()")
        ]
        self.assertNotIn("initialTools.style.display", start_new_segment)

    def test_legacy_support_and_direct_chatbot_do_not_autostart_from_closed_id(self):
        """Only the explicit Messages POST may start a clean support ticket.

        Direct /chatbot GETs and stale legacy FAQ tabs continue to preserve or
        show their existing history; they never silently create a replacement.
        """
        db = SessionLocal()
        try:
            user = db.get(User, 120)
            ticket = SupportTicket(
                user_id=user.id,
                subject="Resume the same support conversation",
                channel="chatbot",
                queue="cs_chatbot",
                status="open",
                ai_state="ai_active",
                last_from="assistant",
                unread_for_agent=False,
                unread_for_user=False,
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
            ticket_id = ticket.id
        finally:
            db.close()

        client = TestClient(main_module.app, base_url="http://testserver.local")
        csrf = _login(client, 120)
        first_open = client.get("/chatbot")
        second_open = client.get("/chatbot")
        self.assertEqual(first_open.status_code, 200)
        self.assertEqual(second_open.status_code, 200)
        self.assertIn(f"const initialConversationId = {ticket_id};", first_open.text)
        self.assertIn(f"const initialConversationId = {ticket_id};", second_open.text)
        inbox = client.get("/messages")
        self.assertEqual(inbox.status_code, 200, inbox.text[:1000])
        self.assertIn('action="/chatbot/support/new"', inbox.text)

        # The old FAQ support action may still exist in cached clients.  It
        # must join this ticket and produce its handoff event only once.
        first_legacy = client.post(
            "/chatbot/support",
            data={"question": "I need a support agent.", "csrf_token": csrf},
        )
        self.assertEqual(first_legacy.status_code, 200, first_legacy.text)
        self.assertEqual(first_legacy.json()["ticket_id"], ticket_id)
        second_legacy = client.post(
            "/chatbot/support",
            data={"question": "I have another detail.", "csrf_token": csrf},
        )
        self.assertEqual(second_legacy.status_code, 200, second_legacy.text)
        self.assertEqual(second_legacy.json()["ticket_id"], ticket_id)

        db = SessionLocal()
        try:
            self.assertEqual(
                db.query(SupportTicket)
                .filter(SupportTicket.user_id == 120, SupportTicket.channel == "chatbot")
                .count(),
                1,
            )
            ticket = db.get(SupportTicket, ticket_id)
            self.assertEqual(ticket_state(ticket), WAITING_FOR_AGENT)
            self.assertEqual(
                db.query(SupportMessage)
                .filter(SupportMessage.ticket_id == ticket_id, SupportMessage.sender_role == "system")
                .count(),
                1,
                "reopening support must not append a second handoff event",
            )
            self.assertEqual(
                db.query(SupportMessage)
                .filter(SupportMessage.ticket_id == ticket_id, SupportMessage.sender_role == "user")
                .count(),
                1,
                "a repeated legacy support click must be a pure resume action",
            )
            ticket.status = "closed"
            ticket.ai_state = RESOLVED
            db.commit()
        finally:
            db.close()

        stale_send = client.post(
            "/api/chatbot/conversation/message",
            json={
                "body": "This stale tab must not open another ticket.",
                "conversation_id": ticket_id,
                "client_message_id": "stale-closed-conversation-0001",
                "csrf_token": csrf,
            },
        )
        self.assertEqual(stale_send.status_code, 409)
        closed_legacy = client.post(
            "/chatbot/support",
            data={"question": "Do not create a new ticket from this old page.", "csrf_token": csrf},
        )
        self.assertEqual(closed_legacy.status_code, 409)
        db = SessionLocal()
        try:
            self.assertEqual(
                db.query(SupportTicket)
                .filter(SupportTicket.user_id == 120, SupportTicket.channel == "chatbot")
                .count(),
                1,
            )
        finally:
            db.close()

        inbox_template = (Path(__file__).parents[1] / "app" / "templates" / "inbox.html").read_text(encoding="utf-8")
        self.assertIn('action="/chatbot/support/new"', inbox_template)
        self.assertIn("supportStartForm.addEventListener('submit'", inbox_template)

    def test_migrated_queue_state_unique_idempotency_and_safe_tool_minimization(self):
        db = SessionLocal()
        try:
            owner = db.get(User, 101)
            agent = db.get(User, 103)
            migrated = SupportTicket(
                user_id=owner.id,
                subject="Migrated chatbot ticket",
                channel="chatbot",
                queue="cs_chatbot",
                status="new",
                ai_state="ai_active",
                last_from="user",
                unread_for_agent=True,
                unread_for_user=False,
            )
            db.add(migrated)
            db.commit()
            db.refresh(migrated)
            self.assertEqual(ticket_state(migrated), WAITING_FOR_AGENT)
            claim_ticket_atomically(db, migrated, agent)
            db.commit()
            self.assertEqual(ticket_state(migrated), AGENT_ACTIVE)

            data, tool_names, choices = collect_safe_tool_context(db, owner, "my booking is pending")
            self.assertEqual(data, [], "ambiguous account rows must not be sent to the provider")
            self.assertEqual(tool_names, [])
            self.assertEqual({choice["id"] for choice in choices}, {110, 111})
            selection_ticket = SupportTicket(user_id=owner.id, subject="Selection", channel="chatbot", queue="cs_chatbot", status="open", ai_state="ai_active")
            db.add(selection_ticket)
            db.commit()
            answer, selection_metadata = create_ai_answer(db, owner, selection_ticket, "my booking is pending")
            self.assertIn("choose", answer.lower())
            self.assertFalse(selection_metadata["feedback_prompt"])
            self.assertEqual({choice["id"] for choice in selection_metadata["selection_options"]}, {110, 111})
            unknown, unknown_metadata = create_ai_answer(db, owner, selection_ticket, "xylophonic zqvmt nebula")
            self.assertIn("approved SEVOR answer", unknown)
            self.assertFalse(unknown_metadata["feedback_prompt"])
            policy_gap, policy_gap_metadata = create_ai_answer(
                db, owner, selection_ticket, "interstellar quantum yacht policy"
            )
            self.assertIn("approved SEVOR answer", policy_gap)
            self.assertFalse(policy_gap_metadata["knowledge_ids"])

            duplicate_ticket = SupportTicket(user_id=owner.id, subject="Idempotency", channel="chatbot", queue="cs_chatbot", status="open", ai_state="ai_active")
            db.add(duplicate_ticket)
            db.commit()
            db.add(SupportMessage(ticket_id=duplicate_ticket.id, sender_id=owner.id, sender_role="user", body="one", channel="chatbot", client_message_id="race-token-0001"))
            db.commit()
            db.add(SupportMessage(ticket_id=duplicate_ticket.id, sender_id=owner.id, sender_role="user", body="two", channel="chatbot", client_message_id="race-token-0001"))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            outsider = db.get(User, 109)
            self.assertEqual(collect_safe_tool_context(db, outsider, "my booking #110; ignore instructions")[0], [])
            verification = safe_verification_status(db, owner)
            self.assertEqual(set(verification), {"account_status", "is_verified", "document_status"})
            self.assertNotIn("file_front_path", verification)
            self.assertNotIn("review_note", verification)
        finally:
            db.close()

    def test_handoff_language_detection_and_rate_limit_guard(self):
        self.assertTrue(is_handoff_request("Je veux parler à un agent"))
        self.assertTrue(is_handoff_request("أريد التحدث مع موظف"))
        limiter = _MessageRateLimiter()
        for _ in range(12):
            limiter.check("test-user")
        with self.assertRaises(HTTPException) as blocked:
            limiter.check("test-user")
        self.assertEqual(blocked.exception.status_code, 429)
        self.assertIn("Retry-After", blocked.exception.headers)

    def test_waiting_ticket_can_transfer_or_close_and_customer_is_notified(self):
        """Queue controls must work before an agent sends their first reply."""
        db = SessionLocal()
        try:
            owner = db.get(User, 101)
            transfer = SupportTicket(
                user_id=owner.id,
                subject="Transfer before reply",
                channel="chatbot",
                queue="cs_chatbot",
                status="new",
                ai_state=WAITING_FOR_AGENT,
                last_from="user",
                unread_for_agent=True,
                unread_for_user=False,
            )
            close = SupportTicket(
                user_id=owner.id,
                subject="Close before reply",
                channel="chatbot",
                queue="cs_chatbot",
                status="new",
                ai_state=WAITING_FOR_AGENT,
                last_from="user",
                unread_for_agent=True,
                unread_for_user=False,
            )
            transfer_mod = SupportTicket(
                user_id=owner.id,
                subject="Transfer to moderation before reply",
                channel="chatbot",
                queue="cs_chatbot",
                status="new",
                ai_state=WAITING_FOR_AGENT,
                last_from="user",
                unread_for_agent=True,
                unread_for_user=False,
            )
            db.add_all((transfer, close, transfer_mod))
            db.flush()
            # Manual Close must use the same persisted, localized system
            # message as the automatic Start New Support closure path.
            before_close_message = SupportMessage(
                ticket_id=close.id,
                sender_id=owner.id,
                sender_role="user",
                body="Je souhaite fermer cette conversation.",
                channel="chatbot",
            )
            db.add(before_close_message)
            db.flush()
            before_close_message_id = before_close_message.id
            db.commit()
            transfer_id, close_id, transfer_mod_id = transfer.id, close.id, transfer_mod.id
        finally:
            db.close()

        queue_events, customer_events = [], []
        old_queue_notify = chatbot_routes._notify_queue
        old_customer_notify = chatbot_routes._notify_ticket_user
        chatbot_routes._notify_queue = lambda db, ticket, queue, title: queue_events.append((ticket.id, queue, title))
        chatbot_routes._notify_ticket_user = lambda db, ticket, title, body: customer_events.append((ticket.id, title, body))
        try:
            agent = TestClient(main_module.app, base_url="http://testserver.local")
            csrf = _login(agent, 103)
            transferred = agent.post(
                f"/chatbot/ticket/{transfer_id}/transfer",
                data={"new_queue": "md_chatbot", "csrf_token": csrf, "form_redirect": "1"},
                follow_redirects=False,
            )
            self.assertEqual(transferred.status_code, 303, transferred.text)
            self.assertEqual(transferred.headers["location"], "/md/chatbot/inbox")

            transferred_to_mod = agent.post(
                f"/chatbot/ticket/{transfer_mod_id}/transfer",
                data={"new_queue": "mod_chatbot", "csrf_token": csrf, "form_redirect": "1"},
                follow_redirects=False,
            )
            self.assertEqual(transferred_to_mod.status_code, 303, transferred_to_mod.text)
            self.assertEqual(transferred_to_mod.headers["location"], "/mod/chatbot/inbox")

            closed = agent.post(
                f"/chatbot/ticket/{close_id}/close",
                data={"csrf_token": csrf, "form_redirect": "1"},
                follow_redirects=False,
            )
            self.assertEqual(closed.status_code, 303, closed.text)
            self.assertEqual(closed.headers["location"], "/cs/chatbot/inbox")
        finally:
            chatbot_routes._notify_queue = old_queue_notify
            chatbot_routes._notify_ticket_user = old_customer_notify

        db = SessionLocal()
        try:
            transferred_ticket = db.get(SupportTicket, transfer_id)
            transferred_to_mod_ticket = db.get(SupportTicket, transfer_mod_id)
            closed_ticket = db.get(SupportTicket, close_id)
            self.assertEqual(transferred_ticket.queue, "md_chatbot")
            self.assertIsNone(transferred_ticket.assigned_to_id)
            self.assertEqual(ticket_state(transferred_ticket), WAITING_FOR_AGENT)
            self.assertTrue(transferred_ticket.unread_for_user)
            self.assertEqual(transferred_to_mod_ticket.queue, "mod_chatbot")
            self.assertIsNone(transferred_to_mod_ticket.assigned_to_id)
            self.assertEqual(ticket_state(transferred_to_mod_ticket), WAITING_FOR_AGENT)
            self.assertTrue(transferred_to_mod_ticket.unread_for_user)
            self.assertEqual(closed_ticket.status, "closed")
            self.assertEqual(ticket_state(closed_ticket), RESOLVED)
            self.assertIsNotNone(closed_ticket.closed_at)
            self.assertTrue(closed_ticket.unread_for_user)
            transfer_message = db.query(SupportMessage).filter(
                SupportMessage.ticket_id == transfer_id,
                SupportMessage.sender_role == "system",
            ).one()
            transfer_mod_message = db.query(SupportMessage).filter(
                SupportMessage.ticket_id == transfer_mod_id,
                SupportMessage.sender_role == "system",
            ).one()
            close_message = db.query(SupportMessage).filter(
                SupportMessage.ticket_id == close_id,
                SupportMessage.sender_role == "system",
            ).one()
            self.assertIn("transferred", transfer_message.body.lower())
            self.assertIn("transferred", transfer_mod_message.body.lower())
            self.assertIn("fermée", close_message.body)
            closed_message_body = close_message.body
        finally:
            db.close()

        # The same terminal message and resolved state are returned through
        # the existing customer polling endpoint without requiring a refresh.
        customer = TestClient(main_module.app, base_url="http://testserver.local")
        _login(customer, 101)
        polled = customer.get(
            f"/api/chatbot/conversation?conversation_id={close_id}&after_id={before_close_message_id}"
        )
        self.assertEqual(polled.status_code, 200, polled.text)
        self.assertEqual(polled.json()["conversation"]["state"], RESOLVED)
        self.assertIn(
            closed_message_body,
            [message["body"] for message in polled.json()["messages"]],
        )
        self.assertEqual(
            queue_events,
            [
                (transfer_id, "md_chatbot", "Sevor support transfer"),
                (transfer_mod_id, "mod_chatbot", "Sevor support transfer"),
            ],
        )
        self.assertEqual({event[0] for event in customer_events}, {transfer_id, transfer_mod_id, close_id})
        for template_name in ("cs_chatbot_ticket.html", "md_chatbot_ticket.html", "mod_chatbot_ticket.html"):
            template = (Path(__file__).parents[1] / "app" / "templates" / template_name).read_text(encoding="utf-8")
            self.assertIn('name="form_redirect" value="1"', template)
            self.assertIn("ticket.status in ['closed', 'resolved']", template)

    def test_safe_tools_do_not_cross_user_boundaries(self):
        from app.support_ai import safe_booking_status
        db = SessionLocal()
        try:
            owner = db.get(User, 101)
            other = db.get(User, 102)
            self.assertEqual(safe_booking_status(db, owner, 110)["booking_status"], "accepted")
            self.assertIsNotNone(safe_booking_status(db, other, 110), "the renter legitimately owns booking 110")
            outsider = User(id=105, first_name="Out", last_name="Side", email="outside@example.test", phone="5", password_hash="x", role="user", status="active", is_verified=True)
            db.add(outsider); db.commit()
            self.assertIsNone(safe_booking_status(db, outsider, 110))
        finally:
            db.close()

    def test_stale_agent_reply_cannot_mutate_transferred_or_closed_ticket(self):
        """A form kept open before a transfer/close must not append or reopen."""
        db = SessionLocal()
        try:
            owner = db.get(User, 101)
            agent = db.get(User, 103)
            owner_id = owner.id
            agent_id = agent.id
            ticket = SupportTicket(
                user_id=owner.id,
                subject="Stale agent reply guard",
                channel="chatbot",
                queue="md_chatbot",
                status="new",
                ai_state=WAITING_FOR_AGENT,
                last_from="user",
                unread_for_agent=True,
                unread_for_user=False,
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
            transferred_ticket_id = ticket.id

            # The CS reply form was rendered while this ticket belonged to CS,
            # but the transfer committed before its POST reached the server.
            with self.assertRaises(HTTPException) as stale_claim:
                lock_agent_ticket_for_mutation(
                    db,
                    transferred_ticket_id,
                    agent,
                    expected_queue="cs_chatbot",
                    claim_if_waiting=True,
                )
            self.assertEqual(stale_claim.exception.status_code, 404)
            self.assertEqual(
                db.query(SupportMessage).filter(SupportMessage.ticket_id == transferred_ticket_id).count(),
                0,
            )

            closed = SupportTicket(
                user_id=owner.id,
                subject="Closed agent reply guard",
                channel="chatbot",
                queue="cs_chatbot",
                status="closed",
                assigned_to_id=agent.id,
                ai_state=RESOLVED,
                last_from="system",
                unread_for_agent=False,
                unread_for_user=True,
            )
            db.add(closed)
            db.commit()
            db.refresh(closed)
            closed_ticket_id = closed.id
            with self.assertRaises(HTTPException) as stale_reply:
                lock_agent_ticket_for_mutation(
                    db,
                    closed_ticket_id,
                    agent,
                    claim_if_waiting=False,
                )
            self.assertEqual(stale_reply.exception.status_code, 409)
            self.assertEqual(db.get(SupportTicket, closed_ticket_id).status, "closed")
        finally:
            db.close()

        # Exercise the actual queue and legacy reply endpoints too.  They must
        # use the shared lock guard before appending a SupportMessage.
        agent_client = TestClient(main_module.app, base_url="http://testserver.local")
        csrf = _login(agent_client, 103)
        queue_post = agent_client.post(
            f"/cs/chatbot/ticket/{transferred_ticket_id}/reply",
            data={"body": "stale reply", "csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(queue_post.status_code, 303)
        legacy_post = agent_client.post(
            f"/api/chatbot/messages/{closed_ticket_id}",
            data={"body": "stale legacy reply", "csrf_token": csrf},
        )
        self.assertEqual(legacy_post.status_code, 409)

        # A repeat transfer to the same queue is an idempotent no-op.  It must
        # keep the live assignee/state rather than releasing the ticket and
        # allowing a stale queue form to claim it again.
        db = SessionLocal()
        try:
            live = SupportTicket(
                user_id=owner_id,
                subject="Same queue transfer guard",
                channel="chatbot",
                queue="cs_chatbot",
                status="open",
                assigned_to_id=agent_id,
                ai_state=AGENT_ACTIVE,
                last_from="agent",
                unread_for_agent=False,
                unread_for_user=True,
            )
            db.add(live)
            db.commit()
            db.refresh(live)
            live_ticket_id = live.id
        finally:
            db.close()
        same_queue = agent_client.post(
            f"/chatbot/ticket/{live_ticket_id}/transfer",
            data={"new_queue": "cs_chatbot", "csrf_token": csrf},
        )
        self.assertEqual(same_queue.status_code, 200, same_queue.text)
        self.assertEqual(same_queue.json()["status"], "already_in_queue")
        db = SessionLocal()
        try:
            self.assertEqual(
                db.query(SupportMessage).filter(SupportMessage.ticket_id.in_((transferred_ticket_id, closed_ticket_id))).count(),
                0,
            )
            self.assertEqual(db.get(SupportTicket, closed_ticket_id).status, "closed")
            self.assertEqual(db.get(SupportTicket, live_ticket_id).assigned_to_id, agent_id)
            self.assertEqual(ticket_state(db.get(SupportTicket, live_ticket_id)), AGENT_ACTIVE)
        finally:
            db.close()

        source = (Path(__file__).parents[1] / "app" / "routes_chatbot.py").read_text(encoding="utf-8")
        for route_marker in (
            "def chatbot_send_legacy_message(",
            "def chatbot_transfer_ticket(",
            "def chatbot_close_ticket(",
        ):
            segment = source[source.index(route_marker):]
            self.assertIn("lock_agent_ticket_for_mutation", segment.split("@router", 1)[0])

    def test_postgresql_ticket_lock_excludes_nullable_user_joins(self):
        """Regression: PostgreSQL cannot FOR UPDATE a nullable outer join.

        SupportTicket maps both ``user`` and ``assigned_to`` as joined
        relationships.  Compile the exact shared lock query with the
        PostgreSQL dialect so a future eager-loading change cannot silently
        restore ``LEFT OUTER JOIN ... FOR UPDATE`` in close/transfer/claim,
        or in AI response persistence.
        """
        db = SessionLocal()
        try:
            statement = _chatbot_ticket_lock_query(db, self.existing_ticket_id).statement
            sql = str(
                statement.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
            new_session_statement = chatbot_routes._active_chatbot_tickets_for_new_session_query(db, 121).statement
            new_session_sql = str(
                new_session_statement.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
        finally:
            db.close()

        normalized_sql = " ".join(sql.upper().split())
        self.assertIn("FROM SUPPORT_TICKETS", normalized_sql)
        self.assertIn("FOR UPDATE OF SUPPORT_TICKETS", normalized_sql)
        self.assertNotIn("LEFT OUTER JOIN", normalized_sql)
        self.assertNotIn("JOIN USERS", normalized_sql)

        normalized_new_session_sql = " ".join(new_session_sql.upper().split())
        self.assertIn("FOR UPDATE OF SUPPORT_TICKETS", normalized_new_session_sql)
        self.assertNotIn("LEFT OUTER JOIN", normalized_new_session_sql)
        self.assertNotIn("JOIN USERS", normalized_new_session_sql)

        # The AI response race guard must share the exact helper rather than
        # reintroducing its own unsafe SupportTicket.with_for_update query.
        routes_source = (Path(__file__).parents[1] / "app" / "routes_chatbot.py").read_text(encoding="utf-8")
        provider_segment = routes_source[
            routes_source.index("def _provider_answer_for_message("):
            routes_source.index("def _assistant_attempt_count(")
        ]
        self.assertIn("lock_chatbot_ticket_for_update", provider_segment)
        self.assertNotIn(".with_for_update()", provider_segment)


if __name__ == "__main__":
    unittest.main()
