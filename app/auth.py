# app/auth.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os, secrets, shutil

from .database import get_db
from .models import User, Document
from .utils import hash_password, verify_password

router = APIRouter()

# مجلدات الرفع العامة
UPLOADS_ROOT = os.environ.get("UPLOADS_DIR", "uploads")
IDS_DIR = os.path.join(UPLOADS_ROOT, "ids")
AVATARS_DIR = os.path.join(UPLOADS_ROOT, "avatars")  # ← جديد: مجلد صور الحساب
os.makedirs(IDS_DIR, exist_ok=True)
os.makedirs(AVATARS_DIR, exist_ok=True)              # ← جديد

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
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/login?err=1", status_code=303)

    # خزّن is_verified و avatar_path ضمن السيشن (مهم لظهور الشارة والصورة)
    request.session["user"] = {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "status": user.status,
        "is_verified": bool(user.is_verified),
        "avatar_path": user.avatar_path or None,  # ← جديد
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

    # حفظ ملف بصورة آمنة
    def _save_any(fileobj, folder, allow_exts):
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
        avatar_path=avatar_path  # خزّن مسار الصورة
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    # سجل الوثيقة
    expiry = None
    if doc_expiry:
        try:
            expiry = datetime.strptime(doc_expiry, "%Y-%m-%d").date()
        except:
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

    return RedirectResponse(url="/login", status_code=303)

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
