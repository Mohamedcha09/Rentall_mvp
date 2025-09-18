# app/disputes.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .database import get_db

router = APIRouter()

def _require_login(request: Request):
    return request.session.get("user")

@router.get("/disputes/new")
def dispute_new(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "dispute_new.html",
        {"request": request, "session_user": u, "title": "فتح نزاع"}
    )
