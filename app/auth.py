from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os, secrets, shutil

from .database import get_db
from .models import User, Document
from .utils import hash_password, verify_password, MAX_FORM_PASSWORD_CHARS

# (اختياري) إشعارات داخلية
try:
    from .notifications_api import push_notification  # noqa: F401
except Exception:
    pass

# ======= Email System =======
from .email_service import send_email

# ===== روابط موقّعة =====
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

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

# ✅ مُوقّع خاص بإعادة التعيين (ملح مختلف)
def _pwd_signer() -> URLSafeTimedSerializer:
    secret = os.getenv("SECRET_KEY", "dev-secret")
    return URLSafeTimedSerializer(secret_key=secret, salt="pwd-reset-v1")


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

    # ✅ السماح للأدمن بالدخول فورًا + تفعيل كامل تلقائيًا
    if str(getattr(user, "role", "")).lower() == "admin":
        changed = False
        if not bool(getattr(user, "is_verified", False)):
            user.is_verified = True
            user.verified_at = datetime.utcnow()
            changed = True
        # اتساق الحالة
        if (getattr(user, "status", "pending") or "").lower() != "active":
            user.status = "active"
            changed = True
        # (اختياري) اجعله مدير ودائع تلقائيًا إن كان الحقل موجود
        try:
            if not bool(getattr(user, "is_deposit_manager", False)):
                user.is_deposit_manager = True
                changed = True
        except Exception:
            pass
        if changed:
            db.add(user)
            db.commit()
            db.refresh(user)

    else:
        # 🧱 المستخدمون العاديون: ما زال مطلوب تحقق البريد
        if not bool(getattr(user, "is_verified", False)):
            return RedirectResponse(url=f"/verify-email?email={email}", status_code=303)

    # ✅ أنشئ الجلسة وسجّل الدخول
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
        "is_deposit_manager": bool(getattr(user, "is_deposit_manager", False)),
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

    # ===== إرسال بريد التفعيل =====
    try:
        s = _signer()
        token = s.dumps({"uid": u.id, "email": u.email})
        verify_url = f"{BASE_URL}/activate/verify?token={token}"
        year = datetime.utcnow().year
        subj = "Activate your account — RentAll"

        html = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>تفعيل الحساب</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;color:#eaf0ff;font-family:Arial,'Segoe UI',Tahoma,sans-serif;direction:rtl;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#0f172a;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;background:#111827;border:1px solid #223049;border-radius:16px;overflow:hidden;">
          <tr>
            <td style="padding:20px 22px;background:#0f172a;border-bottom:1px solid #223049;">
              <span style="display:inline-block;background:rgba(37,99,235,.15);border:1px solid rgba(37,99,235,.35);color:#cfe0ff;padding:6px 10px;border-radius:999px;font-size:13px;">SEVOR • RentAll</span>
            </td>
          </tr>
          <tr>
            <td style="padding:22px;">
              <h2 style="margin:0 0 10px 0;font-weight:800;font-size:22px;line-height:1.4;color:#eaf0ff;">مرحبًا {first_name} 👋</h2>
              <p style="margin:0 0 16px 0;font-size:15px;line-height:1.8;color:#cdd7ee;">
                شكرًا لتسجيلك في <b>RentAll</b>. لتأمين حسابك والبدء، اضغط على الزر أدناه لتفعيل بريدك الإلكتروني:
              </p>
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:18px auto;">
                <tr>
                  <td align="center" bgcolor="#2563eb" style="border-radius:12px;">
                    <a href="{verify_url}" target="_blank"
                       style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;
                              font-weight:700;font-size:18px;line-height:48px;border-radius:12px;
                              padding:0 26px;min-width:200px;text-align:center;cursor:pointer;">
                      تفعيل الحساب
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:22px 0 6px 0;font-size:14px;color:#93a4c9;">إن لم يعمل الزر، انسخ وافتح هذا الرابط:</p>
              <p dir="ltr" style="margin:0 0 16px 0;font-size:14px;word-break:break-all;">
                <a href="{verify_url}" style="color:#60a5fa;text-decoration:underline;" target="_blank">{verify_url}</a>
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:14px 22px;background:#0b1220;color:#94a3b8;font-size:11px;text-align:center;">
              ©️ {year} RentAll
            </td>
          </tr>
        </table>
      </td>
    </tr>
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
def verify_email_page(request: Request, email: str = "", db: Session = Depends(get_db)):
    """
    لو البريد الموجود في الكويري هو أدمن أو حسابه مفعّل -> رجّعه للصفحة الرئيسية حتى بدون جلسة.
    غير كذا اعرض صفحة التحقق.
    """
    u = request.session.get("user") or {}
    if u and (u.get("role", "").lower() == "admin" or bool(u.get("is_verified"))):
        return RedirectResponse("/", status_code=303)

    em = (email or "").strip().lower()
    if em:
        user = db.query(User).filter(User.email == em).first()
        if user:
            if (getattr(user, "role", "") or "").lower() == "admin" or bool(getattr(user, "is_verified", False)):
                return RedirectResponse("/", status_code=303)

    return request.app.templates.TemplateResponse(
        "verify_email.html",
        {"request": request, "title": "تحقق من بريدك", "email": em, "session_user": u or None},
    )


