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
from unittest import mock

from fastapi import HTTPException, Request
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
          storage_backend VARCHAR(16),
          storage_key VARCHAR(255),
          storage_resource_type VARCHAR(16),
          storage_delivery_type VARCHAR(16),
          storage_format VARCHAR(32),
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
    # Unit tests intentionally exercise the local path unless a test opts in
    # to its mocked private Cloudinary provider below.
    os.environ["SEVOR_MESSAGE_ATTACHMENT_STORAGE"] = "local"
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("SEVOR_AI_MODEL", None)

import app.main as main_module
import app.message_attachments as attachment_service
from app.database import SessionLocal
from app.models import Item, Message, MessageAttachment, MessageThread, User
from app.models_metrics import OnlineSession


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
OGG_BYTES = b"OggS" + b"\x00" * 64
MP4_BYTES = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 64


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

    def test_message_template_keeps_media_ui_responsive_hooks(self):
        """Guard UI-only direct-message refinements without touching storage."""
        template = (Path(__file__).resolve().parents[1] / "app" / "templates" / "thread.html").read_text(encoding="utf-8")
        for required in (
            'id="conversationRecordingWave"',
            "window.AudioContext || window.webkitAudioContext",
            "context.createMediaStreamSource(stream)",
            "context.createAnalyser()",
            "recordingAnalyser.getByteFrequencyData(recordingWaveData)",
            "MediaRecorder.isTypeSupported(type) && canPlayVoiceMime(type)",
            "audio.play().catch((error) =>",
            "<source src=\"/messages/{{ thread.id }}/attachments/{{ attachment.id }}\" type=\"{{ attachment.content_type }}\">",
            'form.dataset.recording = \'true\'',
            "conversation-message--me{ padding-left:8%; margin-right:4px; }",
            "aspect-ratio:1 / 1",
            "grid-template-columns:56px minmax(0,1fr) auto",
            "grid-template-columns:minmax(0,1fr)",
            "conversation-composer__preview-track",
            "-webkit-overflow-scrolling:touch",
            "conversation-composer-preview--image",
            "conversation-message__images",
            "nonImageAttachments",
            "Image unavailable",
            "conversation-attachment-image--unavailable",
        ):
            self.assertIn(required, template)

    def test_storage_selector_never_needs_a_render_marker_to_choose_cloudinary(self):
        """A cold production process must not silently fall back to local media."""
        with mock.patch.dict(
            os.environ,
            {"CLOUDINARY_URL": "cloudinary://test-key:test-secret@test-cloud"},
            clear=True,
        ):
            self.assertEqual(attachment_service.message_attachment_storage_backend(), "cloudinary")

        with mock.patch.dict(os.environ, {"RENDER": "true"}, clear=True):
            with self.assertRaises(HTTPException) as unavailable:
                attachment_service.message_attachment_storage_backend()
        self.assertEqual(unavailable.exception.status_code, 503)

        with mock.patch.dict(
            os.environ,
            {
                "RENDER": "true",
                "SEVOR_MESSAGE_ATTACHMENT_STORAGE": "local",
                # A path alone does not prove a persistent Render disk.
                "SEVOR_PRIVATE_UPLOADS_DIR": "/possibly-ephemeral/uploads",
            },
            clear=True,
        ):
            with self.assertRaises(HTTPException) as local_on_ephemeral_render:
                attachment_service.message_attachment_storage_backend()
        self.assertEqual(local_on_ephemeral_render.exception.status_code, 503)

    def test_cloudinary_url_configures_the_private_attachment_adapter(self):
        """Render may provide CLOUDINARY_URL instead of separate variables."""
        with (
            mock.patch.dict(
                os.environ,
                {"CLOUDINARY_URL": "cloudinary://url-key:url-secret@url-cloud"},
                clear=True,
            ),
            mock.patch.object(attachment_service.cloudinary, "config") as configure,
        ):
            attachment_service._configure_cloudinary()
        configure.assert_called_once_with(
            cloud_name="url-cloud",
            api_key="url-key",
            api_secret="url-secret",
            secure=True,
        )

    def test_cloudinary_verification_failure_rolls_back_message_and_attachment(self):
        """Provider upload is not a success until Admin metadata matches it."""
        thread_id = self._thread()
        owner = TestClient(main_module.app)
        _login(owner, self.owner_id)
        destroyed = []

        def fake_upload(_source, **options):
            return {"public_id": options["public_id"]}

        def fake_resource(public_id, **options):
            return {
                "public_id": public_id,
                "resource_type": options["resource_type"],
                "type": options["type"],
                # Intentionally differs from the staged file size.
                "bytes": len(PNG_BYTES) + 1,
            }

        def fake_destroy(public_id, **_options):
            destroyed.append(public_id)
            return {"result": "ok"}

        cloudinary_env = {
            "SEVOR_MESSAGE_ATTACHMENT_STORAGE": "cloudinary",
            "CLOUDINARY_CLOUD_NAME": "test-cloud",
            "CLOUDINARY_API_KEY": "test-key",
            "CLOUDINARY_API_SECRET": "test-secret",
        }
        with (
            mock.patch.dict(os.environ, cloudinary_env, clear=False),
            mock.patch.object(attachment_service.cloudinary.uploader, "upload", side_effect=fake_upload),
            mock.patch.object(attachment_service.cloudinary.api, "resource", side_effect=fake_resource),
            mock.patch.object(attachment_service.cloudinary.uploader, "destroy", side_effect=fake_destroy),
        ):
            response = self._send(
                owner,
                thread_id,
                key="cloud-verification-mismatch-001",
                files=[("attachments", ("proof.png", PNG_BYTES, "image/png"))],
            )

        self.assertEqual(response.status_code, 503, response.text)
        self.assertTrue(destroyed)
        db = SessionLocal()
        try:
            self.assertEqual(db.query(Message).filter(Message.thread_id == thread_id).count(), 0)
            self.assertEqual(db.query(MessageAttachment).filter(MessageAttachment.thread_id == thread_id).count(), 0)
        finally:
            db.close()

    def test_image_only_message_renders_without_a_colored_bubble(self):
        thread_id = self._thread()
        owner = TestClient(main_module.app)
        _login(owner, self.owner_id)
        sent = self._send(
            owner,
            thread_id,
            key="direct-image-only-render-001",
            files=[("attachments", ("proof.png", PNG_BYTES, "image/png"))],
        )
        self.assertEqual(sent.status_code, 201, sent.text)
        message_id = sent.json()["message"]["id"]
        page = owner.get(f"/messages/{thread_id}")
        self.assertEqual(page.status_code, 200, page.text)
        marker = f'data-message-id="{message_id}"'
        start = page.text.find(marker)
        self.assertNotEqual(start, -1, page.text)
        next_message = page.text.find('data-message-id="', start + len(marker))
        typing_mount = page.text.find('<div id="typingMount"', start)
        ends = [position for position in (next_message, typing_mount) if position != -1]
        row = page.text[start:min(ends)] if ends else page.text[start:]
        self.assertIn('conversation-message__images', row)
        self.assertNotIn('conversation-bubble ', row)

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

    def test_mp4_voice_mime_and_extension_are_preserved(self):
        """Safari-style audio/mp4 uploads must never be renamed as WebM."""
        thread_id = self._thread()
        owner = TestClient(main_module.app)
        _login(owner, self.owner_id)

        sent = self._send(
            owner,
            thread_id,
            key="direct-safari-mp4-voice-001",
            files={"voice": ("voice-message.m4a", MP4_BYTES, "audio/mp4")},
        )
        self.assertEqual(sent.status_code, 201, sent.text)
        attachment_id = sent.json()["message"]["attachments"][0]["id"]

        db = SessionLocal()
        try:
            attachment = db.get(MessageAttachment, attachment_id)
            self.assertEqual(attachment.kind, "voice")
            self.assertEqual(attachment.original_name, "voice-message.m4a")
            self.assertEqual(attachment.content_type, "audio/mp4")
            self.assertTrue(attachment.stored_name.endswith(".m4a"))
        finally:
            db.close()

    def test_cloudinary_private_media_survives_a_new_release_filesystem(self):
        """Durable media must not depend on the worker's local upload directory."""
        thread_id = self._thread()
        owner = TestClient(main_module.app)
        participant = TestClient(main_module.app)
        outsider = TestClient(main_module.app)
        _login(owner, self.owner_id)
        _login(participant, self.participant_id)
        _login(outsider, self.outsider_id)

        objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        signed_urls: dict[str, tuple[str, str]] = {}
        staged_suffixes: list[str] = []
        signed_counter = 0

        class FakeProviderResponse:
            def __init__(self, status_code: int, data: bytes = b""):
                self.status_code = status_code
                self._data = data

            def iter_content(self, chunk_size: int):
                for start in range(0, len(self._data), max(1, chunk_size)):
                    yield self._data[start:start + max(1, chunk_size)]

            def close(self):
                return None

        def fake_upload(source, **options):
            payload = source.read()
            suffix = Path(str(source.name)).suffix.lower()
            staged_suffixes.append(suffix)
            objects[(options["resource_type"], options["public_id"])] = (payload, suffix.lstrip("."))
            return {
                "public_id": options["public_id"],
                "resource_type": options["resource_type"],
                "type": options["type"],
                "bytes": len(payload),
            }

        def fake_resource(public_id, **options):
            object_data = objects.get((options["resource_type"], public_id))
            if object_data is None:
                raise RuntimeError("not found")
            payload, provider_format = object_data
            return {
                "public_id": public_id,
                "resource_type": options["resource_type"],
                "type": options["type"],
                "bytes": len(payload),
                "format": provider_format,
                "asset_id": f"asset-{public_id.rsplit('/', 1)[-1]}",
            }

        def fake_private_download_url(public_id, _format, **options):
            nonlocal signed_counter
            signed_counter += 1
            url = f"https://private-provider.test/download/{signed_counter}"
            signed_urls[url] = (options["resource_type"], public_id)
            return url

        def fake_get(url, **_kwargs):
            reference = signed_urls.get(url)
            object_data = objects.get(reference) if reference else None
            data = object_data[0] if object_data else None
            return FakeProviderResponse(200, data) if data is not None else FakeProviderResponse(404)

        cloudinary_env = {
            "SEVOR_MESSAGE_ATTACHMENT_STORAGE": "cloudinary",
            "CLOUDINARY_CLOUD_NAME": "test-cloud",
            "CLOUDINARY_API_KEY": "test-key",
            "CLOUDINARY_API_SECRET": "test-secret",
        }
        with (
            mock.patch.dict(os.environ, cloudinary_env, clear=False),
            mock.patch.object(attachment_service.cloudinary.uploader, "upload", side_effect=fake_upload),
            mock.patch.object(attachment_service.cloudinary.api, "resource", side_effect=fake_resource),
            mock.patch.object(attachment_service.cloudinary.utils, "private_download_url", side_effect=fake_private_download_url),
            mock.patch.object(attachment_service.requests, "get", side_effect=fake_get),
        ):
            sent = [
                self._send(owner, thread_id, key="durable-jpeg", files=[("attachments", ("photo.jpg", JPEG_BYTES, "image/jpeg"))]),
                self._send(owner, thread_id, key="durable-png", files=[("attachments", ("photo.png", PNG_BYTES, "image/png"))]),
                self._send(owner, thread_id, key="durable-pdf", files=[("attachments", ("receipt.pdf", PDF_BYTES, "application/pdf"))]),
                self._send(owner, thread_id, key="durable-voice", files={"voice": ("voice.ogg", OGG_BYTES, "audio/ogg")}),
            ]
            for response in sent:
                self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(staged_suffixes, [".jpg", ".png", ".pdf", ".ogg"])
            attachments = [response.json()["message"]["attachments"][0] for response in sent]

            db = SessionLocal()
            try:
                rows = [db.get(MessageAttachment, int(item["id"])) for item in attachments]
                self.assertTrue(all(row and row.stored_name.startswith("cld1:") for row in rows))
                self.assertTrue(all(row.storage_backend == "cloudinary" for row in rows))
                self.assertTrue(all(row.storage_key and row.storage_key.startswith("sevor_private/") for row in rows))
                self.assertEqual([row.storage_resource_type for row in rows], ["image", "image", "image", "video"])
                self.assertEqual([row.storage_format for row in rows], ["jpg", "png", "pdf", "ogg"])
                self.assertTrue(all(row.storage_delivery_type == "private" for row in rows))
                for row in rows:
                    with self.assertRaises(HTTPException):
                        attachment_service.message_attachment_path(row)
            finally:
                db.close()

            # A deployment config change must not make existing provider
            # references depend on rebuilding the original folder from env.
            os.environ["SEVOR_MESSAGE_CLOUDINARY_FOLDER"] = "different-folder-after-upload"

            # Simulate a redeploy: the new worker has no previous local root.
            old_roots = (
                attachment_service.MESSAGE_ATTACHMENT_ROOT,
                attachment_service.MESSAGE_ATTACHMENT_STAGING_ROOT,
            )
            try:
                shutil.rmtree(old_roots[0], ignore_errors=True)
                attachment_service.MESSAGE_ATTACHMENT_ROOT = self.private_root / "new-release" / "message_attachments"
                attachment_service.MESSAGE_ATTACHMENT_STAGING_ROOT = attachment_service.MESSAGE_ATTACHMENT_ROOT / ".staging"

                reloaded = TestClient(main_module.app)
                _login(reloaded, self.participant_id)
                page = reloaded.get(f"/messages/{thread_id}")
                self.assertEqual(page.status_code, 200, page.text)
                expected_payloads = (JPEG_BYTES, PNG_BYTES, PDF_BYTES, OGG_BYTES)
                for item, expected in zip(attachments, expected_payloads):
                    self.assertIn(item["url"], page.text)
                    download = reloaded.get(item["url"])
                    self.assertEqual(download.status_code, 200, download.text)
                    self.assertEqual(download.content, expected)
                    self.assertEqual(download.headers["cache-control"], "private, no-store")
                    self.assertEqual(download.headers["x-content-type-options"], "nosniff")
                    self.assertNotIn("private-provider.test", str(download.url))

                # A third party still cannot turn a stable attachment route
                # into a provider download capability.
                self.assertEqual(outsider.get(attachments[0]["url"]).status_code, 404)

                # A genuinely missing durable object becomes a typed error;
                # the page's image fallback handles it without a broken icon.
                objects.clear()
                missing = reloaded.get(attachments[0]["url"])
                self.assertEqual(missing.status_code, 410, missing.text)
            finally:
                (attachment_service.MESSAGE_ATTACHMENT_ROOT, attachment_service.MESSAGE_ATTACHMENT_STAGING_ROOT) = old_roots

    def test_legacy_cloudinary_row_hydrates_to_an_exact_reference_before_folder_changes(self):
        """A prior ``cld1:`` row becomes restart-safe on its first authorized read."""
        thread_id = self._thread()
        token = "a" * 32
        stored_name = f"cld1:v:{token}.ogg"
        expected_public_id = f"legacy-direct-messages/{token}"
        voice_bytes = OGG_BYTES

        db = SessionLocal()
        try:
            message = Message(
                thread_id=thread_id,
                sender_id=self.owner_id,
                body="",
                is_read=False,
                created_at=datetime.utcnow(),
            )
            db.add(message)
            db.flush()
            attachment = MessageAttachment(
                thread_id=thread_id,
                message_id=message.id,
                uploader_id=self.owner_id,
                kind="voice",
                original_name="recording.ogg",
                stored_name=stored_name,
                storage_backend="cloudinary",
                content_type="audio/ogg",
                size_bytes=len(voice_bytes),
                created_at=datetime.utcnow(),
            )
            db.add(attachment)
            db.commit()
            attachment_id = attachment.id
        finally:
            db.close()

        provider_ranges = []

        class FakeProviderResponse:
            def __init__(self, status_code=200, payload=voice_bytes, headers=None):
                self.status_code = status_code
                self.payload = payload
                self.headers = headers or {}

            def iter_content(self, chunk_size=None):
                yield self.payload

            def close(self):
                return None

        def fake_resource(public_id, **options):
            self.assertEqual(public_id, expected_public_id)
            self.assertEqual(options["resource_type"], "video")
            self.assertEqual(options["type"], "private")
            return {
                "public_id": public_id,
                "resource_type": "video",
                "type": "private",
                "bytes": len(voice_bytes),
                "format": "ogg",
            }

        def fake_private_download_url(public_id, provider_format, **options):
            self.assertEqual(public_id, expected_public_id)
            self.assertEqual(provider_format, "ogg")
            self.assertEqual(options["resource_type"], "video")
            return "https://private-provider.test/legacy-voice"

        def fake_get(_url, **options):
            requested_range = ((options.get("headers") or {}).get("Range"))
            provider_ranges.append(requested_range)
            if requested_range == "bytes=0-7":
                return FakeProviderResponse(
                    status_code=206,
                    payload=voice_bytes[:8],
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Range": f"bytes 0-7/{len(voice_bytes)}",
                        "Content-Length": "8",
                    },
                )
            return FakeProviderResponse(headers={"Content-Length": str(len(voice_bytes))})

        cloudinary_env = {
            "SEVOR_MESSAGE_ATTACHMENT_STORAGE": "cloudinary",
            "SEVOR_MESSAGE_CLOUDINARY_FOLDER": "legacy-direct-messages",
            "CLOUDINARY_CLOUD_NAME": "test-cloud",
            "CLOUDINARY_API_KEY": "test-key",
            "CLOUDINARY_API_SECRET": "test-secret",
        }
        participant = TestClient(main_module.app)
        _login(participant, self.participant_id)
        with (
            mock.patch.dict(os.environ, cloudinary_env, clear=False),
            mock.patch.object(attachment_service.cloudinary.api, "resource", side_effect=fake_resource) as resource,
            mock.patch.object(attachment_service.cloudinary.utils, "private_download_url", side_effect=fake_private_download_url),
            mock.patch.object(attachment_service.requests, "get", side_effect=fake_get),
        ):
            url = f"/messages/{thread_id}/attachments/{attachment_id}"
            first = participant.get(url)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.content, voice_bytes)

            db = SessionLocal()
            try:
                hydrated = db.get(MessageAttachment, attachment_id)
                self.assertEqual(hydrated.storage_key, expected_public_id)
                self.assertEqual(hydrated.storage_resource_type, "video")
                self.assertEqual(hydrated.storage_delivery_type, "private")
                self.assertEqual(hydrated.storage_format, "ogg")
            finally:
                db.close()

            # A new release can change its default folder after this one-time
            # hydration without breaking the existing provider record.
            os.environ["SEVOR_MESSAGE_CLOUDINARY_FOLDER"] = "wrong-folder-after-restart"
            second = participant.get(url)
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(second.content, voice_bytes)
            self.assertEqual(resource.call_count, 1)

            ranged = participant.get(url, headers={"Range": "bytes=0-7"})
            self.assertEqual(ranged.status_code, 206, ranged.text)
            self.assertEqual(ranged.content, voice_bytes[:8])
            self.assertEqual(ranged.headers.get("accept-ranges"), "bytes")
            self.assertEqual(ranged.headers.get("content-range"), f"bytes 0-7/{len(voice_bytes)}")
            self.assertEqual(ranged.headers.get("content-length"), "8")
            self.assertEqual(ranged.headers.get("content-type"), "audio/ogg")
            self.assertTrue(ranged.headers.get("content-disposition", "").startswith("inline"))
            self.assertEqual(provider_ranges[-1], "bytes=0-7")

            invalid_range = participant.get(url, headers={"Range": "bytes=0-7,9-10"})
            self.assertEqual(invalid_range.status_code, 416)
            self.assertEqual(provider_ranges[-1], "bytes=0-7")

            outsider = TestClient(main_module.app)
            _login(outsider, self.outsider_id)
            self.assertEqual(outsider.get(url, headers={"Range": "bytes=0-7"}).status_code, 404)

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

    def test_unread_summary_uses_actual_direct_message_read_state(self):
        """The shared nav count follows the existing direct-message lifecycle."""
        thread_id = self._thread()
        owner = TestClient(main_module.app)
        participant = TestClient(main_module.app)
        guest = TestClient(main_module.app)
        _login(owner, self.owner_id)
        _login(participant, self.participant_id)

        # Guests receive the safe empty shape and never need private data.
        self.assertEqual(guest.get("/api/unread_summary").json(), {"total": 0, "threads": []})

        for index in range(3):
            sent = self._send(
                participant,
                thread_id,
                body=f"Unread message {index}",
                key=f"global-unread-summary-{index}",
            )
            self.assertEqual(sent.status_code, 201, sent.text)

        before_read = owner.get("/api/unread_summary")
        self.assertEqual(before_read.status_code, 200, before_read.text)
        self.assertEqual(before_read.json()["total"], 3)
        self.assertEqual(before_read.json()["threads"][0]["thread_id"], thread_id)
        self.assertEqual(before_read.json()["threads"][0]["count"], 3)

        # Opening the actual conversation, not the inbox landing page, is what
        # preserves the existing read-receipt semantics and clears the count.
        self.assertEqual(owner.get(f"/messages/{thread_id}").status_code, 200)
        self.assertEqual(owner.get("/api/unread_summary").json()["total"], 0)

        later = self._send(
            participant,
            thread_id,
            body="Unread until the visible conversation poll runs",
            key="global-unread-summary-poll",
        )
        self.assertEqual(later.status_code, 201, later.text)
        self.assertEqual(owner.get("/api/unread_summary").json()["total"], 1)

        self.assertEqual(
            owner.get(f"/messages/{thread_id}/poll", params={"after": 999999}).status_code,
            200,
        )
        self.assertEqual(owner.get("/api/unread_summary").json()["total"], 0)

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
