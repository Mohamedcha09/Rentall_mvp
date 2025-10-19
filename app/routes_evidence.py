# app/routes_evidence.py (CLEAN, no Jinja inside)
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional, Literal, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db, engine as _engine
from .models import Booking, User
from .notifications_api import push_notification, notify_admins

# ===== SMTP Email (fallback) =====
try:
    from .email_service import send_email
except Exception:
    def send_email(to, subject, html_body, text_body=None, cc=None, bcc=None, reply_to=None):
        return False  # NO-OP مؤقتًا

BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")

def _user_email(db: Session, user_id: int) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return (u.email or None) if u else None

def _admin_emails(db: Session) -> list[str]:
    admins = db.query(User).filter(
        ((User.role == "admin") | (User.is_deposit_manager == True))
    ).all()
    return [a.email for a in admins if getattr(a, "email", None)]

router = APIRouter(tags=["deposit-evidence"])

# =========================
# إعدادات الحفظ / الامتدادات (موحّدة مع routes_deposits.py)
# =========================
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
UPLOADS_DIR = PROJECT_ROOT / "uploads"
DEPOSITS_DIR = UPLOADS_DIR / "deposits"

ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "heic", "heif", "bmp", "tiff"}  # ← أضفنا heic/heif
ALLOWED_VIDEO_EXTS = {"mp4", "mov", "webm", "m4v", "avi", "wmv"}
ALLOWED_DOC_EXTS   = {"pdf"}
ALLOWED_ALL_EXTS = ALLOWED_IMAGE_EXTS | ALLOWED_VIDEO_EXTS | ALLOWED_DOC_EXTS

MAX_FILES_PER_REQUEST = 10  # حماية بسيطة

# =========================
# Helpers: هوية المستخدم/الحجز
# =========================
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None

def require_auth(user: Optional[User]):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

def require_booking(db: Session, booking_id: int) -> Booking:
    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    return bk

def user_side_for_booking(user: User, bk: Booking) -> Literal["owner","renter","manager"]:
    role = (getattr(user, "role", "") or "").lower()
    if user.id == bk.owner_id:
        return "owner"
    if user.id == bk.renter_id:
        return "renter"
    if role == "admin" or bool(getattr(user, "is_deposit_manager", False)):
        return "manager"
    raise HTTPException(status_code=403, detail="Forbidden")

