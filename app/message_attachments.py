"""Private, validated media handling for ordinary SEVOR direct messages.

Direct messages are private conversations, so their images, documents, and
voice recordings must never be placed under the application's public
``/uploads`` mount.  This deliberately follows the established support-ticket
attachment pattern while keeping direct-message records and files separate.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence
from urllib.parse import unquote, urlparse

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

try:  # Cloudinary is already used by SEVOR's durable media integrations.
    import cloudinary
    import cloudinary.api
    import cloudinary.uploader
    import cloudinary.utils
except ImportError:  # Keep local development usable when the optional SDK is absent.
    cloudinary = None

import requests

from .models import MessageAttachment
from .support_attachments import PRIVATE_UPLOAD_ROOT


logger = logging.getLogger(__name__)


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
    if cloudinary is None:
        return False
    if all(
        (os.getenv(name) or "").strip()
        for name in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    ):
        return True
    cloudinary_url = (os.getenv("CLOUDINARY_URL") or "").strip()
    parsed = urlparse(cloudinary_url)
    return bool(
        parsed.scheme.lower() == "cloudinary"
        and parsed.hostname
        and parsed.username
        and parsed.password
    )


def _is_render_runtime() -> bool:
    """Recognize Render without making local/test environments remote-backed."""
    return any(
        (os.getenv(name) or "").strip()
        for name in ("RENDER", "RENDER_SERVICE_ID", "RENDER_EXTERNAL_URL")
    )


def message_attachment_storage_backend() -> str:
    """Select the durable backend without silently using ephemeral files in production.

    ``SEVOR_MESSAGE_ATTACHMENT_STORAGE`` can explicitly be ``local`` (only
    for a mounted persistent disk) or ``cloudinary``.  With no explicit
    setting, any configured Cloudinary account wins.  This avoids relying on
    a platform-specific Render marker and prevents a cold production process
    from silently accepting files onto an ephemeral release filesystem.
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

    if _cloudinary_credentials_present():
        return "cloudinary"
    if _is_render_runtime():
        # Do not fall back to Render's release filesystem when no durable
        # provider is configured: accepting an upload that will disappear on
        # redeploy is worse than a clear, retryable configuration failure.
        raise HTTPException(status_code=503, detail="Private attachment storage is not configured.")
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
    cloud_name = (os.getenv("CLOUDINARY_CLOUD_NAME") or "").strip()
    api_key = (os.getenv("CLOUDINARY_API_KEY") or "").strip()
    api_secret = (os.getenv("CLOUDINARY_API_SECRET") or "").strip()
    if cloud_name and api_key and api_secret:
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )
        return

    # Some Render services are configured with the standard CLOUDINARY_URL
    # instead of three individual variables.  Parse it server-side only; no
    # credential or URL is logged, saved in the database, or sent to a client.
    parsed = urlparse((os.getenv("CLOUDINARY_URL") or "").strip())
    if not (parsed.hostname and parsed.username and parsed.password):
        raise HTTPException(status_code=503, detail="Private attachment storage is not configured.")
    cloudinary.config(
        cloud_name=parsed.hostname,
        api_key=unquote(parsed.username),
        api_secret=unquote(parsed.password),
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


def message_attachment_record_backend(attachment: MessageAttachment) -> str:
    """Return the persisted backend, with a compatibility path for old rows.

    New rows always carry ``storage_backend``.  The prefix fallback only keeps
    already-created records readable while the metadata migration rolls out;
    it is deliberately not used for new uploads.
    """
    explicit = str(getattr(attachment, "storage_backend", "") or "").strip().lower()
    if explicit in {"local", "cloudinary"}:
        return explicit
    return "cloudinary" if _cloudinary_reference(getattr(attachment, "stored_name", None)) else "local"


def is_cloudinary_message_attachment(attachment: MessageAttachment) -> bool:
    return message_attachment_record_backend(attachment) == "cloudinary"


def _cloudinary_public_id(object_token: str, *, resource_type: str, extension: str) -> str:
    # Cloudinary requires raw public IDs to include the extension. Image and
    # video IDs intentionally do not include it.
    suffix = extension if resource_type == "raw" else ""
    return f"{_cloudinary_private_folder()}/{object_token}{suffix}"


def _cloudinary_stored_name(kind: str, extension: str) -> str:
    # Cloudinary treats PDFs as image resources; keeping them in that resource
    # class avoids raw-file public-id extension rules while preserving the
    # original private PDF bytes through the authenticated download endpoint.
    code = "i" if kind == "file" and extension == ".pdf" else _CLOUDINARY_CODE_BY_KIND.get(kind, "r")
    return f"{CLOUDINARY_STORED_NAME_PREFIX}{code}:{uuid.uuid4().hex}{extension}"


@dataclass(frozen=True)
class CloudinaryStoredObject:
    """Verified, server-only reference to one private Cloudinary object."""

    stored_name: str
    public_id: str
    resource_type: str
    delivery_type: str
    size_bytes: int
    format: str | None = None
    asset_id: str | None = None


def _cloudinary_attachment_reference(attachment: MessageAttachment) -> CloudinaryStoredObject:
    """Read a durable provider reference without rebuilding new rows from env."""
    if not is_cloudinary_message_attachment(attachment):
        raise HTTPException(status_code=404, detail="Attachment not found")

    public_id = str(getattr(attachment, "storage_key", "") or "").strip()
    resource_type = str(getattr(attachment, "storage_resource_type", "") or "").strip().lower()
    delivery_type = str(getattr(attachment, "storage_delivery_type", "") or "").strip().lower()
    if public_id and resource_type in _CLOUDINARY_RESOURCE_BY_CODE.values() and delivery_type == "private":
        return CloudinaryStoredObject(
            stored_name=str(attachment.stored_name or ""),
            public_id=public_id,
            resource_type=resource_type,
            delivery_type=delivery_type,
            size_bytes=int(attachment.size_bytes or 0),
        )

    # Compatibility for rows created by the prior Cloudinary implementation.
    # New records never enter this branch because they persist public_id/type.
    legacy = _cloudinary_reference(getattr(attachment, "stored_name", None))
    if not legacy:
        raise HTTPException(status_code=404, detail="Attachment not found")
    legacy_resource_type, token, extension = legacy
    return CloudinaryStoredObject(
        stored_name=str(attachment.stored_name or ""),
        public_id=_cloudinary_public_id(token, resource_type=legacy_resource_type, extension=extension),
        resource_type=legacy_resource_type,
        delivery_type="private",
        size_bytes=int(attachment.size_bytes or 0),
        format=extension.lstrip(".") or None,
    )


def _cloudinary_destroy_object(reference: CloudinaryStoredObject) -> None:
    try:
        _configure_cloudinary()
        cloudinary.uploader.destroy(
            reference.public_id,
            resource_type=reference.resource_type,
            type=reference.delivery_type,
            invalidate=True,
        )
    except Exception:
        # The caller has already rolled back/deleted its database record.  A
        # failed cleanup is logged but must not make a request appear to have
        # succeeded or expose a provider URL.
        logger.warning(
            "dm_attachment_cloudinary_cleanup_failed backend=cloudinary resource_type=%s",
            reference.resource_type,
        )


def _cloudinary_verify_object(
    *,
    stored_name: str,
    public_id: str,
    resource_type: str,
    delivery_type: str,
    expected_size_bytes: int,
) -> CloudinaryStoredObject:
    """Require Cloudinary Admin API confirmation before the DB can commit."""
    try:
        _configure_cloudinary()
        metadata = cloudinary.api.resource(
            public_id,
            resource_type=resource_type,
            type=delivery_type,
        )
    except Exception as exc:
        logger.warning(
            "dm_attachment_cloudinary_verify_failed resource_type=%s error=%s",
            resource_type,
            type(exc).__name__,
        )
        raise HTTPException(status_code=503, detail="Attachment upload could not be verified. Please try again.") from exc

    actual_public_id = str((metadata or {}).get("public_id") or "")
    actual_resource_type = str((metadata or {}).get("resource_type") or "").lower()
    actual_delivery_type = str((metadata or {}).get("type") or "").lower()
    try:
        actual_size = int((metadata or {}).get("bytes"))
    except (TypeError, ValueError):
        actual_size = -1

    if (
        actual_public_id != public_id
        or actual_resource_type != resource_type
        or actual_delivery_type != delivery_type
        or actual_size != int(expected_size_bytes)
    ):
        logger.error(
            "dm_attachment_cloudinary_verify_mismatch resource_type=%s expected_bytes=%s actual_bytes=%s",
            resource_type,
            expected_size_bytes,
            actual_size,
        )
        raise HTTPException(status_code=503, detail="Attachment upload could not be verified. Please try again.")

    logger.info(
        "dm_attachment_cloudinary_verified backend=cloudinary resource_type=%s provider_found=true bytes=%s",
        actual_resource_type,
        actual_size,
    )
    return CloudinaryStoredObject(
        stored_name=stored_name,
        public_id=actual_public_id,
        resource_type=actual_resource_type,
        delivery_type=actual_delivery_type,
        size_bytes=actual_size,
        format=str((metadata or {}).get("format") or "") or None,
        asset_id=str((metadata or {}).get("asset_id") or "") or None,
    )


def _cloudinary_private_download_url(attachment: MessageAttachment, *, as_attachment: bool) -> str:
    reference = _cloudinary_attachment_reference(attachment)
    _configure_cloudinary()
    extension = (
        Path(str(attachment.original_name or "")).suffix.lower()
        or Path(str(attachment.stored_name or "")).suffix.lower()
        or (f".{reference.format}" if reference.format else "")
    )
    if not extension:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        return cloudinary.utils.private_download_url(
            reference.public_id,
            extension.lstrip("."),
            resource_type=reference.resource_type,
            type=reference.delivery_type,
            attachment=as_attachment,
            expires_at=int(time.time()) + CLOUDINARY_PRIVATE_URL_TTL_SECONDS,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Attachment is temporarily unavailable.") from exc


def _upload_path_to_cloudinary(
    source_path: Path,
    stored_name: str,
    *,
    expected_size_bytes: int,
) -> CloudinaryStoredObject:
    """Upload and verify one private object before any attachment row is saved."""
    reference = _cloudinary_reference(stored_name)
    if not reference:
        raise HTTPException(status_code=503, detail="Private attachment storage is not configured.")
    resource_type, object_token, _extension = reference
    public_id = _cloudinary_public_id(object_token, resource_type=resource_type, extension=_extension)
    uploaded_reference: CloudinaryStoredObject | None = None
    try:
        _configure_cloudinary()
        with source_path.open("rb") as source:
            result = cloudinary.uploader.upload(
                source,
                public_id=public_id,
                resource_type=resource_type,
                type="private",
                overwrite=False,
                unique_filename=False,
                use_filename=False,
            )
        actual_public_id = str((result or {}).get("public_id") or "")
        if actual_public_id != public_id:
            # A provider-side naming change must not leave an unreferenced
            # private object behind or make a DB row point at the wrong asset.
            if actual_public_id:
                try:
                    cloudinary.uploader.destroy(
                        actual_public_id,
                        resource_type=resource_type,
                        type="private",
                        invalidate=True,
                    )
                except Exception:
                    pass
            raise RuntimeError("The private media provider returned an unexpected object id.")
        uploaded_reference = _cloudinary_verify_object(
            stored_name=stored_name,
            public_id=actual_public_id,
            resource_type=resource_type,
            delivery_type="private",
            expected_size_bytes=expected_size_bytes,
        )
        return uploaded_reference
    except HTTPException:
        if uploaded_reference:
            _cloudinary_destroy_object(uploaded_reference)
        elif public_id:
            _cloudinary_destroy_object(
                CloudinaryStoredObject(
                    stored_name=stored_name,
                    public_id=public_id,
                    resource_type=resource_type,
                    delivery_type="private",
                    size_bytes=expected_size_bytes,
                )
            )
        raise
    except Exception as exc:
        if uploaded_reference:
            _cloudinary_destroy_object(uploaded_reference)
        elif public_id:
            _cloudinary_destroy_object(
                CloudinaryStoredObject(
                    stored_name=stored_name,
                    public_id=public_id,
                    resource_type=resource_type,
                    delivery_type="private",
                    size_bytes=expected_size_bytes,
                )
            )
        raise HTTPException(status_code=503, detail="Attachment upload failed. Please try again.") from exc


def migrate_local_message_attachment_to_cloudinary(attachment: MessageAttachment) -> CloudinaryStoredObject:
    """Copy one recoverable legacy local attachment to private Cloudinary.

    This intentionally does not mutate the database or delete the local source.
    A caller must commit the returned opaque storage key first, then may remove
    the source only after that commit succeeds.
    """
    if is_cloudinary_message_attachment(attachment):
        return _cloudinary_attachment_reference(attachment)
    source_path = message_attachment_path(attachment)
    extension = Path(attachment.stored_name or attachment.original_name or "").suffix.lower()
    stored_name = _cloudinary_stored_name(str(attachment.kind or "file"), extension)
    return _upload_path_to_cloudinary(
        source_path,
        stored_name,
        expected_size_bytes=int(attachment.size_bytes or source_path.stat().st_size),
    )


def stream_cloudinary_message_attachment(attachment: MessageAttachment, *, as_attachment: bool) -> Iterator[bytes]:
    """Proxy one short-lived private provider download through SEVOR's auth gate.

    The browser never receives a permanent provider URL.  The caller has
    already verified conversation membership before this function is reached.
    """
    url = _cloudinary_private_download_url(attachment, as_attachment=as_attachment)
    try:
        response = requests.get(url, stream=True, timeout=(5, CLOUDINARY_DOWNLOAD_TIMEOUT_SECONDS))
    except requests.RequestException as exc:
        logger.warning(
            "dm_attachment_download_failed attachment_id=%s backend=cloudinary provider_status=network_error error=%s",
            getattr(attachment, "id", None),
            type(exc).__name__,
        )
        raise HTTPException(status_code=503, detail="Attachment is temporarily unavailable.") from exc

    if response.status_code == 404:
        response.close()
        logger.warning(
            "dm_attachment_download_failed attachment_id=%s backend=cloudinary provider_found=false provider_status=404",
            getattr(attachment, "id", None),
        )
        raise HTTPException(status_code=410, detail="Attachment is unavailable")
    if response.status_code < 200 or response.status_code >= 300:
        status_code = response.status_code
        response.close()
        logger.warning(
            "dm_attachment_download_failed attachment_id=%s backend=cloudinary provider_status=%s",
            getattr(attachment, "id", None),
            status_code,
        )
        raise HTTPException(status_code=503, detail="Attachment is temporarily unavailable.")

    logger.info(
        "dm_attachment_download_ready attachment_id=%s backend=cloudinary resource_type=%s provider_found=true provider_status=%s",
        getattr(attachment, "id", None),
        _cloudinary_attachment_reference(attachment).resource_type,
        response.status_code,
    )

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
        # Keep the validated suffix while staging.  Cloudinary can then retain
        # the correct format for audio/video as well as images and PDFs; an
        # extensionless temporary stream is not a reliable voice-media input.
        mode="wb", delete=False, dir=MESSAGE_ATTACHMENT_STAGING_ROOT, prefix="message-", suffix=extension
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
    logger.info(
        "dm_attachment_storage_selected backend=%s render_runtime=%s cloudinary_configured=%s",
        backend,
        _is_render_runtime(),
        _cloudinary_credentials_present(),
    )
    if backend == "local":
        MESSAGE_ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[MessageAttachment] = []
    unlinked_remote_objects: list[CloudinaryStoredObject] = []
    try:
        for item in staged:
            stored_name = (
                _cloudinary_stored_name(item.kind, item.extension)
                if backend == "cloudinary"
                else f"{uuid.uuid4().hex}{item.extension}"
            )
            remote_object: CloudinaryStoredObject | None = None
            if backend == "cloudinary":
                # The provider object is uploaded and verified *before* an
                # attachment row is inserted.  A DB commit can therefore never
                # represent a successful cloud attachment whose bytes were not
                # confirmed by Cloudinary.
                remote_object = _upload_path_to_cloudinary(
                    item.temp_path,
                    stored_name,
                    expected_size_bytes=item.size_bytes,
                )
                unlinked_remote_objects.append(remote_object)
            record = MessageAttachment(
                thread_id=thread_id,
                message_id=message_id,
                uploader_id=uploader_id,
                kind=item.kind,
                original_name=item.display_name,
                stored_name=stored_name,
                storage_backend=backend,
                storage_key=remote_object.public_id if remote_object else stored_name,
                storage_resource_type=remote_object.resource_type if remote_object else None,
                storage_delivery_type=remote_object.delivery_type if remote_object else None,
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
                unlinked_remote_objects.remove(remote_object)
                item.temp_path.unlink(missing_ok=True)
            else:
                destination = MESSAGE_ATTACHMENT_ROOT / stored_name
                os.replace(item.temp_path, destination)
            logger.info(
                "dm_attachment_upload_persisted attachment_id=%s message_id=%s backend=%s resource_type=%s bytes=%s",
                record.id,
                message_id,
                backend,
                remote_object.resource_type if remote_object else "local",
                item.size_bytes,
            )
    except Exception:
        remove_saved_message_attachment_files([*records, *unlinked_remote_objects])
        raise
    return records


def remove_saved_message_attachment_files(
    records: Iterable[MessageAttachment | CloudinaryStoredObject | str],
) -> None:
    for record in records:
        try:
            if isinstance(record, CloudinaryStoredObject):
                _cloudinary_destroy_object(record)
                continue
            if not isinstance(record, str) and is_cloudinary_message_attachment(record):
                _cloudinary_destroy_object(_cloudinary_attachment_reference(record))
                continue
            raw_name = record if isinstance(record, str) else (record.storage_key or record.stored_name or "")
            # Old Cloudinary rows supplied only as strings retain their
            # compatibility cleanup behavior until they are migrated.
            reference = _cloudinary_reference(raw_name)
            if reference:
                resource_type, object_token, extension = reference
                _cloudinary_destroy_object(
                    CloudinaryStoredObject(
                        stored_name=raw_name,
                        public_id=_cloudinary_public_id(
                            object_token,
                            resource_type=resource_type,
                            extension=extension,
                        ),
                        resource_type=resource_type,
                        delivery_type="private",
                        size_bytes=0,
                    )
                )
                continue
            stored_name = Path(raw_name).name
            if stored_name:
                (MESSAGE_ATTACHMENT_ROOT / stored_name).unlink(missing_ok=True)
        except Exception:
            logger.warning("dm_attachment_cleanup_failed")


def message_attachment_path(attachment: MessageAttachment) -> Path:
    if is_cloudinary_message_attachment(attachment):
        raise HTTPException(status_code=404, detail="Attachment not found")
    raw_name = str(attachment.storage_key or attachment.stored_name or "")
    stored_name = Path(raw_name).name
    if not stored_name or stored_name != raw_name:
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
