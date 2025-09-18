# app/activate.py
import os, secrets, shutil
from datetime import datetime
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Document

router = APIRouter()

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
    تعرض حالة الحساب، الوثائق المرفوعة، وملاحظات المراجعة إن وجدت،
    مع نماذج لإعادة رفع الصورة/الوثائق، وزر مراسلة الأدمِن.
    """
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    # آخر وثيقة (إن وجدت) — أو أنشئ قائمة فارغة
    docs = user.documents or []

    # لو صار المستخدم approved بالفعل، رجّعه للصفحة الرئيسية
    if user.status == "approved":
        return RedirectResponse(url="/", status_code=303)

    # جرّب جلب ملاحظة من آخر وثيقة مرفوضة أو قيد المراجعة
    review_note = None
    if docs:
        for d in sorted(docs, key=lambda x: x.created_at or datetime.utcnow(), reverse=True):
            if d.review_note:
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
        except:
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
