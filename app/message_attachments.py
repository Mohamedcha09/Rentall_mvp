"""Private, validated media handling for ordinary SEVOR direct messages.

Direct messages are private conversations, so their images, documents, and
voice recordings must never be placed under the application's public
``/uploads`` mount.  This deliberately follows the established support-ticket
attachment pattern while keeping direct-message records and files separate.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from .models import MessageAttachment
from .support_attachments import PRIVATE_UPLOAD_ROOT


MESSAGE_ATTACHMENT_ROOT = PRIVATE_UPLOAD_ROOT / "message_attachments"
MESSAGE_ATTACHMENT_STAGING_ROOT = MESSAGE_ATTACHMENT_ROOT / ".staging"

MAX_ATTACHMENTS_PER_MESSAGE = 4
DEFAULT_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_VOICE_BYTES = 12 * 1024 * 1024
CHUNK_SIZE = 64 * 1024

# Browser selection is intentionally narrow.  The server validates the
# declared MIME, file extension, and content signature; ``accept`` is only a
# usability hint.
ALLOWED_ATTACHMENT_TYPES: dict[str, set[str]] = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
    ".pdf": {"application/pdf"},
}
ALLOWED_VOICE_TYPES: dict[str, set[str]] = {
    ".webm": {"audio/webm"},
    ".ogg": {"audio/ogg", "application/ogg"},
    ".m4a": {"audio/mp4", "audio/x-m4a"},
    ".mp4": {"audio/mp4"},
}
IMAGE_ATTACHMENT_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def _bounded_env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


def max_attachment_bytes() -> int:
    return _bounded_env_int(
        "SEVOR_MESSAGE_ATTACHMENT_MAX_BYTES",
        DEFAULT_MAX_ATTACHMENT_BYTES,
        minimum=256 * 1024,
        maximum=25 * 1024 * 1024,
    )


def max_voice_bytes() -> int:
    return _bounded_env_int(
        "SEVOR_MESSAGE_VOICE_MAX_BYTES",
        DEFAULT_MAX_VOICE_BYTES,
        minimum=256 * 1024,
        maximum=25 * 1024 * 1024,
    )


def max_attachments_per_message() -> int:
    return _bounded_env_int(
        "SEVOR_MESSAGE_MAX_ATTACHMENTS",
        MAX_ATTACHMENTS_PER_MESSAGE,
        minimum=1,
        maximum=8,
    )


def allowed_attachment_accept_value() -> str:
    return ",".join(sorted({mime for values in ALLOWED_ATTACHMENT_TYPES.values() for mime in values}))


def allowed_voice_accept_value() -> str:
    return ",".join(sorted({mime for values in ALLOWED_VOICE_TYPES.values() for mime in values}))


def _display_name(value: str | None, *, fallback: str) -> str:
    raw = Path(value or fallback).name.replace("\x00", "")
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", raw).strip().strip(".")
    return (cleaned or fallback)[:180]


def _declared_content_type(upload: UploadFile) -> str:
    return (upload.content_type or "").split(";", 1)[0].strip().lower()


def _validate_signature(path: Path, extension: str, *, kind: str) -> None:
    with path.open("rb") as source:
        header = source.read(32)

    valid = (
        (extension in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
        or (extension == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension == ".webp" and len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP")
        or (extension == ".pdf" and header.startswith(b"%PDF-"))
        or (kind == "voice" and extension == ".webm" and header.startswith(b"\x1aE\xdf\xa3"))
        or (kind == "voice" and extension == ".ogg" and header.startswith(b"OggS"))
        or (kind == "voice" and extension in {".m4a", ".mp4"} and len(header) >= 12 and header[4:8] == b"ftyp")
    )
    if not valid:
        raise HTTPException(status_code=422, detail="The file content does not match its declared type.")


def _validated_duration_ms(value: str | int | None) -> int | None:
    """Keep a bounded display hint without treating client metadata as trust.

    The persisted audio bytes remain the source used by the browser for
    playback after refresh.  We do not claim server-side media inspection
    without adding a transcoder/metadata dependency to production.
    """
    if value in (None, ""):
        return None
    try:
        duration = int(float(value))
    except (TypeError, ValueError):
        return None
    return duration if 0 < duration <= 10 * 60 * 1000 else None


@dataclass
class StagedMessageAttachment:
    temp_path: Path
    display_name: str
    extension: str
    content_type: str
    size_bytes: int
    kind: str
    duration_ms: int | None = None


def cleanup_staged_message_attachments(staged: Iterable[StagedMessageAttachment]) -> None:
    for item in staged:
        try:
            item.temp_path.unlink(missing_ok=True)
        except OSError:
            pass


async def _stage_one(
    upload: UploadFile,
    *,
    kind: str,
    size_limit: int,
    duration_ms: int | None = None,
) -> StagedMessageAttachment:
    display_name = _display_name(upload.filename, fallback="voice-message.webm" if kind == "voice" else "attachment")
    extension = Path(display_name).suffix.lower()
    content_type = _declared_content_type(upload)
    allowed_types = ALLOWED_VOICE_TYPES.get(extension) if kind == "voice" else ALLOWED_ATTACHMENT_TYPES.get(extension)
    if not allowed_types or content_type not in allowed_types:
        detail = (
            "Voice messages must use a supported WebM, Ogg, or MP4 audio format."
            if kind == "voice"
            else "Only JPEG, PNG, WebP, and PDF attachments are allowed."
        )
        raise HTTPException(status_code=422, detail=detail)

    MESSAGE_ATTACHMENT_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", delete=False, dir=MESSAGE_ATTACHMENT_STAGING_ROOT, prefix="message-"
    )
    temp_path = Path(handle.name)
    size_bytes = 0
    try:
        try:
            while chunk := await upload.read(CHUNK_SIZE):
                size_bytes += len(chunk)
                if size_bytes > size_limit:
                    maximum_mb = max(1, size_limit // (1024 * 1024))
                    raise HTTPException(
                        status_code=422,
                        detail=f"Each {'voice message' if kind == 'voice' else 'attachment'} must be {maximum_mb} MB or smaller.",
                    )
                handle.write(chunk)
        finally:
            # Close before cleanup: Windows does not allow deleting an open
            # temporary file, and local development uses that filesystem too.
            handle.close()
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    if not size_bytes:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=422, detail="Empty attachments are not allowed.")
    try:
        _validate_signature(temp_path, extension, kind=kind)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return StagedMessageAttachment(
        temp_path=temp_path,
        display_name=display_name,
        extension=extension,
        content_type=content_type,
        size_bytes=size_bytes,
        kind=kind,
        duration_ms=duration_ms if kind == "voice" else None,
    )


async def stage_message_attachments(
    uploads: Sequence[UploadFile] | None,
    *,
    voice_upload: UploadFile | None = None,
    voice_duration_ms: str | int | None = None,
) -> list[StagedMessageAttachment]:
    """Validate and stage a bounded private direct-message upload set.

    A message can contain text plus normal files, or text plus one voice
    recording.  Keeping recorded audio separate from arbitrary attachments
    prevents accidental mixed MIME flows and gives the sender a clear audio
    lifecycle in the composer.
    """
    normal_uploads = [upload for upload in (uploads or []) if upload and (upload.filename or "").strip()]
    has_voice = bool(voice_upload and (voice_upload.filename or "").strip())
    all_uploads = [*normal_uploads, *([voice_upload] if has_voice and voice_upload else [])]
    staged: list[StagedMessageAttachment] = []
    try:
        if len(normal_uploads) > max_attachments_per_message():
            raise HTTPException(
                status_code=422,
                detail=f"You can attach up to {max_attachments_per_message()} files to one message.",
            )
        if normal_uploads and has_voice:
            raise HTTPException(status_code=422, detail="Send a voice recording separately from file attachments.")
        for upload in normal_uploads:
            staged.append(await _stage_one(upload, kind="image" if Path(upload.filename or "").suffix.lower() in IMAGE_ATTACHMENT_EXTENSIONS else "file", size_limit=max_attachment_bytes()))
        if has_voice and voice_upload:
            staged.append(
                await _stage_one(
                    voice_upload,
                    kind="voice",
                    size_limit=max_voice_bytes(),
                    duration_ms=_validated_duration_ms(voice_duration_ms),
                )
            )
    except Exception:
        cleanup_staged_message_attachments(staged)
        raise
    finally:
        for upload in all_uploads:
            try:
                await upload.close()
            except Exception:
                pass
    return staged


def persist_staged_message_attachments(
    db: Session,
    *,
    thread_id: int,
    message_id: int,
    uploader_id: int,
    staged: Sequence[StagedMessageAttachment],
) -> list[MessageAttachment]:
    if not staged:
        return []
    MESSAGE_ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[MessageAttachment] = []
    for item in staged:
        stored_name = f"{uuid.uuid4().hex}{item.extension}"
        destination = MESSAGE_ATTACHMENT_ROOT / stored_name
        record = MessageAttachment(
            thread_id=thread_id,
            message_id=message_id,
            uploader_id=uploader_id,
            kind=item.kind,
            original_name=item.display_name,
            stored_name=stored_name,
            content_type=item.content_type,
            size_bytes=item.size_bytes,
            duration_ms=item.duration_ms,
        )
        db.add(record)
        db.flush()
        os.replace(item.temp_path, destination)
        records.append(record)
    return records


def remove_saved_message_attachment_files(records: Iterable[MessageAttachment | str]) -> None:
    for record in records:
        try:
            raw_name = record if isinstance(record, str) else (record.stored_name or "")
            stored_name = Path(raw_name).name
            if stored_name:
                (MESSAGE_ATTACHMENT_ROOT / stored_name).unlink(missing_ok=True)
        except OSError:
            pass


def message_attachment_path(attachment: MessageAttachment) -> Path:
    stored_name = Path(attachment.stored_name or "").name
    if not stored_name or stored_name != attachment.stored_name:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = MESSAGE_ATTACHMENT_ROOT / stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment not found")
    return path


def serialize_message_attachment(attachment: MessageAttachment, *, thread_id: int) -> dict[str, object]:
    kind = str(attachment.kind or "file")
    return {
        "id": attachment.id,
        "name": attachment.original_name,
        "content_type": attachment.content_type,
        "size_bytes": int(attachment.size_bytes or 0),
        "kind": kind,
        "is_image": kind == "image",
        "is_voice": kind == "voice",
        "duration_ms": int(attachment.duration_ms) if attachment.duration_ms else None,
        "url": f"/messages/{thread_id}/attachments/{attachment.id}",
    }
