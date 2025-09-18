# app/profiles.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from .database import get_db
from .models import User, Item, Rating

# ======= [إضافات] استيرادات مطلوبة لمسارات التصحيح والرفع =======
from fastapi import UploadFile, File, Form
import os, secrets, shutil
# ================================================================

router = APIRouter()


@router.get("/profile")
def profile(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    me: User = db.query(User).get(u["id"])
    if not me:
        return RedirectResponse(url="/login", status_code=303)

    # إحصائيات العناصر
    items_count = db.query(Item).filter(Item.owner_id == me.id).count()
    items_active_count = (
        db.query(Item)
        .filter(Item.owner_id == me.id, Item.is_active == "yes")
        .count()
    )

    # التقييمات: متوسط + عدد + آخر 5 مراجعات
    ratings_q = db.query(Rating).filter(Rating.rated_user_id == me.id)
    ratings_count = ratings_q.count()

    avg_stars = (
        db.query(func.avg(Rating.stars))
        .filter(Rating.rated_user_id == me.id)
        .scalar()
    )
    avg_stars = round(float(avg_stars), 1) if avg_stars is not None else 0.0

    last_reviews = (
        ratings_q.order_by(Rating.created_at.desc()).limit(5).all()
    )

    # هيكل آمن للمراجعات (نجيب أسماء القيّمين)
    reviews_view = []
    for r in last_reviews:
        rater = db.query(User).get(r.rater_id)
        reviews_view.append(
            {
                "stars": r.stars,
                "comment": r.comment or "",
                "created_at": r.created_at,
                "rater_name": f"{rater.first_name} {rater.last_name}" if rater else "مستخدم",
            }
        )

    joined_at = me.created_at or datetime.utcnow()

    return request.app.templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "title": "صفحتي",
            "session_user": u,
            "user": me,
            # إحصائيات
            "items_count": items_count,
            "items_active_count": items_active_count,
            # تقييمات
            "avg_stars": avg_stars,
            "ratings_count": ratings_count,
            "reviews": reviews_view,
            "joined_at": joined_at,
        },
    )


@router.get("/u/{user_id}")
def public_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    # المستخدم صاحب الصفحة
    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/", status_code=303)

    # عناصره (يمكنك تعديل الحد/الترتيب كما تشاء)
    items = (
        db.query(Item)
        .filter(Item.owner_id == user.id)
        .order_by(Item.created_at.desc())
        .all()
    )
    view_items = []
    for it in items:
        view_items.append({
            "id": it.id,
            "title": it.title,
            "image_path": it.image_path,
            "price_per_day": it.price_per_day,
            "category": it.category,
        })

    # تقييماته (المستلمة)
    ratings = (
        db.query(Rating)
        .filter(Rating.rated_user_id == user.id)
        .order_by(Rating.created_at.desc())
        .all()
    )

    # اسم المُقيِّم لكل تقييم
    reviews = []
    for r in ratings:
        rater = db.query(User).get(r.rater_id)
        reviews.append({
            "stars": r.stars,
            "comment": r.comment or "",
            "created_at": r.created_at,
            "rater_name": f"{rater.first_name} {rater.last_name}" if rater else "مستخدم",
        })

    # متوسط وعدد
    ratings_count = len(ratings)
    avg_stars = float(sum([r.stars for r in ratings]) / ratings_count) if ratings_count else 0.0

    return request.app.templates.TemplateResponse(
        "user_public.html",
        {
            "request": request,
            "title": f"{user.first_name} {user.last_name}",
            "user": user,                    # نمرّر الكائن نفسه للاستفادة من is_verified
            "items": view_items,
            "reviews": reviews,
            "ratings_count": ratings_count,
            "avg_stars": avg_stars,
            "session_user": request.session.get("user"),
        }
    )


# ========================== [إضافات جديدة] ==========================
# صفحة تصحيح بيانات التحقق (صورة الحساب والوثائق)
UPLOADS_ROOT = os.environ.get("UPLOADS_DIR", "uploads")
AVATARS_DIR = os.path.join(UPLOADS_ROOT, "avatars")
IDS_DIR = os.path.join(UPLOADS_ROOT, "ids")
os.makedirs(AVATARS_DIR, exist_ok=True)
os.makedirs(IDS_DIR, exist_ok=True)

def _save_any(fileobj: UploadFile | None, folder: str, allow_exts: list[str]):
    """حفظ ملف مع توليد اسم آمن وإرجاع المسار (أو None إن لم يُرفع/نوع غير مسموح)."""
    if not fileobj:
        return None
    ext = os.path.splitext(fileobj.filename)[1].lower()
    if ext not in allow_exts:
        return None
    fname = f"{secrets.token_hex(10)}{ext}"
    fpath = os.path.join(folder, fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(fileobj.file, f)
    return fpath.replace("\\", "/")

@router.get("/profile/docs")
def profile_docs_get(request: Request, db: Session = Depends(get_db)):
    """عرض صفحة إعادة رفع/تصحيح صورة الحساب والوثائق."""
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    user = db.query(User).get(u["id"])
    return request.app.templates.TemplateResponse(
        "profile_docs.html",
        {"request": request, "title": "تصحيح بيانات التحقق", "user": user, "session_user": u}
    )

@router.post("/profile/docs")
def profile_docs_post(
    request: Request,
    db: Session = Depends(get_db),
    action: str = Form(...),                # "avatar" أو "documents"
    # avatar
    avatar: UploadFile = File(None),
    # docs
    doc_type: str = Form(None),
    doc_country: str = Form(None),
    doc_expiry: str = Form(None),
    doc_front: UploadFile = File(None),
    doc_back: UploadFile = File(None),
):
    """حفظ التعديلات: صورة الحساب أو الوثائق، وإرجاع الصفحة مع رسالة نجاح/خطأ."""
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(u["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    message = None

    if action == "avatar":
        # تحديث صورة الحساب
        new_path = _save_any(avatar, AVATARS_DIR, [".jpg", ".jpeg", ".png", ".webp"])
        if new_path:
            user.avatar_path = new_path
            db.commit()
            message = "تم تحديث صورة الحساب بنجاح."
        else:
            message = "صورة غير صالحة. يُقبل JPG/PNG/WebP."

    elif action == "documents":
        # أنشئ أو اجلب سجل الوثيقة الأول
        doc = (user.documents[0] if user.documents else None)
        from .models import Document  # استيراد محلي لتفادي الدوائر
        if not doc:
            doc = Document(user_id=user.id)

        if doc_type: doc.doc_type = doc_type
        if doc_country: doc.country = doc_country
        if doc_expiry:
            try:
                doc.expiry_date = datetime.strptime(doc_expiry, "%Y-%m-%d").date()
            except:
                pass

        # حفظ الملفات لو تم رفعها
        fp = _save_any(doc_front, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"])
        if fp: doc.file_front_path = fp
        bp = _save_any(doc_back, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"])
        if bp: doc.file_back_path = bp

        # عند التصحيح: نعيد الحالة إلى pending
        doc.review_status = "pending"
        doc.reviewed_at = None
        if doc not in user.documents:
            db.add(doc)
        db.commit()
        message = "تم حفظ الوثائق وإرسالها للمراجعة."

    # بعد الحفظ نعيد عرض الصفحة مع رسالة
    user = db.query(User).get(u["id"])
    return request.app.templates.TemplateResponse(
        "profile_docs.html",
        {"request": request, "title": "تصحيح بيانات التحقق", "user": user, "session_user": u, "message": message}
    )
# ===================================================================
