"""Focused regressions for private direct-message media and presence.

The suite uses its own SQLite file so these tests never touch the user's app
database or the private production upload directory.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient


TEST_DB = Path(tempfile.gettempdir()) / f"sevor_direct_messages_{os.getpid()}_{uuid.uuid4().hex}.sqlite3"
APP_DATABASE_WAS_PRELOADED = "app.database" in sys.modules


def _bootstrap_schema(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE users (
          id INTEGER PRIMARY KEY,
          first_name VARCHAR(100) NOT NULL,
          last_name VARCHAR(100) NOT NULL,
          email VARCHAR(200) NOT NULL UNIQUE,
          phone VARCHAR(50) NOT NULL,
          password_hash VARCHAR(255) NOT NULL,
          role VARCHAR(20), status VARCHAR(20), is_verified BOOLEAN,
          avatar_path VARCHAR(500), created_at TIMESTAMP
        );
        CREATE TABLE message_threads (
          id INTEGER PRIMARY KEY,
          user_a_id INTEGER NOT NULL,
          user_b_id INTEGER NOT NULL,
          item_id INTEGER,
          created_at TIMESTAMP,
          last_message_at TIMESTAMP
        );
        CREATE TABLE messages (
          id INTEGER PRIMARY KEY,
          thread_id INTEGER NOT NULL,
          sender_id INTEGER NOT NULL,
          body TEXT NOT NULL,
          created_at TIMESTAMP,
          is_read BOOLEAN DEFAULT 0,
          read_at TIMESTAMP,
          client_message_id VARCHAR(72)
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
          created_at TIMESTAMP NOT NULL
        );
        CREATE TABLE online_sessions (
          session_id VARCHAR(64) PRIMARY KEY,
          user_id INTEGER,
          ip VARCHAR(64),
          user_agent VARCHAR(255),
          first_seen TIMESTAMP NOT NULL,
          last_seen TIMESTAMP NOT NULL
        );
        """
    )
    connection.commit()
    connection.close()


if not APP_DATABASE_WAS_PRELOADED:
    _bootstrap_schema(TEST_DB)
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
    os.environ["SECRET_KEY"] = "test-only-direct-message-secret"
    os.environ["COOKIE_DOMAIN"] = "testserver.local"
    os.environ["HTTPS_ONLY_COOKIES"] = "0"
    os.environ["SITE_URL"] = ""
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("SEVOR_AI_MODEL", None)

import app.main as main_module
import app.message_attachments as attachment_service
from app.database import SessionLocal
from app.models import Item, Message, MessageAttachment, MessageThread, User
from app.models_metrics import OnlineSession


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
OGG_BYTES = b"OggS" + b"\x00" * 64


if not APP_DATABASE_WAS_PRELOADED:
    main_module._fx_schedule_daily_sync = lambda: None

    @main_module.app.get("/_test_direct_messages_login/{user_id}")
    def _test_direct_messages_login(user_id: int, request: Request):
        request.session["user"] = {"id": user_id, "status": "approved", "role": "user"}
        return {"ok": True}


def _csrf_from_thread(client: TestClient, thread_id: int) -> tuple[str, str]:
    page = client.get(f"/messages/{thread_id}")
    assert page.status_code == 200, page.text[:1000]
    token = re.search(r'id="conversationCsrf" value="([^"]+)"', page.text)
    cursor = re.search(r"let receiptCursor = (?P<value>[^;]+);", page.text)
    assert token and cursor, page.text[:3000]
    return token.group(1), json.loads(cursor.group("value"))


def _login(client: TestClient, user_id: int) -> None:
    response = client.get(f"/_test_direct_messages_login/{user_id}")
    assert response.status_code == 200


