# app/activate.py
import os, secrets, shutil
from datetime import datetime
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Document

router = APIRouter()

# ========= مسارات الرفع =========
UPLOADS_ROOT = os.environ.get("UPLOADS_DIR", "uploads")
AVATARS_DIR = os.path.join(UPLOADS_ROOT, "avatars")
IDS_DIR = os.path.join(UPLOADS_ROOT, "ids")
os.makedirs(AVATARS_DIR, exist_ok=True)
os.makedirs(IDS_DIR, exist_ok=True)

# اسم قالب صفحة التفعيل (لدعم كلا الاسمين لديك)
TEMPLATE_NAME = os.getenv("ACTIVATE_TEMPLATE", "activete.jtml")  # بدّله إلى "activate.html" إذا أردت

# ========= إعدادات عامة =========
BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")

# ========= خدمة البريد (fallback) =========
try:
    from .emailer import send_email  # signature: (to, subject, html_body, text_body=None, ...)
except Exception:
    def send_email(to, subject, html_body, text_body=None, cc=None, bcc=None, reply_to=None):
        return False  # NO-OP إذا لم توجد الخدمة بعد

# ========= توكن تفعيل الإيميل (كما في auth.py) =========
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

SECRET_KEY = os.getenv("SECRET_KEY", "change-me")  # ضع قيمة قوية في .env
ACTIVATE_SALT = os.getenv("ACTIVATE_EMAIL_SALT", "activate-email-salt")
ACTIVATE_MAX_AGE = int(os.getenv("ACTIVATE_LINK_MAX_AGE_SECONDS", "259200"))  # 3 أيام

def _activation_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(SECRET_KEY, salt=ACTIVATE_SALT)

def _make_activation_token(user_id: int, email: str) -> str:
    data = {"uid": int(user_id), "email": (email or "").strip().lower()}
    return _activation_serializer().dumps(data)

def _verify_activation_token(token: str) -> dict | None:
    try:
        return _activation_serializer().loads(token, max_age=ACTIVATE_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None
    except Exception:
        return None

# ========= مساعدين داخليين =========
def _save(fileobj: UploadFile, folder: str, allow_exts):
    if not fileobj:
        return None
    ext = os.path.splitext(fileobj.filename or "")[1].lower()
    if ext not in allow_exts:
        return None
    fname = f"{secrets.token_hex(12)}{ext}"
    fpath = os.path.join(folder, fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(fileobj.file, f)
    return fpath.replace("\\", "/")

def _require_login(request: Request):
    return request.session.get("user")

# ========= صفحة التفعيل =========
@router.get("/activate")
def activate_get(request: Request, db: Session = Depends(get_db)):
    """
    صفحة إكمال التفعيل للمستخدمين pending/rejected.
    تعرض حالة الحساب، الوثائق، وملاحظات المراجعة إن وجدت،
    مع نماذج لإعادة رفع الصورة/الوثائق، وزر مراسلة الأدمِن.
    """
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    # اجلب أحدث وثائق من قاعدة البيانات (أفضل من user.documents إن كان lazy)
    try:
        docs = (
            db.query(Document)
            .filter(Document.user_id == user.id)
            .order_by(Document.created_at.desc().nullslast())
            .all()
        )
    except Exception:
        docs = []

    # لو صار المستخدم approved بالفعل، رجّعه للصفحة الرئيسية
    if user.status == "approved":
        return RedirectResponse(url="/", status_code=303)

    # ملاحظة المراجعة (إن وجدت)
    review_note = None
    for d in docs:
        if getattr(d, "review_note", None):
            review_note = d.review_note
            break

    return request.app.templates.TemplateResponse(
        TEMPLATE_NAME,
        {
            "request": request,
            "title": "إكمال التفعيل",
            "user": user,
            "docs": docs,
            "review_note": review_note,
            "session_user": sess
        }
    )

# ========= إعادة رفع صورة الحساب =========
@router.post("/activate/avatar")
def activate_update_avatar(
    request: Request,
    db: Session = Depends(get_db),
    avatar: UploadFile = File(...),
):
    """
    إعادة التقاط/رفع صورة الحساب (كاميرا فقط من الواجهة).
    تُحدَّث الصورة وتبقى الحالة كما هي (pending/rejected) إلى أن يراجع الأدمِن.
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

# ========= إعادة رفع الوثائق =========
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

# ========= تأكيد الإيميل بالتوكن =========
@router.get("/activate/confirm")
def activate_confirm(request: Request, token: str, db: Session = Depends(get_db)):
    """
    يقرأ التوكن الموقّع ويؤكد البريد:
      - يضبط is_verified=True و email_verified_at (إن وُجدا)
      - لا يغيّر موافقة الأدمِن (status يبقى كما هو)
      - يحدّث session_user لعرض الشارة فورًا
    """
    data = _verify_activation_token(token)
    if not data:
        return RedirectResponse(url="/activate?err=token", status_code=303)

    u = db.query(User).get(int(data.get("uid", 0)))
    if not u:
        return RedirectResponse(url="/activate?err=user", status_code=303)

    if (u.email or "").strip().lower() != (data.get("email") or "").strip().lower():
        return RedirectResponse(url="/activate?err=mismatch", status_code=303)

    try:
        if hasattr(u, "is_verified"):
            u.is_verified = True
        if hasattr(u, "email_verified_at"):
            setattr(u, "email_verified_at", datetime.utcnow())
        db.add(u); db.commit()
    except Exception:
        pass

    # عدّل السيشن لإظهار الشارة مباشرة
    try:
        sess = request.session.get("user") or {}
        if sess.get("id") == u.id:
            sess["is_verified"] = True
            request.session["user"] = sess
    except Exception:
        pass

    return RedirectResponse(url="/activate?ok=1", status_code=303)

# ========= إعادة إرسال رابط التفعيل =========
@router.post("/activate/resend")
def activate_resend(request: Request, db: Session = Depends(get_db)):
    """
    يعيد إرسال رابط التفعيل للمستخدم الحالي (من السيشن).
    """
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(sess["id"])
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    try:
        token = _make_activation_token(u.id, u.email)
        link = f"{BASE_URL}/activate/confirm?token={token}"
        send_email(
            u.email,
            "Activate your account — RentAll",
            f"<p>مرحبًا {(u.first_name or 'صديقنا')}،</p>"
            f"<p>هذا رابط تفعيل بريدك (صالح 72 ساعة):</p>"
            f"<p><a href='{link}'>{link}</a></p>",
            text_body=f"Activate link: {link}"
        )
    except Exception:
        pass

    return RedirectResponse(url="/activate?resent=1", status_code=303)