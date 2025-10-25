# app/reports.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Item

# استيرادات اختيارية لحماية التشغيل لو الجداول/الخدمات غير متوفرة
try:
    from .models import Report, ReportActionLog  # مضافة في models.py
except Exception:  # pragma: no cover
    Report = None
    ReportActionLog = None

try:
    from .notifications_api import push_notification  # إشعارات داخلية
except Exception:  # pragma: no cover
    def push_notification(db: Session, user_id: int, title: str, body: str, link_url: str = "/", kind: str = "info"):
        return None

try:
    from .email_service import send_email  # بريد (اختياري)
except Exception:  # pragma: no cover
    def send_email(*args, **kwargs):
        return None


router = APIRouter()
BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")


# =========================
# Helpers
# =========================
def _require_login(request: Request) -> Dict[str, Any]:
    u = request.session.get("user")
    if not u:
        raise HTTPException(status_code=401, detail="login-required")
    return u


def _get_item_owner_id(db: Session, item_id: int) -> Optional[int]:
    it = db.query(Item).filter(Item.id == item_id).first()
    return it.owner_id if it else None


def _notify_owner_and_moderators(
    db: Session,
    owner_id: Optional[int],
    reporter_name: str,
    item_id: int,
    reason: str,
    image_index: Optional[int] = None,
):
    """إشعار المالك + كل الأدمن والمودز."""
    label = f"بلاغ على المنشور #{item_id}"
    if image_index is not None:
        label = f"بلاغ على صورة #{image_index} من المنشور #{item_id}"

    body = f"المبلِّغ: {reporter_name}\nالسبب: {reason}"
    link = f"/items/{item_id}"

    # 1) المالك
    if owner_id:
        try:
            push_notification(db, owner_id, "🚩 " + label, body, link, "report")
        except Exception:
            pass

    # 2) كل الأدمن + كل المودز
    try:
        moderators = (
            db.query(User)
            .filter((User.role == "admin") | (getattr(User, "is_mod", False) == True))  # noqa: E712
            .all()
        )
        for m in moderators:
            try:
                push_notification(db, m.id, "🚩 " + label, body, link, "report")
            except Exception:
                pass
    except Exception:
        pass

    # (اختياري) بريد للأدمن فقط
    try:
        admins = db.query(User).filter(User.role == "admin").all()
        for a in admins:
            subj = "🚩 بلاغ جديد"
            html = f"""
              <div style="direction:rtl;text-align:right;font-family:Tahoma,Arial,sans-serif;line-height:1.8">
                <h3>🚩 بلاغ جديد</h3>
                <p><b>المبلِّغ:</b> {reporter_name}</p>
                <p><b>السبب:</b> {reason}</p>
                <p><a href="{BASE_URL}/items/{item_id}" target="_blank">فتح المنشور</a></p>
              </div>
            """
            send_email(a.email, subj, html, text_body=f"بلاغ جديد — {label}\n{body}\n{BASE_URL}{link}")
    except Exception:
        pass


def _build_report_instance(
    reporter_id: int,
    item_id: int,
    reason: str,
    note: Optional[str],
    image_index: Optional[int],
    payload: Optional[Dict[str, Any]] = None,
):
    """
    إنشاء كائن Report مع مراعاة اختلاف السكيمة: لا نضيف إلا الحقول الموجودة فعلاً.
    """
    if Report is None:
        raise HTTPException(status_code=500, detail="Report model is missing")

    data: Dict[str, Any] = {
        "reporter_id": reporter_id,
        "reason": reason[:120] if reason else "",
        "status": "pending",
        "created_at": datetime.utcnow(),
    }

    # أضِف فقط الحقول الموجودة فعليًا في الموديل/الجدول
    if hasattr(Report, "item_id"):
        data["item_id"] = item_id

    if note and hasattr(Report, "note"):
        data["note"] = (note or "").strip() or None

    if image_index is not None and hasattr(Report, "image_index"):
        try:
            data["image_index"] = int(image_index)
        except Exception:
            pass

    if hasattr(Report, "target_type"):
        data["target_type"] = "image" if image_index is not None else "item"

    if payload and hasattr(Report, "payload_json"):
        try:
            import json
            data["payload_json"] = json.dumps(payload, ensure_ascii=False)
        except Exception:
            pass

    return Report(**data)


