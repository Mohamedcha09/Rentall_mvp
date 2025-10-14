# app/routes_evidence.py
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

router = APIRouter(tags=["deposit-evidence"])

# =========================
# إعدادات الحفظ / الامتدادات
# =========================
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent                  # -> /opt/render/project/src
UPLOADS_DIR = PROJECT_ROOT / "uploads"          # -> /opt/render/project/src/uploads ✅
DEPOSITS_DIR = UPLOADS_DIR / "deposits"

ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
ALLOWED_VIDEO_EXTS = {"mp4", "mov", "webm"}
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

def classify_kind(ext: str) -> Literal["image","video","doc"]:
    if ext in ALLOWED_IMAGE_EXTS:
        return "image"
    if ext in ALLOWED_VIDEO_EXTS:
        return "video"
    return "doc"

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
    """
    نكشف وجود الأعمدة في deposit_evidences لنُعامل الفروقات:
    - uploader_id / by_user_id
    - file_path / file
    """
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
    """
    يُدخل صفًا في deposit_evidences مع دعم كلا الاسمين (uploader_id/by_user_id) و (file_path/file).
    لو العمودين موجودين نملأهما معاً بنفس القيمة لضمان عدم كسر قيود NOT NULL.
    """
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

    # أعمدة المستخدم
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
    else:
        # لا يوجد عمود للهوية (نادر جدًا) — نكمل بدونها
        pass

    # أعمدة الملف
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
    else:
        # لا يوجد عمود ملف — مقبول لو kind = note
        pass

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
    """
    نقرأ باستخدام COALESCE لنُرجع uploader_id موحد و file_path موحد مهما كان اسم العمود الحقيقي.
    """
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
# API: رفع الأدلة (صور/فيديو/مستندات + ملاحظة)
# =========================
@router.post("/deposits/{booking_id}/evidence/upload")
async def upload_deposit_evidence(
    booking_id: int,
    request: Request,
    description: str = Form(""),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يرفع أدلة من الطرفين (المالك/المستأجر) أو المتحكّم (manager).
    - يحفظ الملفات تحت: /uploads/deposits/{booking_id}/{side}/<uuid>.<ext>
    - يُدخل الصفوف في deposit_evidences مع دعم (uploader_id/by_user_id) و (file_path/file)
    - إذا لم تُرسل ملفات وأُرسلت ملاحظة -> يسجّل evidence من النوع note (بدون ملف)
    - يُرسل إشعارات
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    side = user_side_for_booking(user, bk)

    # حماية عدد الملفات
    files = files or []
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_REQUEST} files per request")

    saved_any = False
    saved_ids: List[int] = []
    saved_files: List[str] = []
    comment = (description or "").strip()

    # أنشئ المجلد
    evidence_dir = DEPOSITS_DIR / str(bk.id) / side
    ensure_dirs(evidence_dir)

    # 1) ملاحظة فقط (بدون ملف)
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

        # نخزن دائمًا مسارًا عامًا يبدأ بـ /uploads ليسهل العرض
        rel_path = str(full_path).replace("\\", "/")
        if "/uploads/" not in rel_path:
            try:
                rel_path = "/uploads" + rel_path.split("/uploads", 1)[1]
            except Exception:
                rel_path = rel_path  # fallback

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

    # تحديثات عامة
    now = datetime.utcnow()
    try:
        setattr(bk, "updated_at", now)
        db.commit()
    except Exception:
        pass

    # =========================
    # إذا رفع المستأجر أثناء انتظار ردّه → نحولها إلى نزاع ونلغي المهلة
    # =========================
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
            except Exception:
                pass
            try:
                db.commit()
            except Exception:
                pass

            # إشعارات
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

    # إشعارات افتراضية حسب جهة الرفع
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
            # manager
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

    # دعم JSON أو ريديركت
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"ok": True, "saved_ids": saved_ids})

    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

# =========================
# API: جلب الأدلة بشكل JSON (يقرأ ديناميكيًا حسب أسماء الأعمدة)
# =========================
@router.get("/deposits/{booking_id}/evidence")
def list_deposit_evidence(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يُرجع قائمة الأدلة المرفوعة للحجز بترتيب زمني هابط (الأحدث أولًا).
    يدعم كلا الاسمين uploader_id/by_user_id وأيضًا file_path/file.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    _ = user_side_for_booking(user, bk)  # سيثير 403 تلقائيًا إذا ليس مخوّل

    rows = _select_evidence_rows(booking_id)

    def to_dict(r: Dict[str, Any]):
        return {
            "id": r.get("id"),
            "side": r.get("side"),
            "kind": r.get("kind"),
            "file": r.get("file_path"),
            "description": r.get("description"),
            "created_at": (r.get("created_at").isoformat() if hasattr(r.get("created_at"), "isoformat") else r.get("created_at")),
            "uploader_id": r.get("uploader_id"),
        }

    return JSONResponse({
        "booking_id": booking_id,
        "count": len(rows),
        "items": [to_dict(r) for r in rows]
    })

# =========================
# (اختياري) نموذج HTML بسيط للرفع
# =========================
@router.get("/deposits/{booking_id}/evidence/form")
def simple_evidence_form(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    صفحة بسيطة لاختبار الرفع يدويًا (اختياري).
    """
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
        <form method="post" action="/deposits/{bk.id}/evidence/upload" enctype="multipart/form-data">
          <div>
            <label>الوصف (اختياري)</label><br/>
            <textarea name="description" rows="3" cols="60" placeholder="ملاحظة قصيرة…"></textarea>
          </div>
          <div style="margin-top:8px">
            <label>ملفات (اختياري | حتى {MAX_FILES_PER_REQUEST})</label><br/>
            <input type="file" name="files" multiple />
            <div style="opacity:.7;font-size:12px;margin-top:4px">
              المسموح: صور (jpg/png/webp/gif) — فيديو (mp4/mov/webm) — مستند (pdf)
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