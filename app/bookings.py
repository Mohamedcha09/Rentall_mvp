# app/bookings.py
from datetime import datetime, date
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Item, Booking, FreezeDeposit
from .utils import category_label  # إن لم يوجد، أزل الاستيراد أو وفّر دالة بديلة
from sqlalchemy import text

router = APIRouter(tags=["bookings"])

# ---------------------------------------------------
# Helpers: التقييمات (جدول + إدخال + قراءات صغيرة)
# ---------------------------------------------------
def _ensure_reviews_table(db: Session):
    sql = """
    CREATE TABLE IF NOT EXISTS reviews(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      booking_id INTEGER NOT NULL,
      item_id INTEGER,
      reviewer_id INTEGER NOT NULL,
      reviewee_user_id INTEGER,
      role TEXT NOT NULL,              -- renter_to_item | owner_to_user
      rating INTEGER NOT NULL,
      comment TEXT,
      created_at TEXT NOT NULL
    );
    """
    db.execute(text(sql))

def _insert_review(db: Session, **kw):
    keys = ",".join(kw.keys())
    vals = ",".join([f":{k}" for k in kw.keys()])
    db.execute(text(f"INSERT INTO reviews({keys}) VALUES({vals})"), kw)

# helpers قراءة سريعة
def _row_or_none(db: Session, sql: str, **p):
    r = db.execute(text(sql), p).fetchone()
    return dict(r._mapping) if r else None

def _scalar_or_zero(db: Session, sql: str, **p) -> int:
    r = db.execute(text(sql), p).scalar()
    return int(r or 0)

# ---------------------------------------------------
# Helper: احضار المستخدم من السيشن (يرجع None إن لم يسجّل)
# ---------------------------------------------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    if not uid:
        return None
    return db.get(User, uid)

def ensure_logged_in(user: Optional[User]):
    if not user:
        raise HTTPException(status_code=401, detail="not logged in")

def ensure_booking_side(u: User, b: Booking, as_role: Literal["owner","renter","any"]="any"):
    ok = (u.id == b.owner_id) or (u.id == b.renter_id)
    if not ok:
        raise HTTPException(status_code=403, detail="not your booking")
    if as_role == "owner" and u.id != b.owner_id:
        raise HTTPException(status_code=403, detail="owner action only")
    if as_role == "renter" and u.id != b.renter_id:
        raise HTTPException(status_code=403, detail="renter action only")