@unittest.skipIf(
    APP_DATABASE_WAS_PRELOADED,
    "Run this isolated direct-message suite in its own process so it never touches another suite's database.",
)
class DirectMessageMediaTests(unittest.TestCase):
    owner_id = 701
    participant_id = 702
    outsider_id = 703

    @classmethod
    def setUpClass(cls):
        cls.private_root = Path(tempfile.mkdtemp(prefix="sevor-direct-message-tests-"))
        cls._old_roots = (
            attachment_service.MESSAGE_ATTACHMENT_ROOT,
            attachment_service.MESSAGE_ATTACHMENT_STAGING_ROOT,
        )
        attachment_service.MESSAGE_ATTACHMENT_ROOT = cls.private_root / "message_attachments"
        attachment_service.MESSAGE_ATTACHMENT_STAGING_ROOT = attachment_service.MESSAGE_ATTACHMENT_ROOT / ".staging"

        db = SessionLocal()
        try:
            for user_id, first_name in (
                (cls.owner_id, "Owner"),
                (cls.participant_id, "Participant"),
                (cls.outsider_id, "Outside"),
            ):
                if not db.get(User, user_id):
                    db.add(
                        User(
                            id=user_id,
                            first_name=first_name,
                            last_name="User",
                            email=f"{first_name.lower()}-{user_id}@example.test",
                            phone=str(user_id),
                            password_hash="test-only",
                            role="user",
                            status="approved",
                            is_verified=True,
                        )
                    )
            db.commit()
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        (attachment_service.MESSAGE_ATTACHMENT_ROOT, attachment_service.MESSAGE_ATTACHMENT_STAGING_ROOT) = cls._old_roots
        shutil.rmtree(cls.private_root, ignore_errors=True)

    def setUp(self):
        db = SessionLocal()
        try:
            db.query(MessageAttachment).delete(synchronize_session=False)
            db.query(Message).delete(synchronize_session=False)
            db.query(MessageThread).delete(synchronize_session=False)
            db.query(OnlineSession).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
        shutil.rmtree(self.private_root, ignore_errors=True)
        self.private_root.mkdir(parents=True, exist_ok=True)

    def _thread(self) -> int:
        db = SessionLocal()
        try:
            thread = MessageThread(
                user_a_id=self.owner_id,
                user_b_id=self.participant_id,
                last_message_at=datetime.utcnow(),
            )
            db.add(thread)
            db.commit()
            return thread.id
        finally:
            db.close()

    def _send(self, client: TestClient, thread_id: int, *, body="", key="direct-message-key-001", files=None, extra=None):
        csrf, _cursor = _csrf_from_thread(client, thread_id)
        data = {"body": body, "csrf_token": csrf, "client_message_id": key}
        if extra:
            data.update(extra)
        return client.post(
            f"/messages/{thread_id}",
            data=data,
            files=files,
            headers={"Accept": "application/json"},
        )

    def test_image_pdf_and_voice_are_private_persistent_and_idempotent(self):
        thread_id = self._thread()
        owner = TestClient(main_module.app)
        participant = TestClient(main_module.app)
        _login(owner, self.owner_id)
        _login(participant, self.participant_id)
        _csrf, receipt_cursor = _csrf_from_thread(owner, thread_id)

        image = self._send(
            owner,
            thread_id,
            body="See this image",
            key="direct-image-message-001",
            files=[("attachments", ("proof.png", PNG_BYTES, "image/png"))],
        )
        self.assertEqual(image.status_code, 201, image.text)
        image_payload = image.json()["message"]
        self.assertEqual(image_payload["body"], "See this image")
        self.assertEqual(image_payload["attachments"][0]["kind"], "image")
        image_url = image_payload["attachments"][0]["url"]
        self.assertNotIn("/uploads/", image_url)

        duplicate = self._send(
            owner,
            thread_id,
            body="See this image",
            key="direct-image-message-001",
            files=[("attachments", ("proof.png", PNG_BYTES, "image/png"))],
        )
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertFalse(duplicate.json()["created"])

        pdf = self._send(
            owner,
            thread_id,
            key="direct-pdf-message-001",
            files=[("attachments", ("receipt.pdf", PDF_BYTES, "application/pdf"))],
        )
        self.assertEqual(pdf.status_code, 201, pdf.text)
        pdf_attachment = pdf.json()["message"]["attachments"][0]
        self.assertEqual(pdf_attachment["kind"], "file")

        voice = self._send(
            owner,
            thread_id,
            key="direct-voice-message-001",
            files={"voice": ("voice-message.ogg", OGG_BYTES, "audio/ogg")},
            extra={"voice_duration_ms": "10000"},
        )
        self.assertEqual(voice.status_code, 201, voice.text)
        voice_attachment = voice.json()["message"]["attachments"][0]
        self.assertEqual(voice_attachment["kind"], "voice")
        # The browser may provide a duration while recording, but the server
        # does not persist client-controlled display metadata.  The real media
        # element calculates it after loading the private audio bytes.
        self.assertIsNone(voice_attachment["duration_ms"])

        db = SessionLocal()
        try:
            self.assertEqual(db.query(Message).filter(Message.thread_id == thread_id).count(), 3)
            self.assertEqual(db.query(MessageAttachment).filter(MessageAttachment.thread_id == thread_id).count(), 3)
            attachment = db.query(MessageAttachment).filter(MessageAttachment.id == image_payload["attachments"][0]["id"]).one()
            self.assertTrue(attachment_service.message_attachment_path(attachment).is_file())
        finally:
            db.close()

        # The other real participant can render and retrieve each persisted
        # media kind after refresh; these are not browser-blob-only messages.
        refreshed = participant.get(f"/messages/{thread_id}")
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn(image_url, refreshed.text)
        self.assertIn(pdf_attachment["url"], refreshed.text)
        self.assertIn(voice_attachment["url"], refreshed.text)
        self.assertIn('controls preload="metadata"', refreshed.text)
        for url, expected in (
            (image_url, PNG_BYTES),
            (pdf_attachment["url"], PDF_BYTES),
            (voice_attachment["url"], OGG_BYTES),
        ):
            downloaded = participant.get(url)
            self.assertEqual(downloaded.status_code, 200)
            self.assertEqual(downloaded.content, expected)
            self.assertEqual(downloaded.headers["cache-control"], "private, no-store")
            self.assertEqual(downloaded.headers["x-content-type-options"], "nosniff")

        sender_refresh = owner.get(f"/messages/{thread_id}")
        self.assertEqual(sender_refresh.status_code, 200)
        self.assertIn(image_url, sender_refresh.text)
        self.assertIn(voice_attachment["url"], sender_refresh.text)

        # Media rows stay in the ordinary Message lifecycle: the participant
        # opening the conversation produces persisted ✓✓ receipts for image,
        # PDF, and voice messages rather than a client-side timeout.
        receipts = owner.get(
            f"/messages/{thread_id}/poll",
            params={"after": 999999, "receipts_after": receipt_cursor},
        ).json()["read_receipts"]
        self.assertEqual(len(receipts), 3)

    def test_rejects_dangerous_content_and_blocks_nonmembers_from_private_routes(self):
        thread_id = self._thread()
        owner = TestClient(main_module.app)
        outsider = TestClient(main_module.app)
        _login(owner, self.owner_id)
        _login(outsider, self.outsider_id)

        missing_csrf = owner.post(
            f"/messages/{thread_id}",
            data={"body": "not accepted", "client_message_id": "direct-missing-csrf-001"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(missing_csrf.status_code, 403)

        # A normal multipart request declares Content-Length.  Reject an
        # impossible payload before the framework attempts ordinary form work.
        oversized = owner.post(
            f"/messages/{thread_id}",
            data={"body": "oversized", "client_message_id": "direct-oversized-message-001"},
            files=[("attachments", ("proof.png", PNG_BYTES, "image/png"))],
            headers={
                "Accept": "application/json",
                "Content-Length": str(attachment_service.max_direct_message_request_bytes() + 1),
            },
        )
        self.assertEqual(oversized.status_code, 413, oversized.text)

        invalid = self._send(
            owner,
            thread_id,
            key="direct-invalid-message-001",
            files=[("attachments", ("not-a-real.png", b"not-a-png", "image/png"))],
        )
        self.assertEqual(invalid.status_code, 422)

        executable = self._send(
            owner,
            thread_id,
            key="direct-exe-message-001",
            files=[("attachments", ("unsafe.exe", b"MZ\x00\x00", "application/octet-stream"))],
        )
        self.assertEqual(executable.status_code, 422)

        valid = self._send(
            owner,
            thread_id,
            key="direct-valid-message-001",
            files=[("attachments", ("proof.png", PNG_BYTES, "image/png"))],
        )
        self.assertEqual(valid.status_code, 201, valid.text)
        url = valid.json()["message"]["attachments"][0]["url"]
        self.assertEqual(outsider.get(url).status_code, 404)
        self.assertEqual(outsider.get(f"/messages/{thread_id}/poll").status_code, 404)
        self.assertEqual(outsider.get(f"/messages/{thread_id}/typing_status").status_code, 404)
        self.assertEqual(outsider.post(f"/messages/{thread_id}/typing", data={"csrf_token": "wrong"}).status_code, 404)

    def test_real_read_receipts_and_authenticated_presence(self):
        thread_id = self._thread()
        owner = TestClient(main_module.app)
        participant = TestClient(main_module.app)
        _login(owner, self.owner_id)
        _login(participant, self.participant_id)
        _csrf, receipt_cursor = _csrf_from_thread(owner, thread_id)

        sent = self._send(owner, thread_id, body="Read this", key="direct-read-message-001")
        self.assertEqual(sent.status_code, 201, sent.text)
        message_id = sent.json()["message"]["id"]
        self.assertFalse(sent.json()["message"]["is_read"])

        # Rendering the participant's real conversation creates the persisted
        # read state used by the current ✓ / ✓✓ UI.
        self.assertEqual(participant.get(f"/messages/{thread_id}").status_code, 200)
        receipt_poll = owner.get(
            f"/messages/{thread_id}/poll",
            params={"after": message_id, "receipts_after": receipt_cursor},
        )
        self.assertEqual(receipt_poll.status_code, 200, receipt_poll.text)
        self.assertIn(message_id, [row["id"] for row in receipt_poll.json()["read_receipts"]])

        # A forged payload identity cannot mark another account online.  The
        # server derives account identity from the authenticated session.
        heartbeat = owner.post(
            "/api/metrics/heartbeat",
            json={"session_id": "owner-presence-session-001", "user_id": self.participant_id},
        )
        self.assertEqual(heartbeat.status_code, 200, heartbeat.text)
        db = SessionLocal()
        try:
            session = db.get(OnlineSession, "owner-presence-session-001")
            self.assertEqual(session.user_id, self.owner_id)
        finally:
            db.close()

        participant_presence = participant.get(f"/messages/{thread_id}/poll", params={"after": 0})
        self.assertEqual(participant_presence.status_code, 200)
        self.assertTrue(participant_presence.json()["presence"]["online"])

        db = SessionLocal()
        try:
            db.get(OnlineSession, "owner-presence-session-001").last_seen = datetime.utcnow() - timedelta(seconds=121)
            db.commit()
        finally:
            db.close()
        offline = participant.get(f"/messages/{thread_id}/poll", params={"after": 0})
        self.assertFalse(offline.json()["presence"]["online"])
        self.assertTrue(offline.json()["presence"]["last_seen"])

    def test_account_deletion_removes_private_media_and_presence_after_commit(self):
        deleting_id, peer_id = 704, 705
        db = SessionLocal()
        try:
            for user_id, first_name in ((deleting_id, "Deleting"), (peer_id, "Peer")):
                db.add(
                    User(
                        id=user_id,
                        first_name=first_name,
                        last_name="User",
                        email=f"{first_name.lower()}-{user_id}@example.test",
                        phone=str(user_id),
                        password_hash="test-only",
                        role="user",
                        status="approved",
                    )
                )
            thread = MessageThread(user_a_id=deleting_id, user_b_id=peer_id, last_message_at=datetime.utcnow())
            db.add(thread)
            db.flush()
            message = Message(thread_id=thread.id, sender_id=deleting_id, body="private file", created_at=datetime.utcnow())
            db.add(message)
            db.flush()
            stored_name = "delete-after-commit.png"
            attachment = MessageAttachment(
                thread_id=thread.id,
                message_id=message.id,
                uploader_id=deleting_id,
                kind="image",
                original_name="private.png",
                stored_name=stored_name,
                content_type="image/png",
                size_bytes=len(PNG_BYTES),
                created_at=datetime.utcnow(),
            )
            db.add(attachment)
            db.add(
                OnlineSession(
                    session_id="delete-account-presence-001",
                    user_id=deleting_id,
                    first_seen=datetime.utcnow(),
                    last_seen=datetime.utcnow(),
                )
            )
            db.commit()
        finally:
            db.close()

        attachment_service.MESSAGE_ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)
        private_path = attachment_service.MESSAGE_ATTACHMENT_ROOT / stored_name
        private_path.write_bytes(PNG_BYTES)
        self.assertTrue(private_path.exists())

        deleting = TestClient(main_module.app)
        _login(deleting, deleting_id)
        response = deleting.post("/account/delete", follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertFalse(private_path.exists())

        db = SessionLocal()
        try:
            self.assertIsNone(db.get(User, deleting_id))
            self.assertEqual(db.query(MessageAttachment).filter(MessageAttachment.stored_name == stored_name).count(), 0)
            self.assertEqual(db.query(OnlineSession).filter(OnlineSession.user_id == deleting_id).count(), 0)
        finally:
            db.close()

    def test_admin_item_deletion_removes_private_direct_media_after_commit(self):
        """A listing cascade must not leave its private message bytes behind."""
        from app.admin_items import delete_item

        db = SessionLocal()
        try:
            item = Item(
                owner_id=self.owner_id,
                title="Deleted listing",
                description="Test-only listing",
                price=0,
                price_per_day=0,
                category="other",
            )
            db.add(item)
            db.flush()
            thread = MessageThread(
                user_a_id=self.owner_id,
                user_b_id=self.participant_id,
                item_id=item.id,
                last_message_at=datetime.utcnow(),
            )
            db.add(thread)
            db.flush()
            message = Message(thread_id=thread.id, sender_id=self.owner_id, body="private image")
            db.add(message)
            db.flush()
            stored_name = "delete-item-after-commit.png"
            db.add(
                MessageAttachment(
                    thread_id=thread.id,
                    message_id=message.id,
                    uploader_id=self.owner_id,
                    kind="image",
                    original_name="private.png",
                    stored_name=stored_name,
                    content_type="image/png",
                    size_bytes=len(PNG_BYTES),
                    created_at=datetime.utcnow(),
                )
            )
            db.commit()

            attachment_service.MESSAGE_ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)
            private_path = attachment_service.MESSAGE_ATTACHMENT_ROOT / stored_name
            private_path.write_bytes(PNG_BYTES)

            request = type("AdminRequest", (), {"session": {"user": {"role": "admin"}}})()
            response = delete_item(item.id, request, db)
            self.assertEqual(response.status_code, 302)
            self.assertFalse(private_path.exists())
            self.assertIsNone(db.get(Item, item.id))
            self.assertEqual(
                db.query(MessageAttachment).filter(MessageAttachment.stored_name == stored_name).count(),
                0,
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
