# app/profiles.py
from __future__ import annotations

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import os, secrets

from .database import get_db
from .models import User, Item, Rating, Document
from .utils_badges import get_user_badges

# --- Cloudinary ---
import cloudinary
import cloudinary.uploader

CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
API_KEY    = os.environ.get("CLOUDINARY_API_KEY")
API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

if CLOUD_NAME and API_KEY and API_SECRET:
    cloudinary.config(
        cloud_name=CLOUD_NAME,
        api_key=API_KEY,
        api_secret=API_SECRET,
        secure=True,
    )

# -----------------------------
# Helpers: Cloudinary Uploaders
# -----------------------------
def _ensure_cloudinary_keys() -> None:
    if not (CLOUD_NAME and API_KEY and API_SECRET):
        raise RuntimeError("Cloudinary credentials missing on server")

def _upload_avatar_cloudinary(fileobj: UploadFile, *, folder: str = "sevor/avatars") -> str:
    """
    يرفع الأفاتار إلى Cloudinary ويعيد secure_url.
    يَقبل HEIC/HEIF ويُحوّل الناتج إلى JPG ثابت لكسر مشاكل الكاش/الدعم.
    """
    if not fileobj:
        raise ValueError("no file provided")

    ctype = (fileobj.content_type or "").lower()
    if not ctype.startswith("image/"):
        raise ValueError("invalid content type")

    _ensure_cloudinary_keys()

    public_id = f"{secrets.token_hex(12)}"
    res = cloudinary.uploader.upload(
        fileobj.file,
        folder=folder,
        public_id=public_id,
        overwrite=True,
        resource_type="image",
        format="jpg",  # نحصل على مخرجات موحّدة
        transformation=[{"quality": "auto:good"}],
        invalidate=True,  # تنظيف كاش CDN إن تغيّر الملف
    )
    url = res.get("secure_url") or res.get("url")
    if not url:
        raise RuntimeError("cloudinary upload failed")
    return url

def _upload_doc_cloudinary(fileobj: UploadFile, *, folder: str = "sevor/ids") -> str:
    """
    يرفع وثيقة (صورة/ PDF) إلى Cloudinary ويعيد secure_url.
    resource_type='auto' للسماح بـ PDF.
    """
    if not fileobj:
        raise ValueError("no file provided")

    ctype = (fileobj.content_type or "").lower()
    if not (ctype.startswith("image/") or ctype == "application/pdf"):
        raise ValueError("invalid document type")

    _ensure_cloudinary_keys()

    public_id = f"{secrets.token_hex(12)}"
    res = cloudinary.uploader.upload(
        fileobj.file,
        folder=folder,
        public_id=public_id,
        overwrite=True,
        resource_type="auto",
        invalidate=True,
        transformation=[{"quality": "auto:good"}] if ctype.startswith("image/") else None,
    )
    url = res.get("secure_url") or res.get("url")
    if not url:
        raise RuntimeError("cloudinary upload failed")
    return url


router = APIRouter()

# ======================== صفحة ملفّي ========================
@router.get("/profile")
def profile(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    me: User | None = db.get(User, u["id"])
    if not me:
        return RedirectResponse(url="/login", status_code=303)

    db.refresh(me)
    # مزامنة الجلسة مع الأفاتار من القاعدة (حتى لا تظهر "1")
if me.avatar_path:
    u = request.session.get("user") or {}
    if u.get("avatar_path") != me.avatar_path:
        u["avatar_path"] = me.avatar_path
        request.session["user"] = u


    # إحصائيات العناصر
    items_count = db.query(Item).filter(Item.owner_id == me.id).count()
    items_active_count = (
        db.query(Item)
        .filter(Item.owner_id == me.id, Item.is_active == "yes")
        .count()
    )

    # التقييمات
    ratings_q = db.query(Rating).filter(Rating.rated_user_id == me.id)
    ratings_count = ratings_q.count()
    avg_stars_val = db.query(func.avg(Rating.stars)).filter(Rating.rated_user_id == me.id).scalar()
    avg_stars = round(float(avg_stars_val), 1) if avg_stars_val is not None else 0.0

    last_reviews = ratings_q.order_by(Rating.created_at.desc()).limit(5).all()
    reviews_view = []
    for r in last_reviews:
        rater = db.get(User, r.rater_id)
        reviews_view.append(
            {
                "stars": r.stars,
                "comment": r.comment or "",
                "created_at": r.created_at,
                "rater_name": f"{(rater.first_name or '').strip()} {(rater.last_name or '').strip()}".strip() if rater else "مستخدم",
            }
        )

    joined_at = me.created_at or datetime.utcnow()
    my_badges = get_user_badges(me, db)
    payouts_enabled = bool(getattr(me, "payouts_enabled", False))

    return request.app.templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "title": "صفحتي",
            "session_user": u,
            "user": me,
            "badges": my_badges,
            "payouts_enabled": payouts_enabled,
            "items_count": items_count,
            "items_active_count": items_active_count,
            "avg_stars": avg_stars,
            "ratings_count": ratings_count,
            "reviews": reviews_view,
            "joined_at": joined_at,
        },
    )