# ============ تفعيل الحساب عبر الرابط ============
@router.get("/activate/verify")
def verify_from_email(request: Request, token: str = "", db: Session = Depends(get_db)):
    """
    يفكّ توقيع التوكن ويُفعّل الحساب مباشرة: is_verified=True و status=active
    ثم يوجّه للصفحة الرئيسية.
    """
    if not token:
        return RedirectResponse(url="/verify-email", status_code=303)
    try:
        data = _signer().loads(token, max_age=48 * 3600)  # صلاحية 48 ساعة
        uid = int(data.get("uid", 0))
        email = (data.get("email") or "").strip().lower()
    except SignatureExpired:
        return RedirectResponse(url="/verify-email?expired=1", status_code=303)
    except BadSignature:
        return RedirectResponse(url="/verify-email?bad=1", status_code=303)

    user = db.query(User).filter(User.id == uid, User.email == email).first()
    if not user:
        return RedirectResponse(url="/verify-email?bad=1", status_code=303)

    if not bool(getattr(user, "is_verified", False)):
        user.is_verified = True
        user.verified_at = datetime.utcnow()
    if (getattr(user, "status", "pending") or "").lower() != "active":
        user.status = "active"
    db.add(user)
    db.commit()
    db.refresh(user)

    # سجّل الجلسة مباشرةً
    request.session["user"] = {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "status": user.status,
        "is_verified": True,
        "avatar_path": user.avatar_path or None,
        "is_deposit_manager": bool(getattr(user, "is_deposit_manager", False)),
    }
    return RedirectResponse("/", status_code=303)


# ============ Password Reset ============
@router.get("/forgot")
def forgot_get(request: Request):
    return request.app.templates.TemplateResponse(
        "auth_forgot.html",
        {"request": request, "title": "إعادة تعيين كلمة المرور", "session_user": request.session.get("user")}
    )

@router.post("/forgot")
def forgot_post(request: Request, db: Session = Depends(get_db), email: str = Form(...)):
    email = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()

    # نُظهر دائمًا نفس الرسالة
    msg = "إن وُجد حساب مطابق، سنرسل رابط إعادة تعيين كلمة المرور إلى بريدك إن شاء الله."

    try:
        if user:
            s = _pwd_signer()
            token = s.dumps({"uid": user.id, "email": user.email})
            reset_url = f"{BASE_URL}/reset-password?token={token}"
            year = datetime.utcnow().year
            subj = "Reset your password — RentAll"

            html = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>إعادة تعيين كلمة المرور</title></head>
