"""Opt-in rescue migration for recoverable legacy direct-message media.

Run this on the *currently running* release before its local filesystem is
discarded.  It is dry-run by default and never deletes local bytes unless both
``--apply`` and ``--delete-local-after-commit`` are supplied.

Examples:
    python migrate_message_attachments_to_cloudinary.py
    python migrate_message_attachments_to_cloudinary.py --apply
    python migrate_message_attachments_to_cloudinary.py --apply --delete-local-after-commit
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.database import SessionLocal
from app.message_attachments import (
    has_explicit_cloudinary_attachment_reference,
    hydrate_legacy_cloudinary_attachment_metadata,
    is_cloudinary_message_attachment,
    message_attachment_path,
    migrate_local_message_attachment_to_cloudinary,
    remove_saved_message_attachment_files,
    stream_cloudinary_message_attachment,
)
from app.models import MessageAttachment


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_chunks(chunks) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy recoverable direct-message attachments to private Cloudinary storage.")
    parser.add_argument("--apply", action="store_true", help="perform the migration; otherwise only report what is recoverable")
    parser.add_argument(
        "--delete-local-after-commit",
        action="store_true",
        help="delete each local source only after the remote checksum and database commit succeed",
    )
    parser.add_argument("--limit", type=int, default=0, help="maximum number of legacy rows to inspect (0 means all)")
    args = parser.parse_args()
    if args.delete_local_after_commit and not args.apply:
        parser.error("--delete-local-after-commit requires --apply")

    db = SessionLocal()
    summary = {
        "already_remote": 0,
        "legacy_cloud": 0,
        "recoverable": 0,
        "migrated": 0,
        "hydrated": 0,
        "missing": 0,
        "failed": 0,
    }
    try:
        query = db.query(MessageAttachment).order_by(MessageAttachment.id.asc())
        if args.limit > 0:
            query = query.limit(args.limit)
        for attachment in query.all():
            if is_cloudinary_message_attachment(attachment):
                if has_explicit_cloudinary_attachment_reference(attachment):
                    summary["already_remote"] += 1
                    continue
                summary["legacy_cloud"] += 1
                if not args.apply:
                    print(f"attachment {attachment.id}: legacy Cloudinary reference can be verified and hydrated")
                    continue
                try:
                    remote_object = hydrate_legacy_cloudinary_attachment_metadata(attachment)
                    attachment.storage_backend = "cloudinary"
                    attachment.storage_key = remote_object.public_id
                    attachment.storage_resource_type = remote_object.resource_type
                    attachment.storage_delivery_type = remote_object.delivery_type
                    attachment.storage_format = remote_object.format
                    db.commit()
                    summary["hydrated"] += 1
                    print(f"attachment {attachment.id}: Cloudinary reference verified and hydrated")
                except Exception as exc:
                    db.rollback()
                    summary["failed"] += 1
                    # Never delete an existing remote object when metadata
                    # hydration fails; it may still be reachable by the
                    # legacy compatibility path or another active process.
                    print(f"attachment {attachment.id}: Cloudinary reference could not be hydrated ({exc})")
                continue
            try:
                source = message_attachment_path(attachment)
            except Exception:
                summary["missing"] += 1
                print(f"attachment {attachment.id}: local bytes unavailable; skipped")
                continue

            summary["recoverable"] += 1
            if not args.apply:
                print(f"attachment {attachment.id}: recoverable ({attachment.size_bytes} bytes)")
                continue

            previous_key = attachment.stored_name
            previous_backend = attachment.storage_backend
            previous_storage_key = attachment.storage_key
            previous_resource_type = attachment.storage_resource_type
            previous_delivery_type = attachment.storage_delivery_type
            previous_storage_format = attachment.storage_format
            remote_object = None
            try:
                source_checksum = _sha256_file(source)
                remote_object = migrate_local_message_attachment_to_cloudinary(attachment)
                attachment.stored_name = remote_object.stored_name
                attachment.storage_backend = "cloudinary"
                attachment.storage_key = remote_object.public_id
                attachment.storage_resource_type = remote_object.resource_type
                attachment.storage_delivery_type = remote_object.delivery_type
                attachment.storage_format = remote_object.format
                remote_checksum = _sha256_chunks(
                    stream_cloudinary_message_attachment(attachment, as_attachment=False)
                )
                if remote_checksum != source_checksum:
                    raise RuntimeError("remote checksum did not match the local source")
                db.commit()
                summary["migrated"] += 1
                print(f"attachment {attachment.id}: migrated and verified")
                if args.delete_local_after_commit:
                    try:
                        source.unlink(missing_ok=True)
                    except OSError as exc:
                        print(f"attachment {attachment.id}: database migrated, but local cleanup failed: {exc}")
            except Exception as exc:
                db.rollback()
                summary["failed"] += 1
                if remote_object:
                    remove_saved_message_attachment_files([remote_object])
                # The row object may be expired after rollback; restoring this
                # value keeps subsequent diagnostics truthful in this session.
                attachment.stored_name = previous_key
                attachment.storage_backend = previous_backend
                attachment.storage_key = previous_storage_key
                attachment.storage_resource_type = previous_resource_type
                attachment.storage_delivery_type = previous_delivery_type
                attachment.storage_format = previous_storage_format
                print(f"attachment {attachment.id}: failed; local source kept ({exc})")
    finally:
        db.close()

    print(
        "summary: "
        + ", ".join(f"{key}={value}" for key, value in summary.items())
        + (" (dry run)" if not args.apply else "")
    )
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
