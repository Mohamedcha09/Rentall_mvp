# app/reports.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db, engine
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


# =====================================================
# هوت-فيكس تلقائي لإضافة أعمدة ناقصة في جدول reports (Postgres)
# =====================================================
def _ensure_reports_columns():
    """لو تعمل على Postgres وكانت أعمدة معينة غير موجودة نضيفها بأمان."""
    try:
        backend = engine.url.get_backend_name()
    except Exception:
        backend = getattr(getattr(engine, "dialect", None), "name", "")

    if str(backend).startswith("postgres"):
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN IF NOT EXISTS tag VARCHAR(24);")
                conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;")
                conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending';")
                conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN IF NOT EXISTS note TEXT;")
                conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN IF NOT EXISTS image_index INT;")
        except Exception as e:
            print("[WARN] ensure reports columns failed:", e)

_ensure_reports_columns()


# =========================
# Helpers
# =========================
def _require_login(request: Request) -> Dict[str, Any]:
    u = request.session.get("user")
    if not u:
        raise HTTPException(status_code=401, detail="login-required")
    return u


def _require_admin_or_mod(request: Request) -> dict:
    sess = request.session.get("user") or {}
    if not (str(sess.get("role","")).lower() == "admin" or bool(sess.get("is_mod"))):
        raise HTTPException(status_code=403, detail="forbidden")
    return sess


def _get_item_owner_id(db: Session, item_id: int) -> Optional[int]:
    it = db.query(Item).filter(Item.id == item_id).first()
    return it.owner_id if it else None


def _set_item_state(db: Session, item_id: int, *, state: str):
    """
    يغير حالة العنصر بشكل متوافق:
    - لو يوجد عمود status: نستخدم active/suspended/deleted
    - وإلا نستخدم is_active = yes/no
    """
    it = db.query(Item).get(item_id)
    if not it:
        raise HTTPException(status_code=404, detail="item-not-found")

    if hasattr(it, "status"):
        if state == "active":
            it.status = "active"
        elif state == "suspended":
            it.status = "suspended"
        elif state == "deleted":
            it.status = "deleted"
    else:
        if state in ("suspended", "deleted"):
            setattr(it, "is_active", "no")
        elif state == "active":
            setattr(it, "is_active", "yes")

    db.add(it)
    db.commit()
    return it


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

    owner_link = f"/items/{item_id}"   # المالك → يفتح منشوره
    mod_link   = "/admin/reports"      # الأدمن/المود → صفحة البلاغات

    # المالك
    if owner_id:
        try:
            push_notification(db, owner_id, "🚩 " + label, body, owner_link, "report")
        except Exception:
            pass

    # الأدمن/المود
    try:
        moderators = (
            db.query(User)
            .filter((User.role == "admin") | (getattr(User, "is_mod", False) == True))  # noqa: E712
            .all()
        )
        for m in moderators:
            try:
                push_notification(db, m.id, "🚩 " + label, body, mod_link, "report")
            except Exception:
                pass
    except Exception:
        pass

    # (اختياري) بريد للأدمن
    try:
        admins = db.query(User).filter(User.role == "admin").all()
        for a in admins:
            subj = "🚩 بلاغ جديد"
            html = f"""
              <div style="direction:rtl;text-align:right;font-family:Tahoma,Arial,sans-serif;line-height:1.8">
                <h3>🚩 بلاغ جديد</h3>
                <p><b>المبلِّغ:</b> {reporter_name}</p>
                <p><b>السبب:</b> {reason}</p>
                <p><a href="{BASE_URL}/admin/reports" target="_blank">فتح لوحة البلاغات</a></p>
              </div>
            """
            send_email(a.email, subj, html, text_body=f"بلاغ جديد — {label}\n{body}\n{BASE_URL}/admin/reports")
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
    """إنشاء كائن Report مع مراعاة اختلاف السكيمة."""
    if Report is None:
        raise HTTPException(status_code=500, detail="Report model is missing")

    data: Dict[str, Any] = {
        "reporter_id": reporter_id,
        "reason": reason[:120] if reason else "",
        "status": "pending",
        "created_at": datetime.utcnow(),
    }

    if hasattr(Report, "item_id"):
        data["item_id"] = item_id
    if note is not None and hasattr(Report, "note"):
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
    if hasattr(Report, "updated_at"):
        data["updated_at"] = datetime.utcnow()

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
# إنشاء بلاغ
# =========================
@router.post("/reports")
async def create_report(
    request: Request,
    db: Session = Depends(get_db),
    item_id: int = Form(None),
    reason: str = Form(None),
    note: str | None = Form(None),
    image_index: int | None = Form(None),
):
    u = _require_login(request)

    # دعم JSON
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

    owner_id = _get_item_owner_id(db, item_id)
    if not owner_id:
        raise HTTPException(status_code=404, detail="item-not-found")

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

    _log_action(db, getattr(report, "id", 0), int(u["id"]), "submitted", note)

    try:
        reporter_name = f"{u.get('first_name','').strip()} {u.get('last_name','').strip()}".strip() or f"User#{u['id']}"
        _notify_owner_and_moderators(db, owner_id, reporter_name, int(item_id), str(reason), image_index)
    except Exception:
        pass

    return JSONResponse({"ok": True, "message": "تم إرسال البلاغ، شكرًا لمساهمتك.",
                         "report_id": getattr(report, "id", None),
                         "status": getattr(report, "status", "pending")}, status_code=201)


