# app/activate.py
import os, secrets, shutil
from datetime import datetime
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Document

router = APIRouter()

# مجلدات الرفع
UPLOADS_ROOT = os.environ.get("UPLOADS_DIR", "uploads")
AVATARS_DIR = os.path.join(UPLOADS_ROOT, "avatars")
IDS_DIR = os.path.join(UPLOADS_ROOT, "ids")
os.makedirs(AVATARS_DIR, exist_ok=True)
os.makedirs(IDS_DIR, exist_ok=True)

def _save(fileobj: UploadFile, folder: str, allow_exts):
    if not fileobj:
        return None
    ext = os.path.splitext(fileobj.filename)[1].lower()
    if ext not in allow_exts:
        return None
    fname = f"{secrets.token_hex(12)}{ext}"
    fpath = os.path.join(folder, fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(fileobj.file, f)
    return fpath.replace("\\", "/")

def _require_login(request: Request):
    return request.session.get("user")

@router.get("/activate")
def activate_get(request: Request, db: Session = Depends(get_db)):
    """
    صفحة إكمال التفعيل للمستخدمين pending/rejected.
    (لا علاقة لها بتفعيل البريد، فقط لرفع صورة/وثائق)
    """
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    docs = user.documents or []

    if user.status == "approved":
        return RedirectResponse(url="/", status_code=303)

    review_note = None
    if docs:
        for d in sorted(docs, key=lambda x: x.created_at or datetime.utcnow(), reverse=True):
            if getattr(d, "review_note", None):
                review_note = d.review_note
                break

    return request.app.templates.TemplateResponse(
        "activate.html",
        {
            "request": request,
            "title": "إكمال التفعيل",
            "user": user,
            "docs": docs,
            "review_note": review_note,
            "session_user": sess
        }
    )

@router.post("/activate/avatar")
def activate_update_avatar(
    request: Request,
    db: Session = Depends(get_db),
    avatar: UploadFile = File(...),
):
    """
    إعادة التقاط/رفع صورة الحساب (كاميرا فقط من الواجهة).
    تُحدَّث الصورة وتبقى الحالة كما هي حتى يراجع الأدمِن.
    """
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    path = _save(avatar, AVATARS_DIR, [".jpg", ".jpeg", ".png", ".webp"])
    if path:
        user.avatar_path = path
        db.commit()
    return RedirectResponse(url="/activate", status_code=303)

@router.post("/activate/document")
def activate_update_document(
    request: Request,
    db: Session = Depends(get_db),
    doc_type: str = Form("id_card"),
    country: str = Form(""),
    expiry: str = Form(""),
    doc_front: UploadFile = File(...),
    doc_back: UploadFile = File(None),
):
    """
    إعادة رفع الوثيقة (وجه أمامي إجباري + خلفي اختياري).
    تنشئ سجل وثيقة جديد بوضع pending ليُراجع من الأدمِن.
    """
    from datetime import datetime as dt

    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])

    front_path = _save(doc_front, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"])
    back_path = _save(doc_back, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"]) if doc_back else None

    expiry_date = None
    if expiry:
        try:
            expiry_date = dt.strptime(expiry, "%Y-%m-%d").date()
        except Exception:
            expiry_date = None

    d = Document(
        user_id=user.id,
        doc_type=doc_type,
        country=country,
        expiry_date=expiry_date,
        file_front_path=front_path,
        file_back_path=back_path,
        review_status="pending",
        review_note=None,
        created_at=datetime.utcnow(),
    )
    db.add(d)
    db.commit()

    return RedirectResponse(url="/activate", status_code=303)

# ===== تفعيل البريد عبر التوكن + تسجيل دخول تلقائي =====
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

def _signer() -> URLSafeTimedSerializer:
    secret = os.getenv("SECRET_KEY", "dev-secret")
    return URLSafeTimedSerializer(secret_key=secret, salt="email-verify-v1")

@router.get("/activate/verify")
def activate_verify(token: str, request: Request, db: Session = Depends(get_db)):
    """
    يفك التوكن (صالحيته 3 أيام). إذا كان صحيحًا:
      - يضبط is_verified=True و verified_at=الآن (إن وُجد العمود)
      - يضبط status="approved" (لتفعيل الحجز مباشرة)
      - ينشئ جلسة (login) للمستخدم
      - يحوّل للصفحة الرئيسية
    """
    s = _signer()
    try:
        data = s.loads(token, max_age=60 * 60 * 24 * 3)  # 3 أيام
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="انتهت صلاحية رابط التفعيل.")
    except BadSignature:
        raise HTTPException(status_code=400, detail="رابط التفعيل غير صالح.")

    uid = int((data or {}).get("uid") or 0)
    email = ((data or {}).get("email") or "").strip().lower()
    if not uid or not email:
        raise HTTPException(status_code=400, detail="بيانات التفعيل ناقصة.")

    user = db.query(User).get(uid)
    if not user or (user.email or "").lower() != email:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود.")

    # ✅ تفعيل البريد + الموافقة على الحساب للحجز
    try:
        user.is_verified = True
        if hasattr(user, "verified_at"):
            user.verified_at = datetime.utcnow()
        if hasattr(user, "status"):
            user.status = "approved"
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception:
        pass

    # تسجيل دخول تلقائي بالبيانات المحدثة
    request.session["user"] = {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "status": user.status,      # الآن "approved"
        "is_verified": True,
        "avatar_path": user.avatar_path or None,
    }

    return RedirectResponse(url="/", status_code=303)