# =========================
# Helpers: ملفات ومسارات
# =========================
def safe_ext(filename: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower().strip()
    return ext

def classify_kind(ext: str) -> Literal["image","video","doc","note"]:
    if ext in ALLOWED_IMAGE_EXTS:
        return "image"
    if ext in ALLOWED_VIDEO_EXTS:
        return "video"
    if ext in ALLOWED_DOC_EXTS:
        return "doc"
    return "note"

def ensure_dirs(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def save_upload_file(dst_path: Path, up: UploadFile) -> None:
    with dst_path.open("wb") as f:
        while True:
            chunk = up.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

# =========================
# Helpers: طبقة توافق مع الجدول (uploader_id/by_user_id, file_path/file)
# =========================
def _evidence_cols() -> Dict[str, bool]:
    cols = {
        "id": False, "booking_id": False, "uploader_id": False, "by_user_id": False,
        "side": False, "kind": False, "file_path": False, "file": False,
        "description": False, "created_at": False
    }
    try:
        with _engine.begin() as conn:
            rows = conn.exec_driver_sql("PRAGMA table_info('deposit_evidences')").all()
        for _, name, *_ in rows:
            if name in cols:
                cols[name] = True
    except Exception:
        pass
    return cols

def _insert_evidence_row(values: Dict[str, Any]) -> int:
    cols = _evidence_cols()
    has_uploader = cols.get("uploader_id", False)
    has_by_user  = cols.get("by_user_id",  False)
    has_filepath = cols.get("file_path",   False)
    has_file     = cols.get("file",        False)

    insert_cols = ["booking_id", "side", "kind", "description", "created_at"]
    params = {
        "booking_id": values["booking_id"],
        "side": values["side"],
        "kind": values["kind"],
        "description": values.get("description"),
        "created_at": values.get("created_at") or datetime.utcnow(),
    }

    if has_uploader and has_by_user:
        insert_cols += ["uploader_id", "by_user_id"]
        params["uploader_id"] = values["uploader_id"]
        params["by_user_id"]  = values["uploader_id"]
    elif has_uploader:
        insert_cols.append("uploader_id")
        params["uploader_id"] = values["uploader_id"]
    elif has_by_user:
        insert_cols.append("by_user_id")
        params["by_user_id"]  = values["uploader_id"]

    fp = values.get("file_path")
    if has_filepath and has_file:
        insert_cols += ["file_path", "file"]
        params["file_path"] = fp
        params["file"]      = fp
    elif has_filepath:
        insert_cols.append("file_path")
        params["file_path"] = fp
    elif has_file:
        insert_cols.append("file")
        params["file"] = fp

    placeholders = ", ".join([f":{c}" for c in insert_cols])
    columns_sql  = ", ".join(insert_cols)
    sql = f"INSERT INTO deposit_evidences ({columns_sql}) VALUES ({placeholders})"

    with _engine.begin() as conn:
        res = conn.exec_driver_sql(sql, params)
        try:
            new_id = int(res.lastrowid or 0)
        except Exception:
            new_id = 0
    return new_id

def _select_evidence_rows(booking_id: int) -> List[Dict[str, Any]]:
    cols = _evidence_cols()
    has_uploader = cols.get("uploader_id", False)
    has_by_user  = cols.get("by_user_id",  False)
    has_filepath = cols.get("file_path",   False)
    has_file     = cols.get("file",        False)

    uploader_expr = (
        "COALESCE(uploader_id, by_user_id)" if (has_uploader and has_by_user)
        else ("uploader_id" if has_uploader else ("by_user_id" if has_by_user else "NULL"))
    )
    file_expr = (
        "COALESCE(file_path, file)" if (has_filepath and has_file)
        else ("file_path" if has_filepath else ("file" if has_file else "NULL"))
    )

    select_cols = f"id, booking_id, {uploader_expr} as uploader_id, side, kind, {file_expr} as file_path, description, created_at"
    sql = f"""
        SELECT {select_cols}
        FROM deposit_evidences
        WHERE booking_id = :bid
        ORDER BY created_at DESC, id DESC
    """
    with _engine.begin() as conn:
        rows = conn.exec_driver_sql(sql, {"bid": booking_id}).mappings().all()
        return [dict(r) for r in rows]

# =========================
# API: رفع الأدلة (Alias غير متصادم)
# =========================
# NOTE: كانت هنا نسخة متصادمة:
# @router.post("/deposits/{booking_id}/evidence/upload")
# تم تعليقها لتجنّب التعارض مع routes_deposits.py، مع إبقاء Alias يعمل:
@router.post("/evidence-api/deposits/{booking_id}/upload")
async def upload_deposit_evidence(
    booking_id: int,
    request: Request,
    description: str = Form(""),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يرفع أدلة من الطرفين (المالك/المستأجر/المتحكّم).
    - يحفظ الملفات تحت: /uploads/deposits/{booking_id}/{side}/<uuid>.<ext>
    - يُدخل الصفوف في deposit_evidences
    - إذا لم تُرسل ملفات وأُرسلت ملاحظة -> kind=note
    - يُرسل إشعارات
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    side = user_side_for_booking(user, bk)

    files = files or []
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_REQUEST} files per request")

    saved_any = False
    saved_ids: List[int] = []
    saved_files: List[str] = []
    comment = (description or "").strip()

    evidence_dir = DEPOSITS_DIR / str(bk.id) / side
    ensure_dirs(evidence_dir)

    # 1) ملاحظة فقط
    if not files and comment:
        ev_id = _insert_evidence_row({
            "booking_id": bk.id,
            "uploader_id": user.id,
            "side": side,
            "kind": "note",
            "file_path": None,
            "description": comment,
            "created_at": datetime.utcnow(),
        })
        if ev_id:
            saved_any = True
            saved_ids.append(ev_id)

    # 2) ملفات
    for up in files:
        filename = up.filename or ""
        ext = safe_ext(filename)
        if ext not in ALLOWED_ALL_EXTS:
            raise HTTPException(status_code=400, detail=f"Extension .{ext} not allowed")

        uid = uuid.uuid4().hex
        stored_name = f"{uid}.{ext}"
        full_path = evidence_dir / stored_name

        try:
            save_upload_file(full_path, up)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to store file: {e}")

        rel_path = f"/uploads/deposits/{bk.id}/{side}/{stored_name}"
        kind = classify_kind(ext)
        ev_id = _insert_evidence_row({
            "booking_id": bk.id,
            "uploader_id": user.id,
            "side": side,
            "kind": kind,
            "file_path": rel_path,
            "description": (comment or None),
            "created_at": datetime.utcnow(),
        })
        if ev_id:
            saved_any = True
            saved_ids.append(ev_id)
            saved_files.append(rel_path)

    if not saved_any:
        raise HTTPException(status_code=400, detail="No files nor description provided")

    now = datetime.utcnow()
    try:
        setattr(bk, "updated_at", now)
        db.commit()
    except Exception:
        pass

    # لو المستأجر ردّ أثناء awaiting_renter → تحويل لنزاع + إشعارات DM
    try:
        current_status = (getattr(bk, "deposit_status", None) or "").lower()
        if side == "renter" and current_status == "awaiting_renter":
            try:
                bk.deposit_status = "in_dispute"
                bk.status = "in_review"
            except Exception:
                pass
            try:
                setattr(bk, "renter_response_at", now)
            except Exception:
                pass
            try:
                setattr(bk, "renter_response_deadline_at", None)
            except Exception:
                pass
            try:
                old_note = (getattr(bk, "renter_response_text", "") or "").strip()
                new_note = (old_note + ("\n" if old_note and comment else "") + (comment or "")).strip()
                setattr(bk, "renter_response_text", new_note or None)
            except Exception:
                pass
            try:
                from .routes_deposits import _audit
                _audit(
                    db,
                    actor=user,
                    bk=bk,
                    action="renter_uploaded_evidence",
                    details={"files": saved_files, "comment": comment},
                )
                db.commit()
            except Exception:
                pass

            try:
                push_notification(
                    db, bk.owner_id, "ردّ المستأجر على قرار الخصم",
                    f"قام المستأجر برفع أدلة/ملاحظة على الحجز #{bk.id}.",
                    f"/dm/deposits/{bk.id}", "deposit"
                )
                notify_admins(
                    db, "ردّ مستأجر جديد بخصوص قرار الخصم",
                    f"تم استلام أدلة من المستأجر على الحجز #{bk.id}.",
                    f"/dm/deposits/{bk.id}"
                )
            except Exception:
                pass

            accept = (request.headers.get("accept") or "").lower()
            if "application/json" in accept:
                return JSONResponse({"ok": True, "saved_ids": saved_ids})
            return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)
    except Exception:
        pass

    # إشعارات افتراضية حسب الجهة
    try:
        if side == "owner":
            push_notification(
                db, bk.renter_id, "أدلة جديدة من المالك",
                f"تم رفع أدلة جديدة على قضية وديعة الحجز #{bk.id}.",
                f"/bookings/flow/{bk.id}", "deposit"
            )
        elif side == "renter":
            push_notification(
                db, bk.owner_id, "رد وأدلة من المستأجر",
                f"قام المستأجر بإضافة أدلة/ملاحظة على قضية وديعة الحجز #{bk.id}.",
                f"/bookings/flow/{bk.id}", "deposit"
            )
        else:
            push_notification(
                db, bk.owner_id, "تحديث على القضية",
                f"قام متحكّم الوديعة برفع/إرفاق أدلة على قضية #{bk.id}.",
                f"/bookings/flow/{bk.id}", "deposit"
            )
            push_notification(
                db, bk.renter_id, "تحديث على القضية",
                f"قام متحكّم الوديعة برفع/إرفاق أدلة على قضية #{bk.id}.",
                f"/bookings/flow/{bk.id}", "deposit"
            )
        notify_admins(db, "Evidence uploaded", f"حجز #{bk.id} — side={side}", f"/bookings/flow/{bk.id}")
    except Exception:
        pass

    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"ok": True, "saved_ids": saved_ids})
    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