# =========================
# (توافق قديم)
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
    return await create_report(request=request, db=db, item_id=item_id, reason=reason, note=note, image_index=image_index)


# =========================
# قائمة البلاغات
# =========================
@router.get("/admin/reports")
def admin_reports_page(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess or not (str(sess.get("role","")).lower()=="admin" or bool(sess.get("is_mod"))):
        return RedirectResponse(url="/login", status_code=303)

    pending = (
        db.query(Report)
        .filter(Report.status.in_(["open","pending"]))
        .order_by(Report.created_at.desc())
        .all()
    )
    processed = (
        db.query(Report)
        .filter(Report.status.in_(["closed","resolved","rejected"]))
        .order_by(Report.updated_at.desc().nullslast())
        .limit(200)
        .all()
    )

    return request.app.templates.TemplateResponse(
        "reports.html",
        {"request": request, "title": "البلاغات",
         "pending": pending, "processed": processed, "session_user": sess}
    )


# =========================
# صفحة تفاصيل بلاغ واحد
# =========================
@router.get("/admin/reports/{report_id}")
def admin_report_detail(report_id: int, request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess or not (str(sess.get("role","")).lower() == "admin" or bool(sess.get("is_mod"))):
        return RedirectResponse(url="/login", status_code=303)

    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="report-not-found")

    item = db.query(Item).get(getattr(r, "item_id", 0)) if getattr(r, "item_id", None) else None
    reporter = db.query(User).get(getattr(r, "reporter_id", 0)) if getattr(r, "reporter_id", None) else None

    return request.app.templates.TemplateResponse(
        "report_detail.html",
        {"request": request, "title": f"بلاغ #{r.id}",
         "r": r, "item": item, "reporter": reporter, "session_user": sess}
    )


# =========================
# قرارات (إيقاف/حذف/رفض/استرجاع/إعادة فتح)
# =========================
@router.post("/admin/reports/{report_id}/decision")
def reports_decision(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
    action: str = Form(...),           # suspend_item | delete_item | restore_item | close_only | reject_report
    note: str = Form(""),
):
    sess = _require_admin_or_mod(request)

    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="report-not-found")

    item_id = getattr(r, "item_id", None)

    if action == "suspend_item" and item_id:
        _set_item_state(db, int(item_id), state="suspended")
    elif action == "delete_item" and item_id:
        _set_item_state(db, int(item_id), state="deleted")
    elif action == "restore_item" and item_id:
        _set_item_state(db, int(item_id), state="active")
    elif action == "reject_report":
        # لا تغيير على المنشور؛ فقط نغلق البلاغ بعَلم "rejected"
        pass
    elif action == "close_only":
        pass
    else:
        raise HTTPException(status_code=400, detail="bad-action")

    # تحديث البلاغ
    if hasattr(r, "status"):
        r.status = "closed"
    if hasattr(r, "tag") and action == "reject_report":
        r.tag = "rejected"
    if note and hasattr(r, "note"):
        r.note = (note or "").strip()
    if hasattr(r, "updated_at"):
        r.updated_at = datetime.utcnow()

    db.add(r)
    db.commit()
    _log_action(db, getattr(r, "id", 0), int(sess["id"]), f"decision:{action}", note)

    return RedirectResponse(url="/admin/reports", status_code=303)


@router.post("/admin/reports/{report_id}/reopen")
def reports_reopen(report_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin_or_mod(request)
    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="report-not-found")
    if hasattr(r, "status"):
        r.status = "pending"
    if hasattr(r, "updated_at"):
        r.updated_at = datetime.utcnow()
    db.add(r)
    db.commit()
    _log_action(db, getattr(r, "id", 0), request.session["user"]["id"], "reopen", None)
    return RedirectResponse(url="/admin/reports", status_code=303)


# =========================
# تشخيص سريع
# =========================
@router.get("/reports/_diag")
def reports_diag(request: Request, db: Session = Depends(get_db)):
    info: Dict[str, Any] = {"ok": True}
    info["logged_in"] = bool(request.session.get("user"))

    try:
        with engine.begin() as conn:
            res = conn.exec_driver_sql(
                "SELECT column_name FROM information_schema.columns WHERE table_name='reports'"
            ).all()
        cols = [r[0] for r in res] if res else []
        info["table_exists"] = bool(cols)
        info["columns"] = cols
    except Exception as e:
        info["table_exists"] = False
        info["error_list_columns"] = str(e)

    do_insert = os.getenv("DEBUG_REPORTS", "0") == "1"
    if do_insert and Report is not None and info.get("table_exists"):
        try:
            u = request.session.get("user") or {"id": 1}
            r = _build_report_instance(
                reporter_id=int(u["id"]), item_id=1, reason="diag-test",
                note=None, image_index=None, payload=None,
            )
            db.add(r)
            db.commit()
            info["insert_test"] = "ok"
        except Exception as e:
            db.rollback()
            info["insert_error"] = str(e)

    return JSONResponse(info)
