# app/ratings.py
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import Rating, User

router = APIRouter()

def require_login(request: Request):
    return request.session.get("user")

@router.get("/rate/{user_id}")
def rate_get(user_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    rated = db.query(User).get(user_id)
    if not rated:
        return RedirectResponse(url="/", status_code=303)
    return request.app.templates.TemplateResponse(
        "rate.html",
        {"request": request, "title": "Rate User", "rated": rated, "session_user": u}
    )

@router.post("/rate/{user_id}")
def rate_post(user_id: int, request: Request, db: Session = Depends(get_db),
              stars: int = Form(...), comment: str = Form("")):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    rated = db.query(User).get(user_id)
    if not rated or user_id == u["id"]:
        return RedirectResponse(url="/", status_code=303)
    r = Rating(rater_id=u["id"], rated_user_id=user_id, stars=stars, comment=comment)
    db.add(r); db.commit()
    return RedirectResponse(url=f"/u/{user_id}", status_code=303)
