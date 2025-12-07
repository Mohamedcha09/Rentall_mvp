# app/auth.py

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from urllib.parse import urlencode
import os, secrets, shutil

from .database import get_db
from .models import User, Document
from .utils import hash_password, verify_password, MAX_FORM_PASSWORD_CHARS
from cloudinary.uploader import upload as cloud_upload
# (Optional) Internal notifications
try:
    from .notifications_api import push_notification  # noqa: F401
except Exception:
    pass

# ======= Email System =======
from .email_service import send_email

# ===== Signed links =====
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# ==== Environment / base links ====
SITE_URL = (os.getenv("SITE_URL") or "").rstrip("/")
BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

router = APIRouter()

# Unify upload folders with main.py (at project root level)
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOADS_ROOT = os.environ.get("UPLOADS_DIR", os.path.join(APP_ROOT, "uploads"))
IDS_DIR = os.path.join(UPLOADS_ROOT, "ids")
AVATARS_DIR = os.path.join(UPLOADS_ROOT, "avatars")
os.makedirs(IDS_DIR, exist_ok=True)
os.makedirs(AVATARS_DIR, exist_ok=True)

# ===== helpers =====
def _normalize_form_password(pwd: str) -> str:
    """Simple trim for password input to avoid extremely large passwords."""
    if pwd is None:
        return ""
    return pwd[:MAX_FORM_PASSWORD_CHARS]

def _save_any(fileobj: UploadFile | None, folder: str, allow_exts: list[str]) -> str | None:
    """Upload file to Cloudinary instead of local storage."""
    if not fileobj:
        return None

    ext = os.path.splitext(fileobj.filename or "")[1].lower()
    if ext not in allow_exts:
        return None

    try:
        result = cloud_upload(
            fileobj.file,
            folder="sevor/uploads",
            overwrite=True,
            resource_type="image"
        )
        return result.get("secure_url")
    except Exception as e:
        print("Cloudinary upload failed:", e)
        return None

def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=SECRET_KEY, salt="email-verify-v1")

def _pwd_signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=SECRET_KEY, salt="pwd-reset-v1")

def _maybe_redirect_canonical(request: Request) -> RedirectResponse | None:
    """
    If SITE_URL is set and differs from the current domain, redirect to the same path on the primary domain.
    """
    try:
        if not SITE_URL:
            return None
        # If same host, do nothing
        current_host = request.url.hostname or ""
        target_host = SITE_URL.replace("https://", "").replace("http://", "").split("/")[0]
        if current_host == target_host:
            return None
        # Build redirect link with same path and query
        path = request.url.path
        query = request.url.query or ""
        redirect_to = f"{SITE_URL}{path}"
        if query:
            redirect_to += f"?{query}"
        return RedirectResponse(url=redirect_to, status_code=308)
    except Exception:
        return None

