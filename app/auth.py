# app/auth.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os, secrets, shutil

from .database import get_db
from .models import User, Document
from .utils import hash_password, verify_password, MAX_FORM_PASSWORD_CHARS

# (اختياري) إشعارات داخلية، نترك الاستيراد لعدم كسر الملفات الأخرى
try:
    from .notifications_api import push_notification  # noqa: F401
except Exception:
    pass

# ======= Email System =======
from .email_service import send_email

# ===== تواقيع رابط التفعيل =====
from itsdangerous import URLSafeTimedSerializer

BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")

router = APIRouter()

# مجلدات الرفع العامة
UPLOADS_ROOT = os.environ.get("UPLOADS_DIR", "uploads")
IDS_DIR = os.path.join(UPLOADS_ROOT, "ids")
AVATARS_DIR = os.path.join(UPLOADS_ROOT, "avatars")
os.makedirs(IDS_DIR, exist_ok=True)
os.makedirs(AVATARS_DIR, exist_ok=True)

def _normalize_form_password(pwd: str) -> str:
    """قص بسيط لإدخال كلمة السر لتفادي كلمات سر عملاقة."""
    if pwd is None:
        return ""
    return pwd[:MAX_FORM_PASSWORD_CHARS]

def _save_any(fileobj: UploadFile | None, folder: str, allow_exts: list[str]) -> str | None:
    """حفظ ملف بصورة آمنة مع توليد اسم عشوائي وإرجاع المسار."""
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

# ============ Login ============
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
    password: str = Form(...),
):
    email = (email or "").strip().lower()
    password = _normalize_form_password(password or "")

    user = db.query(User).filter(User.email == email).first()
    ok = bool(user) and verify_password(password, user.password_hash)

    if not ok:
        return RedirectResponse(url="/login?err=1", status_code=303)

    # ✅ منع الدخول قبل تفعيل الإيميل
    if not bool(getattr(user, "is_verified", False)):
        return RedirectResponse(url=f"/verify-email?email={email}", status_code=303)

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

# ============ Register ============
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
    doc_front: UploadFile = File(...),
    doc_back: UploadFile = File(None),
    avatar: UploadFile = File(...),
):
    email = (email or "").strip().lower()
    password = _normalize_form_password(password or "")

    # تحقق من وجود المستخدم
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

    # حفظ الوثائق
    front_path = _save_any(doc_front, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"])
    back_path = _save_any(doc_back, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"]) if doc_back else None
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

    # إنشاء المستخدم
    u = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        role="user",
        status="pending",
        avatar_path=avatar_path,
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    # تسجيل الوثيقة
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

    # ===== إرسال بريد التفعيل (تصميم احترافي) =====
    try:
        s = _signer()
        token = s.dumps({"uid": u.id, "email": u.email})
        verify_url = f"{BASE_URL}/activate/verify?token={token}"
        logo = f"{BASE_URL}/static/images/ok.png"
        brand = f"{BASE_URL}/static/images/base.png"
        year = datetime.utcnow().year

        subj = "Activate your account — RentAll"

        html = f"""<!doctype html>
<html lang="ar" dir="rtl">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>تفعيل الحساب</title></head>
  <body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,'Segoe UI',sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0">فعّل حسابك لإتمام الدخول واستخدام المنصّة</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b0f1a;padding:24px 12px">
      <tr><td align="center">
        <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="width:100%;max-width:640px;background:#0f172a;border:1px solid #1f2937;border-radius:16px;overflow:hidden">
          <tr>
            <td style="padding:20px 24px;background:linear-gradient(90deg,#111827,#0b1220)">
              <table width="100%"><tr>
                <td align="right"><img src="{brand}" alt="اسم الموقع" style="height:22px;opacity:.95"></td>
                <td align="left"><img src="{logo}" alt="Logo" style="height:36px;border-radius:8px"></td>
              </tr></table>
            </td>
          </tr>
          <tr><td style="padding:28px 26px">
            <h2 style="margin:0 0 12px;font-size:22px;color:#ffffff;">مرحبًا {first_name} 👋</h2>
            <p style="margin:0 0 12px;line-height:1.9;color:#cbd5e1">
              شكرًا لتسجيلك في <b style="color:#fff">RentAll</b>.
              لتأمين حسابك والبدء، اضغط على الزر أدناه لتفعيل بريدك الإلكتروني.
            </p>
            <!-- Button : BEGIN -->
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:26px auto">
              <tr><td bgcolor="#2563eb" style="border-radius:10px;">
                <a href="{verify_url}" target="_blank"
                   style="font-family:Tahoma,Arial,sans-serif;font-size:16px;line-height:16px;text-decoration:none;
                          padding:14px 22px;display:inline-block;color:#ffffff;border-radius:10px;font-weight:700">
                  تفعيل الحساب
                </a>
              </td></tr>
            </table>
            <!-- Button : END -->
            <p style="margin:0 0 8px;color:#94a3b8;font-size:13px">إن لم يعمل الزر، استخدم هذا الرابط:</p>
            <p style="margin:0 0 16px;word-break:break-all"><a href="{verify_url}" style="color:#60a5fa;text-decoration:none">{verify_url}</a></p>
            <div style="margin-top:20px;padding:12px 14px;border:1px dashed #334155;border-radius:10px;color:#cbd5e1;font-size:13px">
              ملاحظة: حتى بعد تفعيل البريد، يبقى زر <b>احجز الآن</b> مُعطّلًا إلى أن يراجع الأدمين صورك ووثائقك ويوافق على حسابك.
            </div>
          </td></tr>
          <tr><td style="padding:18px 24px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
            إذا لم تقم بالتسجيل، يمكنك تجاهل هذه الرسالة.
          </td></tr>
        </table>
        <div style="color:#64748b;font-size:11px;margin-top:12px">&copy; {year} RentAll — جميع الحقوق محفوظة</div>
      </td></tr>
    </table>
  </body>
</html>"""

        text = f"مرحبًا {first_name}\n\nفعّل حسابك عبر الرابط:\n{verify_url}\n\nإن لم تكن أنت، تجاهل الرسالة."
        send_email(u.email, subj, html, text_body=text)
    except Exception:
        pass

    # ✅ نرسل لصفحة التحقق من البريد
    return RedirectResponse(url=f"/verify-email?email={u.email}&sent=1", status_code=303)

# ============ Email Verify Wall ============
@router.get("/verify-email")
def verify_email_page(request: Request, email: str = ""):
    """
    صفحة تُظهر للمستخدم أنه يجب عليه تفعيل بريده أولاً.
    تُعرض بعد التسجيل أو إذا حاول تسجيل الدخول بدون تفعيل.
    """
    return request.app.templates.TemplateResponse(
        "verify_email.html",
        {
            "request": request,
            "title": "تحقق من بريدك",
            "email": (email or "").strip(),
            "session_user": request.session.get("user"),
        },
    )

# ============ Logout ============
@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)