# app/bookings.py
from datetime import datetime, date
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from .database import get_db
from .models import User, Item, Booking, FreezeDeposit
from .utils import category_label  # If not available, remove the import or provide an alternative function

import json
from typing import List, Optional
from fastapi import UploadFile, File

# --- Cloudinary (if you already have it configured, importing is enough) ---
try:
    import cloudinary
    import cloudinary.uploader
except Exception:
    cloudinary = None

router = APIRouter(tags=["bookings"])

# ---------------------------------------------------
# Helpers: reviews table + insert
# ---------------------------------------------------
def _safe_next(next_raw: str | None, booking_id: int, fallback: str) -> str:
    nxt = (next_raw or "").strip()
    if not nxt:
        nxt = fallback
    # Prevent external links
    if not nxt.startswith("/"):
        nxt = fallback
    return nxt.replace("{id}", str(booking_id))
 

def _upload_images_to_cloudinary(files: List[UploadFile]) -> List[str]:
    """
    Upload up to 6 images and return a list of secure_url links. Non-image files are ignored.
    """
    urls = []
    if not files:
        return urls
    if cloudinary is None:
        # If Cloudinary is unavailable, return an empty list (or save locally if you prefer)
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
            # Ignore failure on a single file and continue
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
    # Index prevents the owner from rating the same booking more than once
    db.execute(text("""
      CREATE UNIQUE INDEX IF NOT EXISTS reviews_unique_owner_once
      ON reviews(booking_id, role, reviewer_id)
    """))

def _insert_review(db: Session, **kw):
    keys = ",".join(kw.keys())
    vals = ",".join([f":{k}" for k in kw.keys()])
    db.execute(text(f"INSERT INTO reviews({keys}) VALUES({vals})"), kw)

def _get_owner_review(db: Session, booking_id: int, owner_id: int):
    """Returns the owner's review (if any) for this booking as a simple dict."""
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
# Get user from session
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
# “Single flow” page for one booking
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

    # Prepare helper texts
    item_title = it.title if it else f"#{b.item_id}"

    # 🔒 Fetch owner review if present to disable the form in the template
    owner_prev_review = _get_owner_review(db, b.id, b.owner_id) if is_owner else None
    owner_already_rated = bool(owner_prev_review)

    return request.app.templates.TemplateResponse(
        "booking_flow.html",
        {
            "request": request,
            "title": f"Booking #{b.id}",
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
# (1) Owner accepts or rejects
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
# (2) Payment choice
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
    Placeholder: no real Stripe.
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
# (3) Pickup confirmation
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
# (4) Mark return (then redirect renter to review page)
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
# (5) Owner confirms return + deposit outcome
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
# Bookings list
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
        "booking_index.html",
        {
            "request": request,
            "title": "My bookings" if view == "renter" else "Bookings on my items",
            "session_user": request.session.get("user"),
            "bookings": bookings,
            "view": view,
        },
    )

# ---------------------------------------------------
# Renter review for the item
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
# Owner review of renter (only once)
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

    # ✅ Prevent duplicates: if there is an existing review by the same owner for the same booking, do not insert a new one
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
    side: Literal["pickup", "return"] = Form(...),   # "pickup" at pickup, "return" at return
    files: List[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    One button:
      - Opens the camera from the UI (input capture) to take up to 6 photos.
      - Uploads photos to Cloudinary.
      - Updates booking state and automatically advances to the next step.
    Response is JSON with next_url for UI redirection.
    """
    ensure_logged_in(user)
    b: Booking = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(status_code=404, detail="booking not found")
    ensure_booking_side(user, b, "renter")

    # Validate proper state per phase
    if side == "pickup" and b.status not in ("paid",):
        return {"ok": False, "reason": "bad_state", "next_url": f"/bookings/{b.id}"}
    if side == "return" and b.status not in ("picked_up",):
        return {"ok": False, "reason": "bad_state", "next_url": f"/bookings/{b.id}"}

    # Upload photos
    urls = _upload_images_to_cloudinary(files)

    # Store links in the booking
    if side == "pickup":
        exists = []
        try:
            exists = json.loads(b.pickup_photos_json or "[]")
        except Exception:
            exists = []
        exists.extend(urls)
        b.pickup_photos_json = json.dumps(exists[:6], ensure_ascii=False)

        # Same logic as old booking_picked_up
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

        # Same logic as old mark-returned
        b.status = "returned"
        b.returned_at = datetime.utcnow()
        db.commit()
        return {"ok": True, "count": len(urls), "next_url": f"/reviews/renter/{b.id}"}



@router.post("/bookings/{booking_id}/pickup-proof-upload")
async def pickup_proof_upload(
    booking_id: int,
    request: Request,
    files: List[UploadFile] = File(default_factory=list),
    comment: str = Form("", alias="comment"),
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

    # Upload and store first 6 photos
    urls = _upload_images_to_cloudinary(files)
    try:
        exists = json.loads(b.pickup_photos_json or "[]")
    except Exception:
        exists = []
    exists.extend(urls)
    b.pickup_photos_json = json.dumps(exists[:6], ensure_ascii=False)

    # Advance state like booking_picked_up
    b.status = "picked_up"
    b.picked_up_at = datetime.utcnow()
    if b.payment_method == "online":
        b.owner_payout_amount = b.rent_amount or 0
        b.rent_released_at = datetime.utcnow()
        b.online_status = "captured"
    db.commit()

    # Read next from query or form
    next_q = request.query_params.get("next") or (await request.form()).get("next")
    next_url = _safe_next(next_q, b.id, fallback=f"/bookings/flow/{b.id}/next")
    return RedirectResponse(url=next_url, status_code=303)


@router.post("/bookings/{booking_id}/return-proof-upload")
async def return_proof_upload(
    booking_id: int,
    request: Request,
    files: List[UploadFile] = File(default_factory=list),
    comment: str = Form("", alias="comment"),
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

    urls = _upload_images_to_cloudinary(files)
    try:
        exists = json.loads(b.return_photos_json or "[]")
    except Exception:
        exists = []
    exists.extend(urls)
    b.return_photos_json = json.dumps(exists[:6], ensure_ascii=False)

    b.status = "returned"
    b.returned_at = datetime.utcnow()
    db.commit()

    next_q = request.query_params.get("next") or (await request.form()).get("next")
    next_url = _safe_next(next_q, b.id, fallback=f"/reviews/renter/{b.id}")
    return RedirectResponse(url=next_url, status_code=303)


@router.get("/bookings/flow/{booking_id}/next")
def bookings_flow_next(
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

    # Decide where to go based on state
    if b.status in ("paid", "requested", "accepted"):
        goto = f"/bookings/{b.id}"
    elif b.status == "picked_up":
        goto = f"/reviews/renter/{b.id}"
    elif b.status in ("returned", "in_review", "closed", "completed"):
        goto = f"/bookings/{b.id}"
    else:
        goto = f"/bookings/{b.id}"
    return RedirectResponse(url=goto, status_code=303)