# ============ Login ============
@router.get("/login")
def login_get(request: Request):
    # Redirect to primary domain if needed
    r = _maybe_redirect_canonical(request)
    if r:
        return r
    return request.app.templates.TemplateResponse(
        "auth_login.html",
        {"request": request, "title": "Login", "session_user": request.session.get("user")}
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

    # ✅ Admin: always fully enabled
    role = str(getattr(user, "role", "") or "").lower()
    if role == "admin":
        changed = False
        if not bool(getattr(user, "is_verified", False)):
            user.is_verified = True
            try:
                user.verified_at = datetime.utcnow()
            except Exception:
                pass
            changed = True
        # State consistency
        if (getattr(user, "status", "pending") or "").lower() not in ("active", "approved"):
            # Choose "active" as login state
            user.status = "active"
            changed = True
        # (Optional) make them a deposit manager automatically if the field exists
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
        # 🧱 Regular user: requires email verification
        if not bool(getattr(user, "is_verified", False)):
            # Redirect to verify-email page with email passed through
            query = urlencode({"email": email})
            return RedirectResponse(url=f"/verify-email?{query}", status_code=303)

    # ✅ Create session and log in
       # ✅ Create session and log in
    request.session["user"] = {
        "id": user.id,
        "first_name": getattr(user, "first_name", ""),
        "last_name": getattr(user, "last_name", ""),
        "email": user.email,
        "phone": getattr(user, "phone", ""),
        "role": user.role,
        "status": getattr(user, "status", "active"),
        "is_verified": bool(getattr(user, "is_verified", False)),
        "avatar_path": getattr(user, "avatar_path", None) or None,
        # Extra flags
        "is_deposit_manager": bool(getattr(user, "is_deposit_manager", False)),
        "is_mod": bool(getattr(user, "is_mod", False)),   # ✅ Important for showing “Reports”
    }

    # If SITE_URL is set and you logged in from a different domain, send back to primary domain
    r = _maybe_redirect_canonical(request)
    if r:
        return r
    return RedirectResponse(url="/", status_code=303)

# ============ Register ============
@router.get("/register")
def register_get(request: Request):
    r = _maybe_redirect_canonical(request)
    if r:
        return r
    return request.app.templates.TemplateResponse(
        "auth_register.html",
        {"request": request, "title": "Register", "session_user": request.session.get("user")}
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

    # Check if user exists
    exists = db.query(User).filter(User.email == email).first()
    if exists:
        return request.app.templates.TemplateResponse(
            "auth_register.html",
            {
                "request": request,
                "title": "Register",
                "message": "This email is already in use.",
                "session_user": request.session.get("user"),
            },
        )

    # Save documents
    front_path = _save_any(doc_front, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"])
    back_path = _save_any(doc_back, IDS_DIR, [".jpg", ".jpeg", ".png", ".pdf"]) if doc_back else None
    avatar_path = _save_any(avatar, AVATARS_DIR, [".jpg", ".jpeg", ".png", ".webp"])
    if not avatar_path:
        return request.app.templates.TemplateResponse(
            "auth_register.html",
            {
                "request": request,
                "title": "Register",
                "message": "Profile image is required and must be an image (JPG/PNG/WebP).",
                "session_user": request.session.get("user"),
            },
        )

    # Create user
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

    # Record document
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

    # ===== Send activation email =====
    try:
        s = _signer()
        token = s.dumps({"uid": u.id, "email": u.email})
        verify_url = f"{BASE_URL}/activate/verify?token={token}"
        year = datetime.utcnow().year
        subj = "Activate your account — RentAll"

        html = f"""<!doctype html>
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Account activation</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;color:#eaf0ff;font-family:Arial,'Segoe UI',Tahoma,sans-serif;direction:ltr;">
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
              <h2 style="margin:0 0 10px 0;font-weight:800;font-size:22px;line-height:1.4;color:#eaf0ff;">Hello {first_name} 👋</h2>
              <p style="margin:0 0 16px 0;font-size:15px;line-height:1.8;color:#cdd7ee;">
                Thanks for signing up to <b>RentAll</b>. To secure your account and get started, click the button below to verify your email:
              </p>
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:18px auto;">
                <tr>
                  <td align="center" bgcolor="#2563eb" style="border-radius:12px;">
                    <a href="{verify_url}" target="_blank"
                       style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;
                              font-weight:700;font-size:18px;line-height:48px;border-radius:12px;
                              padding:0 26px;min-width:200px;text-align:center;cursor:pointer;">
                      Activate account
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:22px 0 6px 0;font-size:14px;color:#93a4c9;">If the button doesn’t work, copy and open this link:</p>
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

        text = f"Hello {first_name}\n\nActivate your account using the link:\n{verify_url}\n\nIf this wasn’t you, please ignore this message."
        send_email(u.email, subj, html, text_body=text)
    except Exception:
        pass

    # ✅ Send to email verification page
    return RedirectResponse(url=f"/verify-email?email={u.email}&sent=1", status_code=303)

# ============ Email Verify Wall ============
@router.get("/verify-email")
def verify_email_page(request: Request, email: str = "", db: Session = Depends(get_db)):
    """
    If the email in the query belongs to an admin or is verified -> redirect to home even without a session.
    Otherwise show the verification page.
    """
    r = _maybe_redirect_canonical(request)
    if r:
        return r

    u = request.session.get("user") or {}
    role = str((u or {}).get("role") or "").lower()
    isv  = bool((u or {}).get("is_verified"))

    # If there is a session and it’s verified/admin -> to homepage
    if role == "admin" or isv:
        return RedirectResponse("/", status_code=303)

    # If an email is provided via query and it appears verified/admin in DB -> redirect home
    em = (email or "").strip().lower()
    if em:
        user = db.query(User).filter(User.email == em).first()
        if user:
            db_role = str(getattr(user, "role", "") or "").lower()
            db_isv  = bool(getattr(user, "is_verified", False))
            if db_role == "admin" or db_isv:
                return RedirectResponse("/", status_code=303)

    # Other cases: show the page
    return request.app.templates.TemplateResponse(
        "verify_email.html",
        {"request": request, "title": "Verify your email", "email": em, "session_user": u or None},
    )

# ============ Activate account via link ============
@router.get("/activate/verify")
def verify_from_email(request: Request, token: str = "", db: Session = Depends(get_db)):
    """
    Decode the token and activate the account immediately: is_verified=True and status=active
    then redirect to homepage.
    """
    r = _maybe_redirect_canonical(request)
    if r:
        return r

    if not token:
        return RedirectResponse(url="/verify-email", status_code=303)
    try:
        data = _signer().loads(token, max_age=48 * 3600)  # 48 hours validity
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
        try:
            user.verified_at = datetime.utcnow()
        except Exception:
            pass
    if (getattr(user, "status", "pending") or "").lower() != "active":
        user.status = "active"
    db.add(user)
    db.commit()
    db.refresh(user)

    # Log the session directly
    request.session["user"] = {
        "id": user.id,
        "first_name": getattr(user, "first_name", ""),
        "last_name": getattr(user, "last_name", ""),
        "email": user.email,
        "phone": getattr(user, "phone", ""),
        "role": user.role,
        "status": getattr(user, "status", "active"),
        "is_verified": True,
        "avatar_path": getattr(user, "avatar_path", None) or None,
        "is_deposit_manager": bool(getattr(user, "is_deposit_manager", False)),
        "is_mod": bool(getattr(user, "is_mod", False)),   # ✅
    }
    return RedirectResponse("/", status_code=303)

# ============ Password Reset ============
@router.get("/forgot")
def forgot_get(request: Request):
    r = _maybe_redirect_canonical(request)
    if r:
        return r
    return request.app.templates.TemplateResponse(
        "auth_forgot.html",
        {"request": request, "title": "Reset password", "session_user": request.session.get("user")}
    )

@router.post("/forgot")
def forgot_post(request: Request, db: Session = Depends(get_db), email: str = Form(...)):
    email = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()

    # Always show the same message
    msg = "If a matching account exists, we'll send a password reset link to your email."

    try:
        if user:
            s = _pwd_signer()
            token = s.dumps({"uid": user.id, "email": user.email})
            reset_url = f"{BASE_URL}/reset-password?token={token}"
            year = datetime.utcnow().year
            subj = "Reset your password — RentAll"

            html = f"""<!doctype html>
<html lang="en" dir="ltr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Password reset</title></head>
<body style="margin:0;padding:0;background:#0f172a;color:#eaf0ff;font-family:Arial,'Segoe UI',Tahoma,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#0f172a;">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;background:#111827;border:1px solid #223049;border-radius:16px;overflow:hidden;">
        <tr>
          <td style="padding:20px 22px;background:#0f172a;border-bottom:1px solid #223049;">
            <span style="display:inline-block;background:rgba(124,92,255,.15);border:1px solid rgba(124,92,255,.35);color:#d8cfff;padding:6px 10px;border-radius:999px;font-size:13px;">Password reset</span>
          </td>
        </tr>
        <tr><td style="padding:22px;">
          <p style="margin:0 0 10px 0;color:#cdd7ee">A password reset was requested for your <b>RentAll</b> account.</p>
          <p style="margin:0 0 14px 0;color:#cdd7ee">Click the button below and enter a new password:</p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:18px auto;">
            <tr><td bgcolor="#7c5cff" style="border-radius:12px;">
              <a href="{reset_url}" target="_blank"
                 style="display:inline-block;background:#7c5cff;color:#ffffff;text-decoration:none;font-weight:700;
                        font-size:18px;line-height:48px;border-radius:12px;padding:0 26px;min-width:220px;text-align:center;">
                Reset now
              </a>
            </td></tr>
          </table>
          <p style="margin:18px 0 6px 0;font-size:14px;color:#93a4c9;">If the button doesn't work, use this link:</p>
          <p dir="ltr" style="margin:0 0 10px 0;word-break:break-all;">
            <a href="{reset_url}" style="color:#bda7ff;text-decoration:underline" target="_blank">{reset_url}</a>
          </p>
          <p style="margin:12px 0 0 0;font-size:12px;color:#7f8db0;">This link expires in two hours.</p>
        </td></tr>
        <tr><td style="padding:14px 22px;background:#0b1220;color:#94a3b8;font-size:11px;text-align:center;">©️ {year} RentAll</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

            text = f"Password reset:\n{reset_url}\n(The link is valid for two hours)"
            send_email(user.email, subj, html, text_body=text)
    except Exception:
        pass

    return request.app.templates.TemplateResponse(
        "auth_forgot.html",
        {"request": request, "title": "Reset password", "info": msg, "session_user": request.session.get("user")}
    )

# 3) New password entry page (via link)
@router.get("/reset-password")
def reset_get(request: Request, token: str = ""):
    r = _maybe_redirect_canonical(request)
    if r:
        return r
    if not token:
        return RedirectResponse(url="/forgot", status_code=303)
    return request.app.templates.TemplateResponse(
        "auth_reset_password.html",
        {"request": request, "title": "Set a new password", "token": token, "session_user": request.session.get("user")}
    )

# 4) Save the new password
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
                "title": "Set a new password",
                "token": token,
                "error": "Passwords do not match.",
                "session_user": request.session.get("user"),
            },
        )

    # Verify/unsign — two-hour validity
    try:
        data = _pwd_signer().loads(token, max_age=2*60*60)
        uid = int(data.get("uid", 0))
        email = (data.get("email") or "").strip().lower()
    except SignatureExpired:
        return request.app.templates.TemplateResponse(
            "auth_reset_password.html",
            {"request": request, "title": "Set a new password", "error": "The link has expired. Request a new link.", "token": "", "session_user": request.session.get("user")},
        )
    except BadSignature:
        return request.app.templates.TemplateResponse(
            "auth_reset_password.html",
            {"request": request, "title": "Set a new password", "error": "Invalid link.", "token": "", "session_user": request.session.get("user")},
        )

    user = db.query(User).filter(User.id == uid, User.email == email).first()
    if not user:
        return request.app.templates.TemplateResponse(
            "auth_reset_password.html",
            {"request": request, "title": "Set a new password", "error": "Account not found.", "token": "", "session_user": request.session.get("user")},
        )

    user.password_hash = hash_password(password)
    db.add(user)
    db.commit()

    try:
        if 'push_notification' in globals():
            push_notification(user_id=user.id, title="Password changed", body="Your account password has been updated successfully.")
    except Exception:
        pass

    return RedirectResponse(url="/login?reset_ok=1", status_code=303)

# ============ Logout ============
# At the end of the logout function in app/auth.py
SESSION_COOKIE = os.getenv("SESSION_COOKIE", "session")

@router.get("/logout")
def logout(request: Request):
    # Clear session
    request.session.clear()

    # Prepare redirect with success message
    resp = RedirectResponse(url="/?logged_out=1", status_code=303)

    # Delete session cookie locally
    try:
        resp.delete_cookie(SESSION_COOKIE)
        # Also try deleting it on the parent domain if you use one
        host = request.url.hostname or ""
        if "." in host:
            root_domain = "." + ".".join(host.split(".")[-2:])
            resp.delete_cookie(SESSION_COOKIE, domain=root_domain)
    except Exception:
        pass

    return resp

@router.get("/dev/admin-login")
def dev_admin_login(request: Request, db: Session = Depends(get_db)):
    # Quick admin sign-in to test sessions (remove it once you’re done)
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
    r = _maybe_redirect_canonical(request)
    if r:
        return r
    return RedirectResponse("/", status_code=303)





@router.get("/settings")
def settings_get(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse("/login", status_code=303)
    u = db.query(User).filter(User.id == sess["id"]).first()
    return request.app.templates.TemplateResponse(
        "settings.html",
        {"request": request, "title": "Settings", "u": u, "session_user": sess}
    )

@router.post("/settings/profile")
def settings_profile_post(
    request: Request,
    db: Session = Depends(get_db),
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(""),
    avatar: UploadFile = File(None),
):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse("/login", status_code=303)

    u = db.query(User).filter(User.id == sess["id"]).first()
    if not u:
        raise HTTPException(404, "User not found")

    # Update data
    u.first_name = (first_name or "").strip()
    u.last_name  = (last_name or "").strip()
    new_email    = (email or "").strip().lower()

    # Check email duplication if changed
    if new_email and new_email != u.email:
        exists = db.query(User).filter(User.email == new_email).first()
        if exists:
            return RedirectResponse("/settings?err=email_used", status_code=303)
        u.email = new_email
        # (Optional) make them unverified until they confirm the new email
        try:
            u.is_verified = False
        except Exception:
            pass

    # New image
    if avatar:
        saved = _save_any(avatar, AVATARS_DIR, [".jpg", ".jpeg", ".png", ".webp"])
        if saved:
            u.avatar_path = saved

    db.add(u); db.commit(); db.refresh(u)

    # Sync session
    request.session["user"] = {
        **sess,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "email": u.email,
        "avatar_path": getattr(u, "avatar_path", None) or None,
        "is_verified": bool(getattr(u, "is_verified", False)),
    }
    return RedirectResponse("/settings?saved=1", status_code=303)

@router.post("/settings/password")
def settings_password_post(
    request: Request,
    db: Session = Depends(get_db),
    current: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse("/login", status_code=303)
    u = db.query(User).filter(User.id == sess["id"]).first()
    if not u:
        raise HTTPException(404, "User not found")

    current = _normalize_form_password(current or "")
    password = _normalize_form_password(password or "")
    confirm  = _normalize_form_password(confirm or "")

    if not verify_password(current, u.password_hash):
        return RedirectResponse("/settings?err=bad_current", status_code=303)
    if not password or password != confirm:
        return RedirectResponse("/settings?err=mismatch", status_code=303)

    u.password_hash = hash_password(password)
    db.add(u); db.commit()

    return RedirectResponse("/settings?pwd_ok=1", status_code=303)


# ============ Current User Dependency ============

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Reads the user from session cookie.
    Returns the full User object or None.
    """
    sess = request.session.get("user")
    if not sess:
        return None

    uid = sess.get("id")
    if not uid:
        return None

    u = db.query(User).filter(User.id == uid).first()
    return u
