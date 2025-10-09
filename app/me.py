from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User

router = APIRouter(tags=["me"], prefix="/api")

@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess or "id" not in sess:
        return JSONResponse({"ok": False, "reason": "not_logged_in"}, status_code=401)

    user = db.query(User).filter(User.id == sess["id"]).first()
    if not user:
        return JSONResponse({"ok": False, "reason": "not_found"}, status_code=404)

    return {
        "ok": True,
        "id": user.id,
        "role": user.role,
        "is_deposit_manager": bool(user.is_deposit_manager),
        "can_manage_deposits": user.can_manage_deposits,
    }