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
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

try:  # Cloudinary is already used by SEVOR's durable media integrations.
    import cloudinary
    import cloudinary.uploader
    import cloudinary.utils
except ImportError:  # Keep local development usable when the optional SDK is absent.
    cloudinary = None

import requests

from .models import MessageAttachment
from .support_attachments import PRIVATE_UPLOAD_ROOT


MESSAGE_ATTACHMENT_ROOT = PRIVATE_UPLOAD_ROOT / "message_attachments"
MESSAGE_ATTACHMENT_STAGING_ROOT = MESSAGE_ATTACHMENT_ROOT / ".staging"

# ``stored_name`` is an opaque database key, not a user-controlled filename.
# Legacy rows contain a local UUID filename.  New Cloudinary-backed rows keep
# the provider + resource class in the same opaque field, so no schema change
# is needed and legacy files remain readable while they still exist locally.
CLOUDINARY_STORED_NAME_PREFIX = "cld1:"
CLOUDINARY_PRIVATE_FOLDER_DEFAULT = "sevor_private/direct_messages"
CLOUDINARY_PRIVATE_URL_TTL_SECONDS = 5 * 60
CLOUDINARY_DOWNLOAD_TIMEOUT_SECONDS = 30
_CLOUDINARY_REFERENCE_RE = re.compile(r"^cld1:([ivr]):([0-9a-f]{32})(\.[a-z0-9]{1,8})$")
_CLOUDINARY_RESOURCE_BY_CODE = {"i": "image", "v": "video", "r": "raw"}
_CLOUDINARY_CODE_BY_KIND = {"image": "i", "voice": "v", "file": "r"}

MAX_ATTACHMENTS_PER_MESSAGE = 4
DEFAULT_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_VOICE_BYTES = 12 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
MESSAGE_REQUEST_OVERHEAD_BYTES = 512 * 1024

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


def _cloudinary_credentials_present() -> bool:
    return bool(
        cloudinary is not None
        and (os.getenv("CLOUDINARY_CLOUD_NAME") or "").strip()
        and (os.getenv("CLOUDINARY_API_KEY") or "").strip()
        and (os.getenv("CLOUDINARY_API_SECRET") or "").strip()
    )


def _is_render_runtime() -> bool:
    """Recognize Render without making local/test environments remote-backed."""
    return any(
        (os.getenv(name) or "").strip()
        for name in ("RENDER", "RENDER_SERVICE_ID", "RENDER_EXTERNAL_URL")
    )


def message_attachment_storage_backend() -> str:
    """Select the durable backend without silently using ephemeral files in production.

    ``SEVOR_MESSAGE_ATTACHMENT_STORAGE`` can explicitly be ``local`` (for a
    mounted persistent disk) or ``cloudinary``.  On Render, a configured
    Cloudinary account is selected automatically.  Local development remains
    filesystem-backed by default, so tests and offline work never upload data.
    """
    configured = (os.getenv("SEVOR_MESSAGE_ATTACHMENT_STORAGE") or "").strip().lower()
    if configured in {"local", "filesystem"}:
        return "local"
    if configured in {"cloudinary", "cloud"}:
        if not _cloudinary_credentials_present():
            raise HTTPException(status_code=503, detail="Private attachment storage is not configured.")
        return "cloudinary"
    if configured:
        raise HTTPException(status_code=503, detail="Private attachment storage is not configured.")

    if _is_render_runtime():
        # Do not fall back to Render's release filesystem when Cloudinary is
        # absent: accepting an upload that will disappear on redeploy is worse
        # than returning a clear, retryable storage configuration failure.
        if not _cloudinary_credentials_present():
            raise HTTPException(status_code=503, detail="Private attachment storage is not configured.")
        return "cloudinary"
    return "local"