# ======================== صفحة عامة لمستخدم ========================
@router.get("/u/{user_id}")
def public_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    user: User | None = db.get(User, user_id)
    if not user:
        return RedirectResponse(url="/", status_code=303)

    items = (
        db.query(Item)
        .filter(Item.owner_id == user.id)
        .order_by(Item.created_at.desc())
        .all()
    )
    view_items = [
        {
            "id": it.id,
            "title": it.title,
            "image_path": it.image_path,
            "price_per_day": it.price_per_day,
            "category": it.category,
        }
        for it in items
    ]

    ratings = (
        db.query(Rating)
        .filter(Rating.rated_user_id == user.id)
        .order_by(Rating.created_at.desc())
        .all()
    )
    reviews = []
    for r in ratings:
        rater = db.get(User, r.rater_id)
        reviews.append({
            "stars": r.stars,
            "comment": r.comment or "",
            "created_at": r.created_at,
            "rater_name": f"{(rater.first_name or '').strip()} {(rater.last_name or '').strip()}".strip() if rater else "مستخدم",
        })

    ratings_count = len(ratings)
    avg_stars = float(sum([r.stars for r in ratings]) / ratings_count) if ratings_count else 0.0

    badges_user = get_user_badges(user, db)

    return request.app.templates.TemplateResponse(
        "user_public.html",
        {
            "request": request,
            "title": f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip(),
            "user": user,
            "badges": badges_user,
            "items": view_items,
            "reviews": reviews,
            "ratings_count": ratings_count,
            "avg_stars": avg_stars,
            "session_user": request.session.get("user"),
        }
    )


# ========================== رفع/تصحيح الوثائق ==========================
@router.get("/profile/docs")
def profile_docs_get(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    user = db.get(User, u["id"])
    return request.app.templates.TemplateResponse(
        "profile_docs.html",
        {"request": request, "title": "تصحيح بيانات التحقق", "user": user, "session_user": u}
    )


@router.post("/profile/docs")
def profile_docs_post(
    request: Request,
    db: Session = Depends(get_db),
    action: str = Form(...),              # "avatar" أو "documents"
    avatar: UploadFile = File(None),
    doc_type: str = Form(None),
    doc_country: str = Form(None),
    doc_expiry: str = Form(None),
    doc_front: UploadFile = File(None),
    doc_back: UploadFile = File(None),
):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    user: User | None = db.get(User, u["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    message = None

    if action == "avatar":
        try:
            if not avatar:
                raise ValueError("no file")
            new_url = _upload_avatar_cloudinary(avatar, folder="sevor/avatars")
            user.avatar_path = new_url
            db.commit()

            # تحديث الجلسة فورًا ليظهر الأفاتار الجديد في الواجهة
            sess = request.session.get("user") or {}
            sess["avatar_path"] = new_url
            request.session["user"] = sess

            message = "تم تحديث صورة الحساب بنجاح."
        except Exception as e:
            message = "تعذّر رفع الصورة. تأكد من الملف وحاول مرة أخرى."

    elif action == "documents":
        # أنشئ/حدّث سجل الوثيقة
        doc = user.documents[0] if user.documents else Document(user_id=user.id)

        if doc_type:
            doc.doc_type = doc_type
        if doc_country:
            doc.country = doc_country
        if doc_expiry:
            try:
                doc.expiry_date = datetime.strptime(doc_expiry, "%Y-%m-%d").date()
            except Exception:
                pass

        # ارفع للـ Cloudinary (صورة أو PDF)
        try:
            if doc_front:
                doc.file_front_path = _upload_doc_cloudinary(doc_front, folder="sevor/ids")
            if doc_back:
                doc.file_back_path = _upload_doc_cloudinary(doc_back, folder="sevor/ids")
        except Exception:
            # حتى لو فشل رفع أحدهما، نُكمل بما تيسّر
            pass

        doc.review_status = "pending"
        doc.reviewed_at = None

        if doc not in user.documents:
            db.add(doc)
        db.commit()

        message = "تم حفظ الوثائق وإرسالها للمراجعة."

    # حدّث النسخة بعد الحفظ
    user = db.get(User, u["id"])
    return request.app.templates.TemplateResponse(
        "profile_docs.html",
        {
            "request": request,
            "title": "تصحيح بيانات التحقق",
            "user": user,
            "session_user": u,
            "message": message,
        }
    )
