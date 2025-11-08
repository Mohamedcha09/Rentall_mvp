# app/reports.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi.responses import RedirectResponse

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db, engine
from .models import User, Item

# =========================
# Optional imports to keep runtime safe if tables/services are unavailable
# =========================
try:
    from .models import Report, ReportActionLog  # added in models.py
except Exception:  # pragma: no cover
    Report = None
    ReportActionLog = None

try:
    from .notifications_api import push_notification  # internal notifications
except Exception:  # pragma: no cover
    def push_notification(db: Session, user_id: int, title: str, body: str, link_url: str = "/", kind: str = "info"):
        return None

try:
    from .email_service import send_email  # email (optional)
except Exception:  # pragma: no cover
    def send_email(*args, **kwargs):
        return None


router = APIRouter()
BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")


# =====================================================
# Auto hot-fix to add missing columns to the reports table (Postgres)
# =====================================================
def _ensure_reports_columns():
    """
    If you are on Postgres and certain columns are missing, add them safely.
    """
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

# Run the fix once on module load
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
    if not (str(sess.get("role","")).lower()=="admin" or bool(sess.get("is_mod"))):
        raise HTTPException(status_code=403, detail="forbidden")
    return sess


def _get_item_owner_id(db: Session, item_id: int) -> Optional[int]:
    it = db.query(Item).filter(Item.id == item_id).first()
    return it.owner_id if it else None


def _set_item_state(db: Session, item_id: int, *, state: str):
    """
    Change the item's state compatibly:
    - If there is a 'status' column: use active/suspended/deleted
    - Otherwise use is_active = yes/no
    """
    it = db.query(Item).get(item_id)
    if not it:
        raise HTTPException(status_code=404, detail="item-not-found")

    # Prefer 'status' column if present
    if hasattr(it, "status"):
        if state == "active":
            it.status = "active"
        elif state == "suspended":
            it.status = "suspended"
        elif state == "deleted":
            it.status = "deleted"
    else:
        # Backward compatibility with old schema
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
    """Notify the owner + all admins and mods when a report is created."""
    label = f"Report on listing #{item_id}"
    if image_index is not None:
        label = f"Report on image #{image_index} of listing #{item_id}"

    body = f"Reporter: {reporter_name}\nReason: {reason}"

    owner_link = f"/items/{item_id}"   # owner → opens their listing
    mod_link   = "/admin/reports"      # admin/mod → reports page

    # 1) Owner
    if owner_id:
        try:
            push_notification(db, owner_id, "🚩 " + label, body, owner_link, "report")
        except Exception:
            pass

    # 2) All admins + all mods
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

    # (Optional) Email admins only
    try:
        admins = db.query(User).filter(User.role == "admin").all()
        for a in admins:
            subj = "🚩 New report"
            html = f"""
              <div style="direction:rtl;text-align:right;font-family:Tahoma,Arial,sans-serif;line-height:1.8">
                <h3>🚩 New Report</h3>
                <p><b>Reporter:</b> {reporter_name}</p>
                <p><b>Reason:</b> {reason}</p>
                <p><a href="{BASE_URL}/admin/reports" target="_blank">Open reports dashboard</a></p>
              </div>
            """
            send_email(a.email, subj, html, text_body=f"New report — {label}\n{body}\n{BASE_URL}/admin/reports")
    except Exception:
        pass


