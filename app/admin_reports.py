# app/admin_reports.py
from __future__ import annotations
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Report, ReportActionLog, Item

router = APIRouter(tags=["admin-reports"])

# ===== Helpers =====
def _require_admin_or_mod(request: Request) -> dict:
    sess = request.session.get("user") or {}
    role = (sess.get("role") or "").lower()
    is_mod = bool(sess.get("is_mod"))
    if role == "admin" or is_mod:
        return sess
    raise HTTPException(status_code=403, detail="Forbidden")

def _template_response(request: Request, name: str, ctx: dict):
    """
    يحاول استخدام Jinja لو متوفر، وإلا يرجع JSON fallback حتى لا تفشل النشرة.
    """
    try:
        templates = request.app.templates  # سُجِّلت في main.py
        return templates.TemplateResponse(name, ctx)
    except Exception:
        # Fallback: JSON مبسّط
        data = {
            "view": name,
            "context_keys": list(ctx.keys()),
            "reports": [
                {
                    "id": r.id,
                    "item_id": r.item_id,
                    "image_index": getattr(r, "image_index", None),
                    "image_url": getattr(r, "image_url", None),
                    "reporter_id": r.reporter_id,
                    "reason": r.reason,
                    "note": getattr(r, "note", None),
                    "tag": getattr(r, "tag", None),
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in ctx.get("reports", [])
            ],
        }
        return JSONResponse(data)

# ===== Views =====
@router.get("/admin/reports")
def admin_reports_index(
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin_or_mod(request)

    # آخر البلاغات
    reports = (
        db.query(Report)
        .order_by(Report.created_at.desc())
        .limit(200)
        .all()
    )

    # تجهيز معلومات إضافية خفيفة
    items_map = {}
    users_map = {}

    def _user(u_id: Optional[int]) -> Optional[User]:
        if not u_id:
            return None
        if u_id in users_map:
            return users_map[u_id]
        u = db.get(User, u_id)
        users_map[u_id] = u
        return u

    def _item(i_id: Optional[int]) -> Optional[Item]:
        if not i_id:
            return None
        if i_id in items_map:
            return items_map[i_id]
        it = db.get(Item, i_id)
        items_map[i_id] = it
        return it

    enriched = []
    for r in reports:
        enriched.append(
            {
                "row": r,
                "reporter": _user(r.reporter_id),
                "item": _item(r.item_id),
            }
        )

    return _template_response(
        request,
        "admin/reports.html",  # إن لم يوجد القالب → JSON fallback
        {
            "request": request,
            "title": "📸 البلاغات",
            "session_user": request.session.get("user"),
            "reports": [e["row"] for e in enriched],
            "enriched": enriched,
        },
    )

# إجراء سريع لتغيير حالة البلاغ (اختياري، بسيط)
@router.post("/admin/reports/{report_id}/set_status")
def set_report_status(
    report_id: int,
    status: str = Form(...),        # pending / in_review / resolved / rejected
    note: str = Form(""),
    request: Request = None,
    db: Session = Depends(get_db),
):
    sess = _require_admin_or_mod(request)
    actor_id = sess["id"]

    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")

    old = r.status
    r.status = status.strip().lower()
    try:
        # لو عندك col updated_at
        if hasattr(r, "updated_at"):
            r.updated_at = datetime.utcnow()
    except Exception:
        pass

    # سجّل إجراء
    log = ReportActionLog(
        report_id=r.id,
        actor_id=actor_id,
        action=f"set_status:{old}->{r.status}",
        note=(note or "").strip()[:1000],
        created_at=datetime.utcnow(),
    )
    db.add(log)
    db.commit()

    # رجّع لنفس الصفحة
    return RedirectResponse(url="/admin/reports", status_code=303)
