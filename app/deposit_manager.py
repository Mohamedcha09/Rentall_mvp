# app/deposit_manager.py
from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, User
from .notifications_api import push_notification

router = APIRouter(tags=["deposit-manager"])

# --------------- Helpers ---------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None

def require_auth(user: Optional[User]):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

def require_manager(user: Optional[User]):
    require_auth(user)
    # نتعامل بأمان لو الخاصية غير موجودة في موديلات قديمة
    if not bool(getattr(user, "can_manage_deposits", False)):
        raise HTTPException(status_code=403, detail="Deposit manager only")

def _get_booking(db: Session, booking_id: int) -> Booking:
    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    return bk


# --------------- قائمة القضايا ---------------
@router.get("/deposit-manager")
def dm_index(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    view: Literal["pending", "in_review", "resolved"] = "pending",
):
    """
    تبويب بسيط:
      - pending   : القضايا التي تحتاج قرار (deposit_status in ['in_dispute','held']) وحالة الحجز ليست مغلقة
      - in_review : الحجز في حالة in_review (مفتوحة وتحت المراجعة)
      - resolved  : الحجز مغلق/مكتمل وفيه قرار وديعة نهائي
    """
    require_manager(user)

    q = db.query(Booking)

    if view == "pending":
        q = q.filter(
            Booking.status.in_(["returned", "in_review"]),
            Booking.deposit_status.in_(["in_dispute", "held"])
        )
        title = "Deposit Queue — Pending"
    elif view == "in_review":
        q = q.filter(Booking.status == "in_review")
        title = "Deposit Queue — In Review"
    else:
        q = q.filter(Booking.status.in_(["closed", "completed"]))
        title = "Deposit Queue — Resolved"

    rows = q.order_by(Booking.updated_at.desc().nullslast(), Booking.created_at.desc().nullslast()).all()

    # نمرر كل شيء للقالب
    return request.app.templates.TemplateResponse(
        "deposit_manager_index.html",
        {
            "request": request,
            "title": title,
            "session_user": request.session.get("user"),
            "rows": rows,
            "view": view,
        }
    )


# --------------- استلام/Claim القضية ---------------
@router.post("/deposit-manager/{booking_id}/claim")
def dm_claim(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    تعليم القضية أنها قيد المراجعة (لا نضيف أعمدة جديدة؛ فقط نضبط status=in_review)
    """
    require_manager(user)
    bk = _get_booking(db, booking_id)

    # حالات منطقية للاستلام
    if bk.deposit_status not in ["in_dispute", "held"]:
        return RedirectResponse(url="/deposit-manager?view=resolved", status_code=303)

    bk.status = "in_review"
    bk.updated_at = datetime.utcnow()
    db.commit()

    # إشعار الطرفين أن القضية دخلت قيد المراجعة
    push_notification(
        db, bk.owner_id, "قضية الوديعة قيد المراجعة",
        f"تم استلام القضية #{bk.id} من قِبل متحكّم الوديعة.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    push_notification(
        db, bk.renter_id, "قضية الوديعة قيد المراجعة",
        f"تم استلام القضية #{bk.id} من قِبل متحكّم الوديعة.",
        f"/bookings/flow/{bk.id}", "deposit"
    )

    return RedirectResponse(url="/deposit-manager?view=in_review", status_code=303)


# --------------- طلب معلومات/أدلة إضافية ---------------
@router.post("/deposit-manager/{booking_id}/need-info")
def dm_need_info(
    booking_id: int,
    target: Literal["owner", "renter"] = Form(...),
    message: str = Form("يرجى تزويدنا بمعلومات/صور إضافية لدعم موقفك."),
    request: Request = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_manager(user)
    bk = _get_booking(db, booking_id)

    # نترك الحالة in_review كما هي
    bk.updated_at = datetime.utcnow()
    db.commit()

    # نرسل إشعار للمطلوب منه
    target_user_id = bk.owner_id if target == "owner" else bk.renter_id
    push_notification(
        db, target_user_id, "طلب معلومات إضافية",
        message or "نرجو تزويدنا بتفاصيل إضافية.",
        f"/bookings/flow/{bk.id}", "deposit"
    )

    return RedirectResponse(url="/deposit-manager?view=in_review", status_code=303)


# --------------- تنفيذ القرار النهائي/الانتظار ---------------
@router.post("/deposit-manager/{booking_id}/decide")
def dm_decide(
    booking_id: int,
    # 🔗 نفس القيم المتوقّعة في routes_deposits.dm_decision
    decision: Literal["release", "withhold"] = Form(...),
    amount: int = Form(0),
    reason: str = Form(""),
    finalize: int = Form(0),  # 0/1 من الزر
    request: Request = None,
    user: Optional[User] = Depends(get_current_user),
):
    """
    لا ننفّذ المنطق هنا؛ نعيد توجيه POST بنفس الحقول إلى
    /dm/deposits/{booking_id}/decision
    ونستخدم 307 للحفاظ على طريقة POST والـbody.
    """
    require_manager(user)

    # إعادة توجيه إلى راوت التنفيذ الموحد
    # (307 = Temporary Redirect مع الحفاظ على POST)
    return RedirectResponse(
        url=f"/dm/deposits/{booking_id}/decision",
        status_code=307
    )