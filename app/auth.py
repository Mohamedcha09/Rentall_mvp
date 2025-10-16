# app/auth.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os, secrets, shutil

from .database import get_db
from .models import User, Document
from .utils import hash_password, verify_password, MAX_FORM_PASSWORD_CHARS

# ===== إشعارات (مضاف) =====
from .notifications_api import push_notification  # ← استخدام للإشعار بعد التسجيل

# ===== SMTP Email (fallback) =====
# سنستبدل هذا لاحقًا بـ app/emailer.py، لكن الآن نجعله لا يكسر التنفيذ إن لم يوجد.
try:
    from .emailer import send_email  # سيُنشأ لاحقًا
except Exception:
    def send_email(to, subject, html_body, text_body=None, cc=None, bcc=None, reply_to=None):
        return False  # NO-OP مؤقتًا

BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")

# ==== تفعيل الإيميل (توكنات موقّعة) ====
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")  # ضعه في .env
ACTIVATE_SALT = os.getenv("ACTIVATE_EMAIL_SALT", "activate-email-salt")
ACTIVATE_MAX_AGE = int(os.getenv("ACTIVATE_LINK_MAX_AGE_SECONDS", "259200"))  # 3 أيام

def _activation_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(SECRET_KEY, salt=ACTIVATE_SALT)

def make_activation_token(user_id: int, email: str) -> str:
    data = {"uid": int(user_id), "email": (email or "").strip().lower()}
    return _activation_serializer().dumps(data)

router = APIRouter()

# مجلدات الرفع العامة
UPLOADS_ROOT = os.environ.get("UPLOADS_DIR", "uploads")
IDS_DIR = os.path.join(UPLOADS_ROOT, "ids")
AVATARS_DIR = os.path.join(UPLOADS_ROOT, "avatars")  # ← مجلد صور الحساب
os.makedirs(IDS_DIR, exist_ok=True)
os.makedirs(AVATARS_DIR, exist_ok=True)

def _normalize_form_password(pwd: str) -> str:
    """
    قص بسيط لإدخال كلمة السر من الفورم لتفادي كلمات سر عملاقة.
    (القص النهائي على 72 بايت يحصل داخل utils أيضاً)
    """
    if pwd is None:
        return ""
    return pwd[:MAX_FORM_PASSWORD_CHARS]

def _save_any(fileobj: UploadFile | None, folder: str, allow_exts: list[str]) -> str | None:
    """
    حفظ ملف بصورة آمنة مع توليد اسم عشوائي وإرجاع المسار (forward slashes).
    """
    if not fileobj:
        return None
    ext = os.path.splitext(fileobj.filename or "")[1].lower()
    if ext not in allow_exts:
        return None
    fname = f"{secrets.token_hex(10)}{ext}"
    fpath = os.path.join(folder, fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(fileobj.file, f)
    return fpath.replace("\\", "/")

@router.get("/login")
def login_get(request: Request):
    return request.app.templates.TemplateResponse(
        "auth_login.html",
        {"request": request, "title": "دخول", "session_user": request.session.get("user")}
    )

@router.post("/login")
def login_post(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...)
):
    email = (email or "").strip().lower()
    password = _normalize_form_password(password or "")

    user = db.query(User).filter(User.email == email).first()
    ok = bool(user) and verify_password(password, user.password_hash)

    if not ok:
        # فشل → رجوع لنفس الصفحة مع باراميتر خطأ
        return RedirectResponse(url="/login?err=1", status_code=303)

    # خزّن is_verified و avatar_path ضمن السيشن (لإظهار الشارة والصورة)
    request.session["user"] = {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "status": user.status,
        "is_verified": bool(user.is_verified),
        "avatar_path": user.avatar_path or None,
    }
    return RedirectResponse(url="/", status_code=303)

@router.get("/register")
def register_get(request: Request):
    return request.app.templates.TemplateResponse(
        "auth_register.html",
        {"request": request, "title": "تسجيل", "session_user": request.session.get("user")}
    )

@router.post("/register")
def register_post(
    request: Request,
    db: Session = Depends(get_db),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    doc_type: str = Form(...),
    doc_country: str = Form(...),
    doc_expiry: str = Form(None),
    # الوثائق
    doc_front: UploadFile = File(...),
    doc_back: UploadFile = File(None),
    # صورة الحساب (إلزامي)
    avatar: UploadFile = File(...)
):
    email = (email or "").strip().lower()
    password = _normalize_form_password(password or "")

    # موجود مسبقًا؟
    exists = db.query(User).filter(User.email == email).first()
    if exists:
        return request.app.templates.TemplateResponse(
            "auth_register.html",
            {
                "request": request,
                "title": "تسجيل",
                "message": "هذا البريد مستخدم بالفعل",
                "session_user": request.session.get("user"),
            },
        )

    # احفظ الوثائق
    front_path = _save_any(doc_front, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"])
    back_path = _save_any(doc_back, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"]) if doc_back else None

    # احفظ صورة الحساب (صور فقط)
    avatar_path = _save_any(avatar, AVATARS_DIR, [".jpg", ".jpeg", ".png", ".webp"])
    if not avatar_path:
        return request.app.templates.TemplateResponse(
            "auth_register.html",
            {
                "request": request,
                "title": "تسجيل",
                "message": "صورة الحساب مطلوبة ويجب أن تكون صورة (JPG/PNG/WebP).",
                "session_user": request.session.get("user"),
            },
        )

    # أنشئ المستخدم
    u = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        role="user",
        status="pending",
        avatar_path=avatar_path
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    # سجل الوثيقة
    expiry = None
    if doc_expiry:
        try:
            expiry = datetime.strptime(doc_expiry, "%Y-%m-%d").date()
        except Exception:
            expiry = None

    d = Document(
        user_id=u.id,
        doc_type=doc_type,
        country=doc_country,
        expiry_date=expiry,
        file_front_path=front_path,
        file_back_path=back_path,
        review_status="pending",
    )
    db.add(d)
    db.commit()

    # ===== إشعار داخلي بعد التسجيل (مضاف) =====
    try:
        push_notification(
            db,
            user_id=u.id,
            title="✅ تأكيد التسجيل",
            body="تم إنشاء حسابك بنجاح. رجاءً فعّل بريدك الإلكتروني لإكمال التسجيل.",
            url="/activate",              # مسار صفحة/تدفق التفعيل لديك
            kind="system"
        )
    except Exception:
        # لا نكسر التدفق لو تعذّر الإشعار
        pass

    # ===== بريد تفعيل الحساب (آمن بتوكن) =====
    try:
        token = make_activation_token(u.id, u.email)
        activate_url = f"{BASE_URL}/activate/confirm?token={token}"
        subj = "Activate your account — RentAll"
        html = (
            f"<p>مرحبًا {first_name},</p>"
            f"<p>شكرًا لتسجيلك في RentAll. رجاءً فعّل حسابك عبر الرابط التالي (صالح 72 ساعة):</p>"
            f'<p><a href="{activate_url}">{activate_url}</a></p>'
            "<p>إذا لم تقم بالتسجيل، تجاهل هذه الرسالة.</p>"
        )
        send_email(u.email, subj, html, text_body=f"Activate: {activate_url}")
    except Exception:
        pass

    return RedirectResponse(url="/login", status_code=303)

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)