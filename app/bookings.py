# app/bookings.py
from datetime import datetime, date
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from .database import get_db
from .models import User, Item, Booking, FreezeDeposit
from .utils import category_label  # إن لم يوجد، أزل الاستيراد أو وفّر دالة بديلة

import json
from typing import List
from fastapi import UploadFile, File

# --- Cloudinary (لو عندك إعداد مسبق يكفي الاستيراد) ---
try:
    import cloudinary
    import cloudinary.uploader
except Exception:
    cloudinary = None

router = APIRouter(tags=["bookings"])

# ---------------------------------------------------
# Helpers: جدول المراجعات + إدراج
# ---------------------------------------------------

def _upload_images_to_cloudinary(files: List[UploadFile]) -> List[str]:
    """
    يرفع حتى 6 صور ويعيد قائمة روابط secure_url. يتجاهل الملفات غير الصورية.
    """
    urls = []
    if not files:
        return urls
    if cloudinary is None:
        # لو Cloudinary غير متوفر، نرجّع قائمة فاضية (أو ارفع محليًا لو تحب)
        return urls
    for f in files[:6]:
        try:
            ct = (f.content_type or "").lower()
            if not ct.startswith("image/"):
                continue
            up = cloudinary.uploader.upload(f.file, folder="sevor/booking_photos", resource_type="image")
            url = up.get("secure_url") or up.get("url")
            if url:
                urls.append(url)
        except Exception:
            # تجاهل أي فشل في ملف واحد واستمر
            continue
    return urls


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
    # فهرس يمنع تكرار تقييم المالك لنفس الحجز
    db.execute(text("""
      CREATE UNIQUE INDEX IF NOT EXISTS reviews_unique_owner_once
      ON reviews(booking_id, role, reviewer_id)
    """))

def _insert_review(db: Session, **kw):
    keys = ",".join(kw.keys())
    vals = ",".join([f":{k}" for k in kw.keys()])
    db.execute(text(f"INSERT INTO reviews({keys}) VALUES({vals})"), kw)

def _get_owner_review(db: Session, booking_id: int, owner_id: int):
    """يرجع تقييم المالك (إن وجد) لهذا الحجز كقاموس بسيط."""
    _ensure_reviews_table(db)
    row = db.execute(
        text("""
          SELECT id, rating AS stars, comment, created_at
          FROM reviews
          WHERE booking_id = :bid
            AND role = 'owner_to_user'
            AND reviewer_id = :oid
          LIMIT 1
        """),
        {"bid": booking_id, "oid": owner_id}
    ).mappings().first()
    return dict(row) if row else None