# =========================
# API: جلب الأدلة JSON (Alias غير متصادم)
# =========================
# كانت هنا نسخة متصادمة:
# @router.get("/deposits/{booking_id}/evidence")
@router.get("/evidence-api/deposits/{booking_id}/evidence")
def list_deposit_evidence(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    _ = user_side_for_booking(user, bk)
    rows = _select_evidence_rows(booking_id)

    def to_dict(r: Dict[str, Any]):
        created = r.get("created_at")
        return {
            "id": r.get("id"),
            "side": r.get("side"),
            "kind": r.get("kind"),
            "file": r.get("file_path"),
            "description": r.get("description"),
            "created_at": (created.isoformat() if hasattr(created, "isoformat") else created),
            "uploader_id": r.get("uploader_id"),
        }

    return JSONResponse({
        "booking_id": booking_id,
        "count": len(rows),
        "items": [to_dict(r) for r in rows]
    })

# =========================
# نموذج HTML بسيط (Alias غير متصادم)
# =========================
# كانت هنا نسخة متصادمة:
# @router.get("/deposits/{booking_id}/evidence/form")
@router.get("/evidence-api/deposits/{booking_id}/evidence/form")
def simple_evidence_form(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    _ = user_side_for_booking(user, bk)

    html = f"""
    <html lang="ar">
      <head>
        <meta charset="utf-8" />
        <title>رفع أدلة — حجز #{bk.id}</title>
      </head>
      <body style="font-family: sans-serif; padding:20px">
        <h3>رفع أدلة — حجز #{bk.id}</h3>
        <form method="post" action="/evidence-api/deposits/{bk.id}/upload" enctype="multipart/form-data">
          <div>
            <label>الوصف (اختياري)</label><br/>
            <textarea name="description" rows="3" cols="60" placeholder="ملاحظة قصيرة…"></textarea>
          </div>
          <div style="margin-top:8px">
            <label>ملفات (اختياري | حتى {MAX_FILES_PER_REQUEST})</label><br/>
            <input type="file" name="files" multiple />
            <div style="opacity:.7;font-size:12px;margin-top:4px">
              المسموح: صور (jpg/png/webp/gif/heic/heif) — فيديو (mp4/mov/webm/m4v/avi/wmv) — مستند (pdf)
            </div>
          </div>
          <div style="margin-top:12px">
            <button type="submit">رفع</button>
            <a href="/bookings/flow/{bk.id}" style="margin-right:8px">رجوع لصفحة الحجز</a>
          </div>
        </form>
      </body>
    </html>
    """
    return HTMLResponse(html)

# =========================
# Redirect قديم — جعلناه Alias غير متصادم
# =========================
# كانت هنا نسخة متصادمة:
# @router.get("/deposits/{booking_id}/report")
@router.get("/evidence-api/deposits/{booking_id}/report-redirect")
def deposit_report_redirect(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    إشعارات قديمة كانت ترسل إلى /deposits/{id}/report.
    هنا alias آمن:
      - إذا كان المستخدم DM/Admin → صفحة القضية
      - غير ذلك → صفحة تدفّق الحجز
    """
    if user and (getattr(user, "is_deposit_manager", False) or (getattr(user, "role", "") or "").lower() == "admin"):
        return RedirectResponse(url=f"/dm/deposits/{booking_id}", status_code=303)
    return RedirectResponse(url=f"/bookings/flow/{booking_id}", status_code=303)

# =========================
# أرشفة القوالب التي كانت ملتصقة هنا (بدون حذف)
# =========================
ARCHIVED_JINJA_TEMPLATES = r"""
[تم نقل كتل Jinja والـHTML التي كانت هنا إلى ملفاتها داخل templates/.
أبقينا نسخة أرشيفية نصّية فقط لكي لا نفقد المحتوى مفهوميًا، بدون تأثير على بايثون.]
"""