def _notify_owner_on_moderation(db: Session, item_id: int, action: str, reason: str = ""):
    """
    Notify the owner when their listing is suspended or deleted.
    action: suspend_item | delete_item | remove_item (alias)
    """
    owner_id = _get_item_owner_id(db, item_id)
    if not owner_id:
        return

    # Normalize action name
    if action == "remove_item":
        action = "delete_item"

    if action == "suspend_item":
        title = "⏸️ Your listing was suspended"
        body  = f"Your listing #{item_id} was suspended due to a report (reason: {reason})."
    elif action == "delete_item":
        title = "🗑️ Your listing was removed"
        body  = f"Your listing #{item_id} was removed after review (reason: {reason})."
    else:
        return

    link = f"/items/{item_id}"
    try:
        push_notification(db, owner_id, title, body, link, kind="moderation")
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
    Build a Report object while accounting for schema variations.
    """
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
# API: create a report (main endpoint)
# =========================
@router.post("/reports")
async def create_report(
    request: Request,
    db: Session = Depends(get_db),

    # Support both Form and JSON
    item_id: int = Form(None),
    reason: str = Form(None),
    note: str | None = Form(None),
    image_index: int | None = Form(None),
):
    """
    Creates a report on a listing/image. Accepts Form or JSON.
    """
    u = _require_login(request)

    # Allow JSON payload (mobile/SPA)
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

    # Verify item exists and get owner
    owner_id = _get_item_owner_id(db, item_id)
    if not owner_id:
        raise HTTPException(status_code=404, detail="item-not-found")

    # Create the report
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

    # Log the initial action "submitted"
    _log_action(db, getattr(report, "id", 0), int(u["id"]), "submitted", note)

    # Notify owner + admins/mods
    try:
        reporter_name = f"{u.get('first_name','').strip()} {u.get('last_name','').strip()}".strip() or f"User#{u['id']}"
        _notify_owner_and_moderators(db, owner_id, reporter_name, int(item_id), str(reason), image_index)
    except Exception:
        pass

    return JSONResponse(
        {
            "ok": True,
            "message": "Report submitted, thank you for your contribution.",
            "report_id": getattr(report, "id", None),
            "status": getattr(report, "status", "pending"),
        },
        status_code=201,
    )


# =========================
# (Legacy compatibility) /reports/new → reuse the same logic
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
# Reports management page
# =========================
@router.get("/admin/reports")
def admin_reports_page(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    # Strict DB check (don’t rely only on session flags)
    me = db.query(User).filter(User.id == int(sess.get("id", 0))).first()
    is_admin = (getattr(me, "role", "") or "").lower() == "admin"
    is_mod   = bool(getattr(me, "is_mod", False))

    if not (is_admin or is_mod):
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
    reports = (
        db.query(Report)
        .order_by(Report.created_at.desc())
        .limit(200)
        .all()
    )

    return request.app.templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "title": "Reports",
            "pending": pending,
            "processed": processed,
            "reports": reports,
            "session_user": sess,
        }
    )


# =========================
# Decision routes (suspend/delete/restore/close/reopen)
# =========================
@router.post("/admin/reports/{report_id}/decision")
def reports_decision(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
    action: str = Form(...),           # suspend_item | remove_item | delete_item | restore_item | close_only | reject_report
    note: str = Form(""),
):
    sess = _require_admin_or_mod(request)

    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="report-not-found")

    item_id = getattr(r, "item_id", None)

    # Normalize alias
    normalized = action
    if normalized == "remove_item":
        normalized = "delete_item"

    # Change item state according to decision
    if normalized == "suspend_item" and item_id:
        _set_item_state(db, int(item_id), state="suspended")
        _notify_owner_on_moderation(db, int(item_id), "suspend_item", getattr(r, "reason", "") or "")
        if hasattr(r, "tag"): r.tag = "suspended"
    elif normalized == "delete_item" and item_id:
        _set_item_state(db, int(item_id), state="deleted")
        _notify_owner_on_moderation(db, int(item_id), "delete_item", getattr(r, "reason", "") or "")
        if hasattr(r, "tag"): r.tag = "removed"
    elif normalized == "restore_item" and item_id:
        _set_item_state(db, int(item_id), state="active")
        if hasattr(r, "tag"): r.tag = "restored"
    elif normalized == "close_only":
        if hasattr(r, "tag"): r.tag = "closed"
    elif normalized == "reject_report":
        if hasattr(r, "tag"): r.tag = "rejected"
    else:
        raise HTTPException(status_code=400, detail="bad-action")

    # Update report
    if hasattr(r, "status"):
        # If we rejected the report → close it, and likewise for the other cases
        r.status = "closed"
    if note and hasattr(r, "note"):
        r.note = (note or "").strip()
    if hasattr(r, "updated_at"):
        r.updated_at = datetime.utcnow()

    db.add(r)
    db.commit()
    _log_action(db, getattr(r, "id", 0), int(sess["id"]), f"decision:{normalized}", note)

    # Back to the reports dashboard
    return RedirectResponse(url="/admin/reports", status_code=303)


@router.post("/admin/reports/{report_id}/reopen")
def reports_reopen(report_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin_or_mod(request)
    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="report-not-found")
    if hasattr(r, "status"):
        r.status = "pending"
    if hasattr(r, "tag"):
        r.tag = "reopened"
    if hasattr(r, "updated_at"):
        r.updated_at = datetime.utcnow()
    db.add(r)
    db.commit()
    _log_action(db, getattr(r, "id", 0), request.session["user"]["id"], "reopen", None)
    return RedirectResponse(url="/admin/reports", status_code=303)


# =========================
# Quick diagnostic route: /reports/_diag
# =========================
@router.get("/reports/_diag")
def reports_diag(request: Request, db: Session = Depends(get_db)):
    """
    Useful for diagnostics: checks table/columns existence and attempts an example insert.
    Enable DEBUG_REPORTS=1 to allow the example insert.
    """
    info: Dict[str, Any] = {"ok": True}

    # Is the user logged in?
    info["logged_in"] = bool(request.session.get("user"))

    # Does the 'reports' table exist?
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

    # Try inserting a sample record (optional)
    do_insert = os.getenv("DEBUG_REPORTS", "0") == "1"
    if do_insert and Report is not None and info.get("table_exists"):
        try:
            u = request.session.get("user") or {"id": 1}
            r = _build_report_instance(
                reporter_id=int(u["id"]),
                item_id=1,
                reason="diag-test",
                note=None,
                image_index=None,
                payload=None,
            )
            db.add(r)
            db.commit()
            info["insert_test"] = "ok"
        except Exception as e:
            db.rollback()
            info["insert_error"] = str(e)

    return JSONResponse(info)

    # =========================
# Single report details page
# =========================
@router.get("/admin/reports/{report_id}")
def admin_report_detail_page(report_id: int, request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess or not (str(sess.get("role","")).lower()=="admin" or bool(sess.get("is_mod"))):
        return RedirectResponse(url="/login", status_code=303)

    r = db.query(Report).get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="report-not-found")

    status_val = (getattr(r, "status", None) or "").lower()
    is_pending = status_val in ("", "pending", "open")

    item_id = getattr(r, "item_id", None)
    owner_id = _get_item_owner_id(db, int(item_id)) if item_id else None

    return request.app.templates.TemplateResponse(
        "report_detail.html",
        {
            "request": request,
            "title": f"Report #{getattr(r,'id', '')}",
            "r": r,
            "item_id": item_id,
            "owner_id": owner_id,
            "is_pending": is_pending,
            "session_user": sess,  # ✅ important
        }
    )


@router.get("/mod/reports")
def legacy_mod_reports_redirect():
    # Redirect any old link /mod/reports to the new path
    return RedirectResponse(url="/admin/reports", status_code=308)
