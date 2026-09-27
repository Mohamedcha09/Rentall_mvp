"""Private, validated file handling for human support-ticket messages.

Support attachments must not use the application's public ``/uploads`` mount:
ticket conversations can contain private account information.  This module keeps
the files outside that mount and leaves access control to the authenticated
ticket download route.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from .models import SupportAttachment


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_UPLOAD_ROOT = Path(
    os.getenv("SEVOR_PRIVATE_UPLOADS_DIR", str(PROJECT_ROOT / "private_uploads"))
).resolve()
SUPPORT_ATTACHMENT_ROOT = PRIVATE_UPLOAD_ROOT / "support_ticket_attachments"
SUPPORT_ATTACHMENT_STAGING_ROOT = SUPPORT_ATTACHMENT_ROOT / ".staging"

MAX_ATTACHMENTS_PER_MESSAGE = 4
DEFAULT_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
CHUNK_SIZE = 64 * 1024

# Keep the allow-list intentionally small.  The browser's ``accept`` attribute
# mirrors this list for usability, but every restriction is enforced here.
ALLOWED_ATTACHMENT_TYPES: dict[str, set[str]] = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
    ".pdf": {"application/pdf"},
}
IMAGE_ATTACHMENT_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def max_attachment_bytes() -> int:
    """Read the one configurable server-side attachment limit safely."""
    raw = (os.getenv("SEVOR_SUPPORT_ATTACHMENT_MAX_BYTES") or "").strip()
    if not raw:
        return DEFAULT_MAX_ATTACHMENT_BYTES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_ATTACHMENT_BYTES
    # Do not let an accidental environment value disable a practical cap.
    return value if 256 * 1024 <= value <= 25 * 1024 * 1024 else DEFAULT_MAX_ATTACHMENT_BYTES


def allowed_accept_value() -> str:
    return ",".join(sorted({mime for mimes in ALLOWED_ATTACHMENT_TYPES.values() for mime in mimes}))


def _display_name(value: str | None) -> str:
    """Keep a safe display-only filename; never use it for storage."""
    raw = Path(value or "attachment").name.replace("\x00", "")
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", raw).strip().strip(".")
    if not cleaned:
        cleaned = "attachment"
    return cleaned[:180]


def _declared_content_type(upload: UploadFile) -> str:
    return (upload.content_type or "").split(";", 1)[0].strip().lower()


def _validate_signature(path: Path, extension: str) -> None:
    with path.open("rb") as source:
        header = source.read(16)

    valid = (
        (extension in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
        or (extension == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension == ".webp" and len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP")
        or (extension == ".pdf" and header.startswith(b"%PDF-"))
    )
    if not valid:
        raise HTTPException(status_code=422, detail="The file content does not match its declared type.")


@dataclass
class StagedSupportAttachment:
    temp_path: Path
    display_name: str
    extension: str
    content_type: str
    size_bytes: int


def cleanup_staged_attachments(staged: Iterable[StagedSupportAttachment]) -> None:
    for item in staged:
        try:
            item.temp_path.unlink(missing_ok=True)
        except OSError:
            pass


async def stage_support_attachments(
    uploads: Sequence[UploadFile] | None,
) -> list[StagedSupportAttachment]:
    """Validate every upload before any ticket message is persisted.

    Uploads are streamed to a private staging directory, so a client cannot
    force an unbounded in-memory allocation.  All staged files are discarded
    when one file fails validation.
    """
    candidates = [upload for upload in (uploads or []) if upload and (upload.filename or "").strip()]
    if len(candidates) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise HTTPException(
            status_code=422,
            detail=f"You can attach up to {MAX_ATTACHMENTS_PER_MESSAGE} files to one message.",
        )

    if not candidates:
        return []

    SUPPORT_ATTACHMENT_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    size_limit = max_attachment_bytes()
    staged: list[StagedSupportAttachment] = []
    try:
        for upload in candidates:
            display_name = _display_name(upload.filename)
            extension = Path(display_name).suffix.lower()
            content_type = _declared_content_type(upload)
            allowed_types = ALLOWED_ATTACHMENT_TYPES.get(extension)
            if not allowed_types or content_type not in allowed_types:
                raise HTTPException(status_code=422, detail="Only JPEG, PNG, WebP, and PDF attachments are allowed.")

            handle = tempfile.NamedTemporaryFile(
                mode="wb", delete=False, dir=SUPPORT_ATTACHMENT_STAGING_ROOT, prefix="support-"
            )
            temp_path = Path(handle.name)
            size_bytes = 0
            try:
                while chunk := await upload.read(CHUNK_SIZE):
                    size_bytes += len(chunk)
                    if size_bytes > size_limit:
                        raise HTTPException(
                            status_code=422,
                            detail=f"Each attachment must be {size_limit // (1024 * 1024)} MB or smaller.",
                        )
                    handle.write(chunk)
            finally:
                handle.close()

            if not size_bytes:
                raise HTTPException(status_code=422, detail="Empty attachments are not allowed.")
            _validate_signature(temp_path, extension)
            staged.append(
                StagedSupportAttachment(
                    temp_path=temp_path,
                    display_name=display_name,
                    extension=extension,
                    content_type=content_type,
                    size_bytes=size_bytes,
                )
            )
    except Exception:
        cleanup_staged_attachments(staged)
        # If validation fails while processing the current upload, it has not
        # been added to ``staged`` yet.
        try:
            temp_path.unlink(missing_ok=True)  # type: ignore[name-defined]
        except (NameError, OSError):
            pass
        raise
    finally:
        for upload in candidates:
            try:
                await upload.close()
            except Exception:
                pass

    return staged


def persist_staged_support_attachments(
    db: Session,
    *,
    ticket_id: int,
    message_id: int,
    uploader_id: int,
    staged: Sequence[StagedSupportAttachment],
) -> list[SupportAttachment]:
    """Attach validated private files to an already-flushed support message.

    The caller owns the surrounding database transaction.  If moving one file
    fails, it can roll the transaction back and call ``remove_saved_files``.
    """
    if not staged:
        return []

    SUPPORT_ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[SupportAttachment] = []
    for item in staged:
        stored_name = f"{uuid.uuid4().hex}{item.extension}"
        destination = SUPPORT_ATTACHMENT_ROOT / stored_name
        record = SupportAttachment(
            ticket_id=ticket_id,
            message_id=message_id,
            uploader_id=uploader_id,
            original_name=item.display_name,
            stored_name=stored_name,
            content_type=item.content_type,
            size_bytes=item.size_bytes,
        )
        db.add(record)
        db.flush()
        os.replace(item.temp_path, destination)
        records.append(record)
    return records


def remove_saved_attachment_files(records: Iterable[SupportAttachment]) -> None:
    for record in records:
        try:
            stored_name = Path(record.stored_name or "").name
            if stored_name:
                (SUPPORT_ATTACHMENT_ROOT / stored_name).unlink(missing_ok=True)
        except OSError:
            pass


def support_attachment_path(attachment: SupportAttachment) -> Path:
    stored_name = Path(attachment.stored_name or "").name
    if not stored_name or stored_name != attachment.stored_name:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = SUPPORT_ATTACHMENT_ROOT / stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment not found")
    return path


def serialize_support_attachment(attachment: SupportAttachment, *, ticket_id: int) -> dict[str, object]:
    return {
        "id": attachment.id,
        "name": attachment.original_name,
        "content_type": attachment.content_type,
        "size_bytes": int(attachment.size_bytes or 0),
        "is_image": Path(attachment.stored_name or "").suffix.lower() in IMAGE_ATTACHMENT_EXTENSIONS,
        "url": f"/support/ticket/{ticket_id}/attachments/{attachment.id}",
    }