# ---------------------------------------------------
# احضار المستخدم من السيشن
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

    # 🔒 جلب تقييم المالك إن وُجد لنعطّل النموذج في القالب
    owner_prev_review = _get_owner_review(db, b.id, b.owner_id) if is_owner else None
    owner_already_rated = bool(owner_prev_review)

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
            "owner_already_rated": owner_already_rated,
            "owner_prev_review": owner_prev_review,
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
# (2) اختيار الدفع
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
    """
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    ensure_booking_side(user, b, "renter")

    if b.status not in ("accepted",):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    b.payment_method = "online"
    b.rent_amount = max(0, int(rent_amount or 0))
    b.hold_deposit_amount = max(0, int(deposit_amount or 0))

    b.online_status = "paid"
    b.deposit_status = "held" if b.hold_deposit_amount > 0 else "none"
    b.status = "paid"
    b.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

# ---------------------------------------------------
# (3) تأكيد الاستلام
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

    if b.payment_method == "online":
        b.owner_payout_amount = b.rent_amount or 0
        b.rent_released_at = datetime.utcnow()
        b.online_status = "captured"

    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

# ---------------------------------------------------
# (4) تعليم الإرجاع (ثم توجيه صفحة التقييم للمستأجر)
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
        return RedirectResponse(url=f"/bookings/{{b.id}}", status_code=303)

    b.status = "returned"
    b.returned_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/reviews/renter/{b.id}", status_code=303)

# ---------------------------------------------------
# (5) تأكيد المالك للإرجاع + مصير الوديعة
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
            b.deposit_charged_amount = 0
            b.deposit_status = "refunded"
        else:
            amt = max(0, int(charge_amount or 0))
            held = b.hold_deposit_amount or 0
            if amt >= held:
                b.deposit_charged_amount = held
                b.deposit_status = "claimed"
            else:
                b.deposit_charged_amount = amt
                b.deposit_status = "partially_refunded"
    else:
        b.deposit_charged_amount = 0
        b.deposit_status = "none" if (b.hold_deposit_amount or 0) == 0 else (b.deposit_status or "released")

    b.return_confirmed_by_owner_at = now
    b.status = "closed"
    b.updated_at = now
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

# ---------------------------------------------------
# قائمة الحجوزات
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
# مراجعة المستأجر للعنصر
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
    if not b:
        raise HTTPException(status_code=404)
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

    if b.status == "picked_up":
        b.status = "returned"
        b.returned_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/bookings/{b.id}?r_reviewed=1", status_code=303)

# ---------------------------------------------------
# مراجعة المالك للمستأجر (مرة واحدة فقط)
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
    if not b:
        raise HTTPException(status_code=404)
    ensure_booking_side(user, b, "owner")
    if b.status not in ("returned", "in_review", "closed"):
        return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

    _ensure_reviews_table(db)

    # ✅ امنع التكرار: إن كان هناك تقييم سابق لنفس المالك والحجز، لا نُدرج جديدًا
    prev = _get_owner_review(db, b.id, user.id)
    if prev:
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


@router.post("/bookings/{booking_id}/upload-photos")
async def booking_upload_photos_and_advance(
    booking_id: int,
    request: Request,
    side: Literal["pickup", "return"] = Form(...),   # "pickup" عند الاستلام، "return" عند الإرجاع
    files: List[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    زر واحد:
      - يفتح الكاميرا من الواجهة (input capture) لالتقاط حتى 6 صور.
      - يرفع الصور إلى Cloudinary.
      - يحدّث حالة الحجز ويتقدّم تلقائيًا للخطوة التالية.
    الرد بصيغة JSON يحوي next_url لتوجيه الواجهة.
    """
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    ensure_booking_side(user, b, "renter")

    # تحقّق الحالة المناسبة حسب المرحلة
    if side == "pickup" and b.status not in ("paid",):
        return {"ok": False, "reason": "bad_state", "next_url": f"/bookings/{b.id}"}
    if side == "return" and b.status not in ("picked_up",):
        return {"ok": False, "reason": "bad_state", "next_url": f"/bookings/{b.id}"}

    # ارفع الصور
    urls = _upload_images_to_cloudinary(files)

    # خزّن الروابط في الحجز
    if side == "pickup":
        exists = []
        try:
            exists = json.loads(b.pickup_photos_json or "[]")
        except Exception:
            exists = []
        exists.extend(urls)
        b.pickup_photos_json = json.dumps(exists[:6], ensure_ascii=False)

        # نفس منطق booking_picked_up القديم
        b.status = "picked_up"
        b.picked_up_at = datetime.utcnow()
        if b.payment_method == "online":
            b.owner_payout_amount = b.rent_amount or 0
            b.rent_released_at = datetime.utcnow()
            b.online_status = "captured"

        db.commit()
        return {"ok": True, "count": len(urls), "next_url": f"/bookings/{b.id}"}

    else:  # side == "return"
        exists = []
        try:
            exists = json.loads(b.return_photos_json or "[]")
        except Exception:
            exists = []
        exists.extend(urls)
        b.return_photos_json = json.dumps(exists[:6], ensure_ascii=False)

        # نفس منطق mark-returned القديم
        b.status = "returned"
        b.returned_at = datetime.utcnow()
        db.commit()
        return {"ok": True, "count": len(urls), "next_url": f"/reviews/renter/{b.id}"}
