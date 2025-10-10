# app/utils_uploads.py
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Literal, Optional, Tuple

# ملاحظة: مشروعك يركّب الـ uploads في app/main.py على:
#   UPLOADS_DIR = <root>/uploads
# هذا الملف يبني نفس المسارات بشكل آمن.

# جذر ملفات الرفع بالنسبة لبنية مشروعك الحالية:
PROJECT_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = PROJECT_DIR / "uploads"      # ../uploads
DEPOSITS_DIR = UPLOADS_DIR / "deposits"    # ../uploads/deposits

# الامتدادات المسموح بها
ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
ALLOWED_VIDEO_EXTS = {"mp4", "mov", "webm"}
ALLOWED_DOC_EXTS   = {"pdf"}
ALLOWED_ALL_EXTS = ALLOWED_IMAGE_EXTS | ALLOWED_VIDEO_EXTS | ALLOWED_DOC_EXTS

# تطبيع أسماء الملفات
_filename_keep = re.compile(r"[^A-Za-z0-9._-]+")


def ensure_dirs(path: Path) -> None:
    """ينشئ المجلدات إذا لم تكن موجودة (آمن للتوازي)."""
    path.mkdir(parents=True, exist_ok=True)


def split_name_ext(name: str) -> Tuple[str, str]:
    """يفصل الاسم عن الامتداد ويعيد (الاسم بدون الامتداد, الامتداد بدون النقطة)."""
    name = name or ""
    if "." not in name:
        return name, ""
    base, ext = name.rsplit(".", 1)
    return base, ext.lower().strip()


def normalize_base_name(base: str) -> str:
    """ينظّف الاسم الأساسي ليكون آمن ضمن نظام الملفات."""
    base = base or ""
    base = base.strip().replace(" ", "_")
    base = _filename_keep.sub("-", base)
    base = base.strip("-._")
    return base or "file"


def safe_filename(original: str, *, force_ext: Optional[str] = None, with_uuid: bool = True) -> str:
    """
    يولد اسم ملف آمن:
      - ينظّف الاسم
      - يحافظ على الامتداد أو يفرض امتداداً معيّناً
      - يمكن أن يضيف UUID لتفادي التصادم
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
    """يتحقق من سماحية الامتداد اختيارياً حسب نوع الملف."""
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
    """يصنّف الامتداد إلى نوع منطقي للاستخدام في قاعدة البيانات."""
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
    يبني مساراً آمناً لتخزين دليل وديعة:
      uploads/deposits/{booking_id}/{side}/{uuid}.{ext}

    يُرجع المسار الكامل على القرص (Path).
    """
    _, ext = split_name_ext(original_filename)
    ext = ext.lower().strip(".")
    if not is_allowed_ext(ext):
        raise ValueError(f"Extension '.{ext}' not allowed")

    # نستخدم UUID قصير + الامتداد
    file_name = f"{uuid.uuid4().hex}.{ext}"
    folder = DEPOSITS_DIR / str(int(booking_id)) / side
    ensure_dirs(folder)
    return folder / file_name


def to_public_uploads_path(full_path: Path) -> str:
    """
    يحوّل مساراً مطلقاً داخل مجلد /uploads إلى مسار يمكن تقديمه عبر الويب:
      مثال: '.../<root>/uploads/deposits/5/owner/xxx.jpg' -> '/uploads/deposits/5/owner/xxx.jpg'
    """
    p = str(full_path).replace("\\", "/")
    key = "/uploads/"
    if key in p:
        return p[p.index(key):]  # يبدأ بـ /uploads/...
    # fallback: إن لم ينجح القصّ لأي سبب، أعد المسار كما هو
    return p


def map_kind_from_filename(name: str) -> Literal["image", "video", "doc"]:
    """Shortcut: استنتاج النوع من اسم الملف فقط."""
    _, ext = split_name_ext(name)
    return classify_kind(ext)