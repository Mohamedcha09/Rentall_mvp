# app/routes_debug_cloudinary.py
from __future__ import annotations
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
import cloudinary
import cloudinary.uploader
from datetime import datetime
import base64

router = APIRouter(tags=["debug-cloudinary"])

@router.get("/debug/cloudinary", response_class=JSONResponse)
def cloudinary_info():
    cfg = cloudinary.config(secure=True)
    # لا نُرجع الأسرار؛ فقط معلومات عامة للتأكد من التحميل
    return {
        "cloud_name": cfg.cloud_name,
        "api_key_present": bool(cfg.api_key),
        "secure": True,
        "folder_hint": "debug/"
    }

@router.get("/debug/cloudinary/form", response_class=HTMLResponse)
def cloudinary_form():
    # صفحة HTML صغيرة للرفع من المتصفح مباشرة
    return """
    <html><body>
      <h3>رفع اختبار إلى Cloudinary</h3>
      <form action="/debug/cloudinary/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file" accept="image/*,video/*" required />
        <button type="submit">رفع</button>
      </form>
      <p>أو جرّب توليد صورة 1x1 (بدون ملف): <a href="/debug/cloudinary/generate">/debug/cloudinary/generate</a></p>
    </body></html>
    """

@router.post("/debug/cloudinary/upload")
async def cloudinary_upload(file: UploadFile = File(...)):
    # نرفع أي ملف (صورة/فيديو) مباشرة إلى كلوديناري
    content = await file.read()
    public_id = f"debug/{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    up = cloudinary.uploader.upload(
        content,
        public_id=public_id,
        resource_type="auto",   # يدعم صور/فيديو تلقائيًا
        folder="debug"
    )
    return {
        "ok": True,
        "public_id": up.get("public_id"),
        "resource_type": up.get("resource_type"),
        "format": up.get("format"),
        "bytes": up.get("bytes"),
        "secure_url": up.get("secure_url"),
        "thumbnail": up.get("thumbnail_url") or up.get("secure_url"),
    }

@router.get("/debug/cloudinary/generate")
def cloudinary_generate():
    # نرفع صورة PNG شفافة 1x1 من داخل الكود (بدون إنترنت وبدون ملف خارجي)
    # data URI لصورة 1x1
    data_uri = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAF"
        "9gJ/0h3JXQAAAABJRU5ErkJggg=="
    )
    public_id = f"debug/generated_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    up = cloudinary.uploader.upload(
        data_uri,
        public_id=public_id,
        resource_type="image",
        folder="debug"
    )
    return {
        "ok": True,
        "public_id": up.get("public_id"),
        "secure_url": up.get("secure_url"),
        "width": up.get("width"),
        "height": up.get("height"),
        "bytes": up.get("bytes"),
    }