def _cloudinary_private_folder() -> str:
    raw = (os.getenv("SEVOR_MESSAGE_CLOUDINARY_FOLDER") or CLOUDINARY_PRIVATE_FOLDER_DEFAULT).strip("/ ")
    parts = [part for part in raw.split("/") if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", part or "")]
    return "/".join(parts) or CLOUDINARY_PRIVATE_FOLDER_DEFAULT


def _configure_cloudinary() -> None:
    if not _cloudinary_credentials_present():
        raise HTTPException(status_code=503, detail="Private attachment storage is not configured.")
    # This is intentionally server-side only.  Neither a secret nor a signed
    # provider URL is persisted in a message row or rendered into the page.
    cloudinary.config(
        cloud_name=(os.getenv("CLOUDINARY_CLOUD_NAME") or "").strip(),
        api_key=(os.getenv("CLOUDINARY_API_KEY") or "").strip(),
        api_secret=(os.getenv("CLOUDINARY_API_SECRET") or "").strip(),
        secure=True,
    )


def _cloudinary_reference(value: str | None) -> tuple[str, str, str] | None:
    """Return ``(resource_type, object_token, extension)`` for a remote row."""
    match = _CLOUDINARY_REFERENCE_RE.fullmatch(str(value or ""))
    if not match:
        return None
    resource_type = _CLOUDINARY_RESOURCE_BY_CODE.get(match.group(1))
    if not resource_type:
        return None
    return resource_type, match.group(2), match.group(3)


def is_cloudinary_message_attachment(attachment: MessageAttachment) -> bool:
    return _cloudinary_reference(getattr(attachment, "stored_name", None)) is not None


def _cloudinary_public_id(object_token: str) -> str:
    return f"{_cloudinary_private_folder()}/{object_token}"


def _cloudinary_stored_name(kind: str, extension: str) -> str:
    code = _CLOUDINARY_CODE_BY_KIND.get(kind, "r")
    return f"{CLOUDINARY_STORED_NAME_PREFIX}{code}:{uuid.uuid4().hex}{extension}"


def _cloudinary_private_download_url(attachment: MessageAttachment, *, as_attachment: bool) -> str:
    reference = _cloudinary_reference(getattr(attachment, "stored_name", None))
    if not reference:
        raise HTTPException(status_code=404, detail="Attachment not found")
    _configure_cloudinary()
    resource_type, object_token, extension = reference
    try:
        return cloudinary.utils.private_download_url(
            _cloudinary_public_id(object_token),
            extension.lstrip("."),
            resource_type=resource_type,
            type="private",
            attachment=as_attachment,
            expires_at=int(time.time()) + CLOUDINARY_PRIVATE_URL_TTL_SECONDS,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Attachment is temporarily unavailable.") from exc


def stream_cloudinary_message_attachment(attachment: MessageAttachment, *, as_attachment: bool) -> Iterator[bytes]:
    """Proxy one short-lived private provider download through SEVOR's auth gate.

    The browser never receives a permanent provider URL.  The caller has
    already verified conversation membership before this function is reached.
    """
    url = _cloudinary_private_download_url(attachment, as_attachment=as_attachment)
    try:
        response = requests.get(url, stream=True, timeout=(5, CLOUDINARY_DOWNLOAD_TIMEOUT_SECONDS))
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Attachment is temporarily unavailable.") from exc

    if response.status_code == 404:
        response.close()
        raise HTTPException(status_code=410, detail="Attachment is unavailable")
    if response.status_code < 200 or response.status_code >= 300:
        response.close()
        raise HTTPException(status_code=503, detail="Attachment is temporarily unavailable.")

    def _chunks() -> Iterator[bytes]:
        try:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    yield chunk
        finally:
            response.close()

    return _chunks()


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


def max_direct_message_request_bytes() -> int:
    """Return the largest valid multipart body plus a bounded form overhead.

    This is used by a route-scoped preflight guard before Starlette parses a
    normal browser upload.  The streaming per-file checks below remain the
    authoritative validation for requests without a Content-Length header.
    """
    normal_batch = max_attachment_bytes() * max_attachments_per_message()
    return max(normal_batch, max_voice_bytes()) + MESSAGE_REQUEST_OVERHEAD_BYTES


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
            # Duration supplied by a browser is not authoritative.  New voice
            # rows intentionally leave it empty; the recipient's native audio
            # element derives the real duration from the persisted bytes.
            _ = voice_duration_ms
            staged.append(
                await _stage_one(
                    voice_upload,
                    kind="voice",
                    size_limit=max_voice_bytes(),
                    duration_ms=None,
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
    backend = message_attachment_storage_backend()
    if backend == "local":
        MESSAGE_ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[MessageAttachment] = []
    try:
        for item in staged:
            stored_name = (
                _cloudinary_stored_name(item.kind, item.extension)
                if backend == "cloudinary"
                else f"{uuid.uuid4().hex}{item.extension}"
            )
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
            # Append before touching storage so a partial provider success is
            # cleaned if a later local/remote operation raises.
            records.append(record)
            if backend == "cloudinary":
                reference = _cloudinary_reference(stored_name)
                if not reference:
                    raise HTTPException(status_code=503, detail="Private attachment storage is not configured.")
                resource_type, object_token, _extension = reference
                try:
                    _configure_cloudinary()
                    with item.temp_path.open("rb") as source:
                        result = cloudinary.uploader.upload(
                            source,
                            public_id=_cloudinary_public_id(object_token),
                            resource_type=resource_type,
                            type="private",
                            overwrite=False,
                            unique_filename=False,
                            use_filename=False,
                        )
                    if not (result or {}).get("public_id"):
                        raise RuntimeError("The private media provider did not return an object id.")
                    item.temp_path.unlink(missing_ok=True)
                except HTTPException:
                    raise
                except Exception as exc:
                    raise HTTPException(status_code=503, detail="Attachment upload failed. Please try again.") from exc
            else:
                destination = MESSAGE_ATTACHMENT_ROOT / stored_name
                os.replace(item.temp_path, destination)
    except Exception:
        remove_saved_message_attachment_files(records)
        raise
    return records


def remove_saved_message_attachment_files(records: Iterable[MessageAttachment | str]) -> None:
    for record in records:
        try:
            raw_name = record if isinstance(record, str) else (record.stored_name or "")
            reference = _cloudinary_reference(raw_name)
            if reference:
                resource_type, object_token, _extension = reference
                try:
                    _configure_cloudinary()
                    cloudinary.uploader.destroy(
                        _cloudinary_public_id(object_token),
                        resource_type=resource_type,
                        type="private",
                        invalidate=True,
                    )
                except Exception:
                    # This cleanup runs only after a DB rollback/deletion.  A
                    # best-effort provider cleanup must never resurrect the DB
                    # transaction or expose the private object to a client.
                    pass
                continue
            stored_name = Path(raw_name).name
            if stored_name:
                (MESSAGE_ATTACHMENT_ROOT / stored_name).unlink(missing_ok=True)
        except OSError:
            pass


def message_attachment_path(attachment: MessageAttachment) -> Path:
    if is_cloudinary_message_attachment(attachment):
        raise HTTPException(status_code=404, detail="Attachment not found")
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