def _log_action(db: Session, report_id: int, actor_id: int, action: str, note: Optional[str] = None):
    if ReportActionLog is None:
        return
    try:
        log = ReportActionLog(
            report_id=report_id,
            actor_id=actor_id,
            action=action,
            note=(note or "").strip() or None,
            created_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()


# =========================
# API: إنشاء بلاغ (المسار الرئيسي)
# =========================
@router.post("/reports")
async def create_report(
    request: Request,
    db: Session = Depends(get_db),

    # ندعم Form وكذلك JSON
    item_id: int = Form(None),
    reason: str = Form(None),
    note: str | None = Form(None),
    image_index: int | None = Form(None),
):
    """
    ينشئ بلاغًا على منشور/صورة. يقبل Form أو JSON.
    لو أُرسل JSON، سنقرأه من body مباشرةً.
    """
    u = _require_login(request)

    # السماح بإرسال JSON (mobile/SPA)
    if item_id is None or reason is None:
        try:
            data = await request.json()
            item_id = int(data.get("item_id")) if data.get("item_id") is not None else None
            reason = data.get("reason")
            note = data.get("note")
            image_index = data.get("image_index")
            if image_index is not None:
                try:
                    image_index = int(image_index)
                except Exception:
                    image_index = None
        except Exception:
            pass

    if not item_id or not reason:
        raise HTTPException(status_code=422, detail="missing-required-fields")

    # تحقّق من وجود العنصر ومعرفة المالك
    owner_id = _get_item_owner_id(db, item_id)
    if not owner_id:
        raise HTTPException(status_code=404, detail="item-not-found")

    # أنشئ البلاغ
    try:
        report = _build_report_instance(
            reporter_id=int(u["id"]),
            item_id=int(item_id),
            reason=str(reason),
            note=note,
            image_index=image_index,
            payload={"ip": request.client.host if request.client else None},
        )
        db.add(report)
        db.commit()
        db.refresh(report)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="failed-to-create-report") from e

    # سجلّ الإجراء الأولي "submitted"
    _log_action(db, getattr(report, "id", 0), int(u["id"]), "submitted", note)

    # إشعار المالك + الأدمن/المود
    try:
        reporter_name = f"{u.get('first_name','').strip()} {u.get('last_name','').strip()}".strip() or f"User#{u['id']}"
        _notify_owner_and_moderators(db, owner_id, reporter_name, int(item_id), str(reason), image_index)
    except Exception:
        pass

    return JSONResponse(
        {
            "ok": True,
            "message": "تم إرسال البلاغ، شكرًا لمساهمتك.",
            "report_id": getattr(report, "id", None),
            "status": getattr(report, "status", "pending"),
        },
        status_code=201,
    )


# =========================
# (توافق قديم) /reports/new → يعيد استخدام نفس المنطق
# =========================
@router.post("/reports/new")
async def create_report_legacy(
    request: Request,
    db: Session = Depends(get_db),
    item_id: int = Form(None),
    reason: str = Form(None),
    note: str | None = Form(None),
    image_index: int | None = Form(None),
):
    return await create_report(
        request=request,
        db=db,
        item_id=item_id,
        reason=reason,
        note=note,
        image_index=image_index,
    )


# =========================
# صفحة إدارة البلاغات (اختيارية)
# =========================
@router.get("/admin/reports")
def admin_reports_page(request: Request, db: Session = Depends(get_db)):
    """
    يعرض قالب admin/reports.html إن كان موجودًا؛ وإلا يرجع JSON بسيط.
    الوصول مقيّد للأدمن/المود.
    """
    sess = request.session.get("user")
    if not sess or not (str(sess.get("role", "")).lower() == "admin" or bool(sess.get("is_mod"))):
        return RedirectResponse(url="/login", status_code=303)

    try:
        if Report is None:
            raise RuntimeError("Report model missing")
        reports = (
            db.query(Report)
            .order_by(getattr(Report, "created_at").desc() if hasattr(Report, "created_at") else None)
            .limit(50)
            .all()
        )
        return request.app.templates.TemplateResponse(
            "admin/reports.html",
            {
                "request": request,
                "title": "البلاغات",
                "reports": reports,
                "session_user": sess,
            },
        )
    except Exception:
        try:
            count = db.query(Report).count() if Report else 0
        except Exception:
            count = 0
        return JSONResponse({"ok": True, "message": "Reports admin view is not installed yet.", "count": count})
