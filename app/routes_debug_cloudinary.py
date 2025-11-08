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
    # We do not return secrets; only general information to verify upload
    return {
        "cloud_name": cfg.cloud_name,
        "api_key_present": bool(cfg.api_key),
        "secure": True,
        "folder_hint": "debug/"
    }

@router.get("/debug/cloudinary/form", response_class=HTMLResponse)
def cloudinary_form():
    # Small HTML page to upload directly from the browser
    return """
    <html><body>
      <h3>Test Upload to Cloudinary</h3>
      <form action="/debug/cloudinary/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file" accept="image/*,video/*" required />
        <button type="submit">Upload</button>
      </form>
      <p>Or try generating a 1x1 image (without a file): <a href="/debug/cloudinary/generate">/debug/cloudinary/generate</a></p>
    </body></html>
    """

@router.post("/debug/cloudinary/upload")
async def cloudinary_upload(file: UploadFile = File(...)):
    # Upload any file (image/video) directly to Cloudinary
    content = await file.read()
    public_id = f"debug/{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    up = cloudinary.uploader.upload(
        content,
        public_id=public_id,
        resource_type="auto",   # Automatically supports images/videos
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
    # Upload a transparent 1x1 PNG image from code (without internet or external file)
    # data URI for a 1x1 image
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
