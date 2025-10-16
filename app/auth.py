# app/auth.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os, secrets, shutil

from .database import get_db
from .models import User, Document
from .utils import hash_password, verify_password, MAX_FORM_PASSWORD_CHARS

# (اختياري) لديك إشعارات داخلية في المشروع، لكننا لن نستخدمها لتفعيل البريد
# من أجل عدم كسر الاستيراد في أماكن أخرى نتركه موجودًا إن احتاجته ملفات ثانية
try:
    from .notifications_api import push_notification  # noqa: F401
except Exception:
    pass

# ===== SMTP Email helper =====
# سنستخدم app/emailer.py لو موجود. وإلا نعمل NO-OP.
try:
    from .emailer import send_email  # ← يرسل عبر SMTP (Gmail)
except Exception:
    def send_email(to, subject, html_body, text_body=None, cc=None, bcc=None, reply_to=None):
        return False  # NO-OP مؤقتًا

# ===== تواقيع رابط التفعيل =====
from itsdangerous import URLSafeTimedSerializer

BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")

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

def _signer() -> URLSafeTimedSerializer:
    secret = os.getenv("SECRET_KEY", "dev-secret")
    return URLSafeTimedSerializer(secret_key=secret, salt="email-verify-v1")

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
        status="pending",   # حالة المراجعة الإدارية إن كانت لديك
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

    # ===== (جديد) بريد تفعيل الحساب فقط (بدون إشعار داخلي) =====
    try:
        s = _signer()
        token = s.dumps({"uid": u.id, "email": u.email})
        verify_url = f"{BASE_URL}/activate/verify?token={token}"

        subj = "Activate your account — RentAll"
        html = f"""
        <div style="font-family:Tahoma,Arial,sans-serif;line-height:1.8;direction:rtl;text-align:right">
          <h3 style="margin:0 0 12px">مرحبًا {first_name} 👋</h3>
          <p>شكرًا لتسجيلك في <b>RentAll</b>. اضغط الزر أدناه لتفعيل حسابك وتسجيل الدخول تلقائيًا:</p>
          <p style="text-align:center;margin:24px 0">
            <a href="{verify_url}"
               style="display:inline-block;padding:12px 20px;border-radius:8px;
                      background:#2563eb;color:#fff;text-decoration:none;font-weight:700">
              تفعيل الحساب
            </a>
          </p>
          <p style="color:#666;font-size:13px">إن لم يظهر الزر، افتح هذا الرابط:</p>
          <p style="word-break:break-all"><a href="{verify_url}">{verify_url}</a></p>
          <p style="color:#888;font-size:12px">إذا لم تقم بالتسجيل، تجاهل هذه الرسالة.</p>
        </div>
        """
        text = f"مرحبًا {first_name}\n\nفعّل حسابك عبر الرابط:\n{verify_url}\n\nإن لم تكن أنت، تجاهل الرسالة."
        send_email(u.email, subj, html, text_body=text)
    except Exception:
        # لا نكسر التدفق إذا فشل الإرسال
        pass

    return RedirectResponse(url="/login?check_email=1", status_code=303)

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
