# app/routes_evidence.py
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional, Literal, List

from datetime import datetime
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
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
    # متحكّم وديعة / أدمن (يُعامل كـ manager)
    if role == "admin" or bool(getattr(user, "is_deposit_manager", False)):
        return "manager"
    # إذا ليس له علاقة بالحجز
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

    # حماية عدد الملفات
    files = files or []
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_REQUEST} files per request")

    saved_any = False
    saved_records: List[int] = []

    # أنشئ المجلد
    evidence_dir = DEPOSITS_DIR / str(bk.id) / side
    ensure_dirs(evidence_dir)

    # 1) ملاحظة فقط (بلا ملف) — إذا لا يوجد ملفات وتم تمرير وصف
    if not files and (description or "").strip():
        ev = DepositEvidence(
            booking_id=bk.id,
            uploader_id=user.id,
            side=side,
            kind="note",
            file_path=None,
            description=description.strip(),
            created_at=datetime.utcnow(),
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        saved_any = True
        saved_records.append(ev.id)

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
        # نخزن مسارًا يبدأ بـ /uploads ليسهل عرضه في القالب
        if "/uploads/" not in rel_path:
            # حوّل إلى مسار نسبي من جذر المشروع
            try:
                rel_path = "/uploads" + rel_path.split("/uploads", 1)[1]
            except Exception:
                # fallback: مسار مطلق (لكن الأفضل إبقاءه نسبيًا)
                pass

        ev = DepositEvidence(
            booking_id=bk.id,
            uploader_id=user.id,
            side=side,
            kind=kind,
            file_path=rel_path,
            description=(description or "").strip() or None,
            created_at=datetime.utcnow(),
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        saved_any = True
        saved_records.append(ev.id)

    if not saved_any:
        raise HTTPException(status_code=400, detail="No files nor description provided")

    # إجعل حالة الوديعة نزاعًا عند رفع أدلة من المالك/المدير إذا كانت مفرج/لا شيء
    try:
        if side in ("owner", "manager"):
            current = (getattr(bk, "deposit_status", None) or "none").lower()
            if current in ("none", "refunded"):
                setattr(bk, "deposit_status", "in_dispute")
                setattr(bk, "status", "in_review")
        setattr(bk, "updated_at", datetime.utcnow())
        db.commit()
    except Exception:
        pass

    # إشعارات
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
        return JSONResponse({"ok": True, "saved_ids": saved_records})

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
    # السماح للمالك/المستأجر/الإدارة فقط
    _ = user_side_for_booking(user, bk)  # سيثير 403 تلقائيًا إذا ليس مخوّل

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