# ---------------------------------------------------
# صفحة “العملية الواحدة” لحجز واحد
# ---------------------------------------------------
@router.get("/bookings/{booking_id}")
def booking_flow_page(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")

    ensure_booking_side(user, b, "any")

    it = db.get(Item, b.item_id)
    is_owner = (user.id == b.owner_id)
    is_renter = (user.id == b.renter_id)

    # تجهيز نصوص مساعدة
    item_title = it.title if it else f"#{b.item_id}"
    owner_is_you = is_owner
    renter_is_you = is_renter

    # ===== معلومات التقييم: هل سبق أن قيّم المالك هذا المستأجر في هذا الحجز؟ + ملخص تقييمه كمستأجر
    owner_already_rated = False
    owner_prev_review = None
    renter_reviews_avg = 0.0
    renter_reviews_count = 0

    try:
        _ensure_reviews_table(db)

        if is_owner:
            owner_prev_review = _row_or_none(
                db,
                """
                SELECT id, rating AS stars, comment, created_at
                FROM reviews
                WHERE booking_id=:bid AND reviewer_id=:rid
                      AND reviewee_user_id=:uid AND role='owner_to_user'
                LIMIT 1
                """,
                bid=b.id, rid=user.id, uid=b.renter_id
            )
            owner_already_rated = bool(owner_prev_review)

        if b.renter_id:
            renter_reviews_avg = db.execute(
                text("SELECT ROUND(AVG(rating),2) FROM reviews WHERE role='owner_to_user' AND reviewee_user_id=:u"),
                {"u": b.renter_id}
            ).scalar() or 0.0
            renter_reviews_count = _scalar_or_zero(
                db,
                "SELECT COUNT(*) FROM reviews WHERE role='owner_to_user' AND reviewee_user_id=:u",
                u=b.renter_id
            )
    except Exception:
        # لا تكسر الصفحة لو الجدول غير موجود أو قاعدة نوع مختلف
        owner_already_rated = False
        owner_prev_review = None
        renter_reviews_avg = 0.0
        renter_reviews_count = 0

    # تمرير كل شيء للقالب
    return request.app.templates.TemplateResponse(
        "booking_flow.html",
        {
            "request": request,
            "title": f"الحجز #{b.id}",
            "session_user": request.session.get("user"),
            "booking": b,
            "item": it,
            "item_title": item_title,
            "is_owner": is_owner,
            "is_renter": is_renter,
            # إضافات التقييم:
            "owner_already_rated": owner_already_rated,
            "owner_prev_review": owner_prev_review,
            "renter_reviews_avg": renter_reviews_avg,
            "renter_reviews_count": renter_reviews_count,
            "category_label": category_label if "category_label" in globals() else (lambda c: c),
        },
    )

# ---------------------------------------------------
# (1) المالك يوافق أو يرفض
# ---------------------------------------------------
@router.post("/bookings/{booking_id}/accept")
def booking_accept(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    ensure_booking_side(user, b, "owner")
    if b.status not in ("requested",):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    b.status = "accepted"
    b.accepted_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

@router.post("/bookings/{booking_id}/reject")
def booking_reject(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    ensure_booking_side(user, b, "owner")
    if b.status not in ("requested", "accepted"):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    b.status = "rejected"
    b.rejected_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

# ---------------------------------------------------
# (2) المستأجر يختار طريقة الدفع
#     - كاش: نعدّها “مدفوعة” بدون ديبو
#     - أونلاين (Placeholder): نضع قيم rent/deposit ونعلّمها “paid”
# ---------------------------------------------------
@router.post("/bookings/{booking_id}/pay-cash")
def booking_pay_cash(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")

    ensure_booking_side(user, b, "renter")
    if b.status not in ("accepted",):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    b.payment_method = "cash"
    b.online_status = None
    b.hold_deposit_amount = 0
    b.deposit_status = "none"

    # علامة “paid” هنا تعني أنه اختار الكاش وتم الاتفاق، لكن التحويل ليس عبر المنصة
    b.status = "paid"
    b.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

@router.post("/bookings/{booking_id}/pay-online")
def booking_pay_online_placeholder(
    booking_id: int,
    request: Request,
    rent_amount: int = Form(...),
    deposit_amount: int = Form(0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    Placeholder: لا يوجد Stripe فعلي.
    - نخزّن rent_amount و deposit_amount
    - نعلّم online_status='paid' و status='paid'
    - عند 'picked_up' سنحوّل rent للمالك (نحط وقت release فقط كتسجيل)
    - الديبو يبقى 'held' حتى الإرجاع.
    """
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    ensure_booking_side(user, b, "renter")

    if b.status not in ("accepted",):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    # حفظ القيم
    b.payment_method = "online"
    b.rent_amount = max(0, int(rent_amount or 0))
    b.hold_deposit_amount = max(0, int(deposit_amount or 0))

    b.online_status = "paid"      # في Stripe الحقيقي تنتظر webhook
    b.deposit_status = "held" if b.hold_deposit_amount > 0 else "none"
    b.status = "paid"
    b.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

# ---------------------------------------------------
# (3) المستأجر يؤكد “تم استلام الغرض” (تحويل مبلغ الإيجار للمالك)
# ---------------------------------------------------
@router.post("/bookings/{booking_id}/picked-up")
def booking_picked_up(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    ensure_booking_side(user, b, "renter")

    if b.status not in ("paid",):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    b.status = "picked_up"
    b.picked_up_at = datetime.utcnow()

    # في الدفع الأونلاين: لحظة الاستلام نعتبر تحويل الإيجار للمالك (release)
    if b.payment_method == "online":
        b.owner_payout_amount = b.rent_amount or 0
        b.rent_released_at = datetime.utcnow()
        b.online_status = "captured"  # مجرد تمييز placeholder

    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

# ---------------------------------------------------
# (4) المستأجر يضغط “تم إرجاع الغرض”
# ---------------------------------------------------
@router.post("/bookings/{booking_id}/mark-returned")
def booking_mark_returned(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    ensure_booking_side(user, b, "renter")

    if b.status not in ("picked_up",):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    b.status = "returned"
    b.returned_at = datetime.utcnow()
    db.commit()
    # ⬅️ بعد التعليم، اذهب مباشرة لصفحة التقييم المستقلة
    return RedirectResponse(url=f"/reviews/renter/{b.id}", status_code=303)

# ---------------------------------------------------
# (5) المالك يؤكد الإرجاع ويقرر مصير الديبو
# ---------------------------------------------------
@router.post("/bookings/{booking_id}/owner-confirm-return")
def owner_confirm_return(
    booking_id: int,
    request: Request,
    action: Literal["ok", "charge"] = Form(...),
    charge_amount: int = Form(0),
    owner_note: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    ensure_booking_side(user, b, "owner")

    if b.status not in ("returned", "picked_up"):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    b.owner_return_note = (owner_note or "").strip()
    now = datetime.utcnow()

    if b.payment_method == "online" and (b.hold_deposit_amount or 0) > 0:
        if action == "ok":
            # إرجاع الديبو بالكامل
            b.deposit_charged_amount = 0
            b.deposit_status = "refunded"
            # في Stripe الحقيقي: تنفيذ refund/void
        else:
            amt = max(0, int(charge_amount or 0))
            held = b.hold_deposit_amount or 0
            if amt >= held:
                # اقتطاع كامل الديبو
                b.deposit_charged_amount = held
                b.deposit_status = "claimed"
            else:
                # اقتطاع جزئي
                b.deposit_charged_amount = amt
                b.deposit_status = "partially_refunded"
            # Stripe الحقيقي: capture جزئي/كامل لباقي الديبو
    else:
        # كاش أو لا يوجد ديبو
        b.deposit_charged_amount = 0
        b.deposit_status = "none" if (b.hold_deposit_amount or 0) == 0 else (b.deposit_status or "released")

    b.return_confirmed_by_owner_at = now
    b.status = "closed"
    b.updated_at = now
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

# ---------------------------------------------------
# قائمة الحجوزات (مختصر للمالك/المستأجر)
# ---------------------------------------------------
@router.get("/bookings")
def bookings_index(
    request: Request,
    view: Literal["owner", "renter"] = "renter",
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    q = db.query(Booking)
    if view == "owner":
        q = q.filter(Booking.owner_id == user.id)
    else:
        q = q.filter(Booking.renter_id == user.id)
    q = q.order_by(Booking.created_at.desc())
    bookings = q.all()

    return request.app.templates.TemplateResponse(
        "bookings_index.html",
        {
            "request": request,
            "title": "حجوزاتي" if view == "renter" else "حجوزات على ممتلكاتي",
            "session_user": request.session.get("user"),
            "bookings": bookings,
            "view": view,
        },
    )

# ---------------------------------------------------
# تقييم المستأجر للعنصر (بعد الإرجاع)
# ---------------------------------------------------
@router.post("/reviews/renter/{booking_id}")
def renter_review_and_return(
    booking_id: int,
    request: Request,
    rating: int = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b: raise HTTPException(status_code=404)
    ensure_booking_side(user, b, "renter")
    if b.status not in ("picked_up", "returned"):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    _ensure_reviews_table(db)
    _insert_review(
        db,
        booking_id=b.id,
        item_id=b.item_id,
        reviewer_id=user.id,
        reviewee_user_id=None,
        role="renter_to_item",
        rating=max(1, min(5, int(rating))),
        comment=(comment or "").strip(),
        created_at=datetime.utcnow().isoformat()
    )

    # علّم الإرجاع إن لم يكن معلّمًا
    if b.status == "picked_up":
        b.status = "returned"
        b.returned_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}?r_reviewed=1", status_code=303)

# ---------------------------------------------------
# تقييم المالك للمستأجر — مرة واحدة فقط لكل حجز
# ---------------------------------------------------
@router.post("/reviews/owner/{booking_id}")
def owner_review_renter(
    booking_id: int,
    request: Request,
    rating: int = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b: raise HTTPException(status_code=404)
    ensure_booking_side(user, b, "owner")
    if b.status not in ("returned", "in_review", "closed"):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    _ensure_reviews_table(db)

    # منع التقييم المكرر لنفس الحجز من نفس المالك لنفس المستخدم
    exists = _scalar_or_zero(
        db,
        """
        SELECT COUNT(*) FROM reviews
        WHERE booking_id=:bid AND reviewer_id=:rid
              AND reviewee_user_id=:uid AND role='owner_to_user'
        """,
        bid=b.id, rid=user.id, uid=b.renter_id
    )
    if exists:
        return RedirectResponse(url=f"/bookings/{b.id}?o_reviewed=1", status_code=303)

    _insert_review(
        db,
        booking_id=b.id,
        item_id=None,
        reviewer_id=user.id,
        reviewee_user_id=b.renter_id,
        role="owner_to_user",
        rating=max(1, min(5, int(rating))),
        comment=(comment or "").strip(),
        created_at=datetime.utcnow().isoformat()
    )
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}?o_reviewed=1", status_code=303)
