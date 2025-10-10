"""
app/utils_uploads.py
---------------------
ملف أدوات المساعدة (Utilities) لإدارة رفع الملفات والصور بشكل آمن داخل المنصة.

الاستخدام الحالي:
  - رفع صور أو فيديوهات الأدلة في قضايا الوديعة (Deposit Evidence)
  - تنظيم الملفات في مجلدات حسب نوعها مثل:
      /uploads/deposits/{booking_id}/
      /uploads/items/{item_id}/
  - التحقق من الامتدادات المسموح بها فقط.
"""

import os
import secrets
from datetime import datetime
from fastapi import UploadFile, HTTPException

# المسار الأساسي لكل الرفع
UPLOAD_ROOT = "uploads"

# الامتدادات المسموح بها
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".webp"}

def ensure_dir(path: str):
    """يتأكد أن المجلد موجود (وإن لم يكن، ينشئه)."""
    os.makedirs(path, exist_ok=True)
    return path


def get_extension(filename: str):
    """إرجاع الامتداد بصيغة صغيرة."""
    return os.path.splitext(filename)[1].lower()


def is_allowed(filename: str):
    """يتأكد من أن الامتداد مسموح."""
    return get_extension(filename) in ALLOWED_EXTENSIONS


def safe_filename(prefix: str = "file", ext: str = ".jpg"):
    """يولّد اسم ملف آمن وعشوائي."""
    token = secrets.token_hex(8)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}_{timestamp}_{token}{ext}"


def upload_to_deposit_folder(booking_id: int, file: UploadFile):
    """
    يحفظ ملف الأدلة الخاص بقضية وديعة معينة:
      المسار: /uploads/deposits/{booking_id}/
    """
    ext = get_extension(file.filename)
    if not is_allowed(file.filename):
        raise HTTPException(status_code=400, detail=f"❌ الامتداد غير مسموح: {ext}")

    # بناء المسار الآمن
    target_dir = ensure_dir(os.path.join(UPLOAD_ROOT, "deposits", str(booking_id)))
    filename = safe_filename("evidence", ext)
    file_path = os.path.join(target_dir, filename)

    # حفظ فعلي
    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    rel_path = os.path.relpath(file_path, ".")
    return rel_path


def upload_to_item_folder(item_id: int, file: UploadFile):
    """
    يحفظ صور العناصر (products/items):
      المسار: /uploads/items/{item_id}/
    """
    ext = get_extension(file.filename)
    if not is_allowed(file.filename):
        raise HTTPException(status_code=400, detail=f"❌ الامتداد غير مسموح: {ext}")

    target_dir = ensure_dir(os.path.join(UPLOAD_ROOT, "items", str(item_id)))
    filename = safe_filename("photo", ext)
    file_path = os.path.join(target_dir, filename)

    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    rel_path = os.path.relpath(file_path, ".")
    return rel_path


def remove_upload(path: str):
    """يحذف ملف مرفوع بأمان إذا وُجد."""
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except Exception:
        pass
    return False


def list_uploads_for_deposit(booking_id: int):
    """يُرجع قائمة الأدلة (صور/فيديوهات) الموجودة لحجز معيّن."""
    folder = os.path.join(UPLOAD_ROOT, "deposits", str(booking_id))
    if not os.path.exists(folder):
        return []
    return [os.path.join(folder, f) for f in os.listdir(folder) if is_allowed(f)]