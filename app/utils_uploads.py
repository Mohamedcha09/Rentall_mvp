# app/utils_uploads.py
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Literal, Optional, Tuple

# Note: your project mounts uploads in app/main.py at:
#   UPLOADS_DIR = <root>/uploads
# This file builds the same paths safely.

# Root upload directories based on your current project structure:
PROJECT_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = PROJECT_DIR / "uploads"      # ../uploads
DEPOSITS_DIR = UPLOADS_DIR / "deposits"    # ../uploads/deposits

# Allowed extensions
ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
ALLOWED_VIDEO_EXTS = {"mp4", "mov", "webm"}
ALLOWED_DOC_EXTS   = {"pdf"}
ALLOWED_ALL_EXTS = ALLOWED_IMAGE_EXTS | ALLOWED_VIDEO_EXTS | ALLOWED_DOC_EXTS

# Filename normalization
_filename_keep = re.compile(r"[^A-Za-z0-9._-]+")


def ensure_dirs(path: Path) -> None:
    """Create directories if they don't exist (safe for concurrency)."""
    path.mkdir(parents=True, exist_ok=True)


def split_name_ext(name: str) -> Tuple[str, str]:
    """Split name from extension and return (name without extension, extension without dot)."""
    name = name or ""
    if "." not in name:
        return name, ""
    base, ext = name.rsplit(".", 1)
    return base, ext.lower().strip()


def normalize_base_name(base: str) -> str:
    """Sanitize the base name to be filesystem-safe."""
    base = base or ""
    base = base.strip().replace(" ", "_")
    base = _filename_keep.sub("-", base)
    base = base.strip("-._")
    return base or "file"


def safe_filename(original: str, *, force_ext: Optional[str] = None, with_uuid: bool = True) -> str:
    """
    Generate a safe filename:
      - sanitize the name
      - keep the extension or force a specific one
      - optionally append a UUID to avoid collisions
    """
    base, ext = split_name_ext(original)
    base = normalize_base_name(base)
    ext = (force_ext or ext or "").lower().strip(".")
    if with_uuid:
        uid = uuid.uuid4().hex
        if ext:
            return f"{base}-{uid}.{ext}"
        return f"{base}-{uid}"
    else:
        return f"{base}.{ext}" if ext else base


def is_allowed_ext(ext: str, kind: Optional[Literal["image", "video", "doc"]] = None) -> bool:
    """Check if an extension is allowed, optionally constrained by kind."""
    ext = (ext or "").lower().strip(".")
    if not ext:
        return False
    if kind == "image":
        return ext in ALLOWED_IMAGE_EXTS
    if kind == "video":
        return ext in ALLOWED_VIDEO_EXTS
    if kind == "doc":
        return ext in ALLOWED_DOC_EXTS
    return ext in ALLOWED_ALL_EXTS


def classify_kind(ext: str) -> Literal["image", "video", "doc"]:
    """Classify an extension into a logical kind for DB usage."""
    e = (ext or "").lower().strip(".")
    if e in ALLOWED_IMAGE_EXTS:
        return "image"
    if e in ALLOWED_VIDEO_EXTS:
        return "video"
    return "doc"


def build_deposit_evidence_path(
    booking_id: int,
    side: Literal["owner", "renter", "manager"],
    original_filename: str,
) -> Path:
    """
    Build a safe storage path for deposit evidence:
      uploads/deposits/{booking_id}/{side}/{uuid}.{ext}

    Returns the absolute path on disk (Path).
    """
    _, ext = split_name_ext(original_filename)
    ext = ext.lower().strip(".")
    if not is_allowed_ext(ext):
        raise ValueError(f"Extension '.{ext}' not allowed")

    # Use a short UUID + the extension
    file_name = f"{uuid.uuid4().hex}.{ext}"
    folder = DEPOSITS_DIR / str(int(booking_id)) / side
    ensure_dirs(folder)
    return folder / file_name


def to_public_uploads_path(full_path: Path) -> str:
    """
    Convert an absolute path under /uploads to a web-servable path:
      Example: '.../<root>/uploads/deposits/5/owner/xxx.jpg' -> '/uploads/deposits/5/owner/xxx.jpg'
    """
    p = str(full_path).replace("\\", "/")
    key = "/uploads/"
    if key in p:
        return p[p.index(key):]  # starts with /uploads/...
    # fallback: if slicing fails for any reason, return the original string
    return p


def map_kind_from_filename(name: str) -> Literal["image", "video", "doc"]:
    """Shortcut: infer kind from filename only."""
    _, ext = split_name_ext(name)
    return classify_kind(ext)
