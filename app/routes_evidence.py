# app/routes_evidence.py
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional, Literal, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, User, DepositEvidence
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
# Helpers
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
    - ينشئ سجل في DepositEvidence لكل ملف
    - إذا لم تُرسل ملفات وأُرسلت ملاحظة -> يسجّل evidence من النوع note (بدون ملف)
    - يُرسل إشعارات
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    side = user_side_for_booking(user, bk)

    files = files or []
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_REQUEST} files per request")

    saved_any = False
    saved_record_ids: List[int] = []
    saved_files: List[str] = []
    comment = (description or "").strip()

    evidence_dir = DEPOSITS_DIR / str(bk.id) / side
    ensure_dirs(evidence_dir)

    # 1) ملاحظة فقط (بلا ملف)
    if not files and comment:
        ev = DepositEvidence(
            booking_id=bk.id,
            uploader_id=user.id,
            side=side,
            kind="note",
            file_path=None,
            description=comment,
            created_at=datetime.utcnow(),
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        saved_any = True
        saved_record_ids.append(ev.id)

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

        kind = classify_kind(ext)
        rel_path = str(full_path).replace("\\", "/")
        if "/uploads/" not in rel_path:
            try:
                rel_path = "/uploads" + rel_path.split("/uploads", 1)[1]
            except Exception:
                pass

        ev = DepositEvidence(
            booking_id=bk.id,
            uploader_id=user.id,
            side=side,
            kind=kind,
            file_path=rel_path,
            description=comment or None,
            created_at=datetime.utcnow(),
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        saved_any = True
        saved_record_ids.append(ev.id)
        saved_files.append(rel_path)

    if not saved_any:
        raise HTTPException(status_code=400, detail="No files nor description provided")

    # تحديثات الحالة العامة بعد أي رفع
    now = datetime.utcnow()
    try:
        setattr(bk, "updated_at", now)
        db.commit()
    except Exception:
        pass

    # =========================
    # ✅ تعديل مطلوب: إذا كان الرافع مستأجرًا والحالة تنتظر ردّه (awaiting_renter)
    #    → نحولها إلى نزاع in_dispute + مراجعة in_review + نسجل رده ونخطر الجميع
    # =========================
    try:
        current_status = (getattr(bk, "deposit_status", None) or "").lower()
        if side == "renter" and current_status == "awaiting_renter":
            bk.deposit_status = "in_dispute"
            bk.status = "in_review"
            bk.updated_at = now

            # حفظ تعليق المستأجر (اختياري إن كان لديك هذا الحقل)
            try:
                old_note = (getattr(bk, "renter_response_text", "") or "").strip()
                new_note = (old_note + ("\n" if old_note and comment else "") + (comment or "")).strip()
                setattr(bk, "renter_response_text", new_note or None)
                setattr(bk, "renter_response_at", now)
            except Exception:
                pass

            # سجل تدقيق
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

            db.commit()

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
                return JSONResponse({"ok": True, "saved_ids": saved_record_ids})
            return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)
    except Exception:
        # لا نكسر العملية لو حدث خطأ في الفرع السابق
        pass

    # إشعارات افتراضية حسب الجهة الرافعِة
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
        return JSONResponse({"ok": True, "saved_ids": saved_record_ids})

    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

# =========================
# API: جلب الأدلة بشكل JSON
# =========================
@router.get("/deposits/{booking_id}/evidence")
def list_deposit_evidence(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يُرجع قائمة الأدلة المرفوعة للحجز بترتيب زمني هابط (الأحدث أولًا).
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    _ = user_side_for_booking(user, bk)

    rows = (
        db.query(DepositEvidence)
        .filter(DepositEvidence.booking_id == booking_id)
        .order_by(DepositEvidence.created_at.desc())
        .all()
    )

    def to_dict(ev: DepositEvidence):
        return {
            "id": ev.id,
            "side": ev.side,
            "kind": ev.kind,
            "file": ev.file_path,
            "description": ev.description,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "uploader_id": ev.uploader_id,
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
    صفحة بسيطة لاختبار الرفع يدويًا (اختيارية).
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