<body style="margin:0;padding:0;background:#0f172a;color:#eaf0ff;font-family:Arial,'Segoe UI',Tahoma,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#0f172a;">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;background:#111827;border:1px solid #223049;border-radius:16px;overflow:hidden;">
        <tr>
          <td style="padding:20px 22px;background:#0f172a;border-bottom:1px solid #223049;">
            <span style="display:inline-block;background:rgba(124,92,255,.15);border:1px solid rgba(124,92,255,.35);color:#d8cfff;padding:6px 10px;border-radius:999px;font-size:13px;">إعادة تعيين كلمة المرور</span>
          </td>
        </tr>
        <tr><td style="padding:22px;">
          <p style="margin:0 0 10px 0;color:#cdd7ee">لقد طُلِب إعادة تعيين كلمة المرور لحسابك على <b>RentAll</b>.</p>
          <p style="margin:0 0 14px 0;color:#cdd7ee">اضغط الزر أدناه وأدخل كلمة مرور جديدة:</p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:18px auto;">
            <tr><td bgcolor="#7c5cff" style="border-radius:12px;">
              <a href="{reset_url}" target="_blank"
                 style="display:inline-block;background:#7c5cff;color:#ffffff;text-decoration:none;font-weight:700;
                        font-size:18px;line-height:48px;border-radius:12px;padding:0 26px;min-width:220px;text-align:center;">
                إعادة التعيين الآن
              </a>
            </td></tr>
          </table>
          <p style="margin:18px 0 6px 0;font-size:14px;color:#93a4c9;">إن لم يعمل الزر، استخدم الرابط التالي:</p>
          <p dir="ltr" style="margin:0 0 10px 0;word-break:break-all;">
            <a href="{reset_url}" style="color:#bda7ff;text-decoration:underline" target="_blank">{reset_url}</a>
          </p>
          <p style="margin:12px 0 0 0;font-size:12px;color:#7f8db0;">يتنهي صلاحية هذا الرابط بعد ساعتين.</p>
        </td></tr>
        <tr><td style="padding:14px 22px;background:#0b1220;color:#94a3b8;font-size:11px;text-align:center;">©️ {year} RentAll</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

            text = f"إعادة تعيين كلمة المرور:\n{reset_url}\n(الرابط صالح لساعتين)"
            send_email(user.email, subj, html, text_body=text)
    except Exception:
        pass

    return request.app.templates.TemplateResponse(
        "auth_forgot.html",
        {"request": request, "title": "إعادة تعيين كلمة المرور", "info": msg, "session_user": request.session.get("user")}
    )

# 3) صفحة إدخال كلمة مرور جديدة (من خلال الرابط)
@router.get("/reset-password")
def reset_get(request: Request, token: str = ""):
    if not token:
        return RedirectResponse(url="/forgot", status_code=303)
    return request.app.templates.TemplateResponse(
        "auth_reset_password.html",
        {"request": request, "title": "تعيين كلمة مرور جديدة", "token": token, "session_user": request.session.get("user")}
    )

# 4) حفظ كلمة المرور الجديدة
@router.post("/reset-password")
def reset_post(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    password = _normalize_form_password(password or "")
    confirm  = _normalize_form_password(confirm or "")

    if (not password) or (password != confirm):
        return request.app.templates.TemplateResponse(
            "auth_reset_password.html",
            {
                "request": request,
                "title": "تعيين كلمة مرور جديدة",
                "token": token,
                "error": "كلمتا المرور غير متطابقتين.",
                "session_user": request.session.get("user"),
            },
        )

    # تحقق/فك التوقيع — صلاحية ساعتين
    try:
        data = _pwd_signer().loads(token, max_age=2*60*60)
        uid = int(data.get("uid", 0))
        email = (data.get("email") or "").strip().lower()
    except SignatureExpired:
        return request.app.templates.TemplateResponse(
            "auth_reset_password.html",
            {"request": request, "title": "تعيين كلمة مرور جديدة", "error": "انتهت صلاحية الرابط. اطلب رابطًا جديدًا.", "token": "", "session_user": request.session.get("user")},
        )
    except BadSignature:
        return request.app.templates.TemplateResponse(
            "auth_reset_password.html",
            {"request": request, "title": "تعيين كلمة مرور جديدة", "error": "رابط غير صالح.", "token": "", "session_user": request.session.get("user")},
        )

    user = db.query(User).filter(User.id == uid, User.email == email).first()
    if not user:
        return request.app.templates.TemplateResponse(
            "auth_reset_password.html",
            {"request": request, "title": "تعيين كلمة مرور جديدة", "error": "الحساب غير موجود.", "token": "", "session_user": request.session.get("user")},
        )

    user.password_hash = hash_password(password)
    db.add(user)
    db.commit()

    try:
        if 'push_notification' in globals():
            push_notification(user_id=user.id, title="تم تغيير كلمة المرور", body="تم تحديث كلمة مرور حسابك بنجاح.")
    except Exception:
        pass

    return RedirectResponse(url="/login?reset_ok=1", status_code=303)


# ============ Logout ============
@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.get("/dev/admin-login")
def dev_admin_login(request: Request, db: Session = Depends(get_db)):
    # إدخال سريع للأدمن لاختبار الجلسات (احذِفه بعد ما تخلّص)
    user = db.query(User).filter(User.email == "admin@example.com").first()
    if not user:
        return RedirectResponse("/login", status_code=303)
    user.is_verified = True
    user.status = "active"
    db.add(user); db.commit(); db.refresh(user)
    request.session["user"] = {
        "id": user.id, "email": user.email, "role": user.role,
        "is_verified": True, "status": "active"
    }
    return RedirectResponse("/", status_code=303)