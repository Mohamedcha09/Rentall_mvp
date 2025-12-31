from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import PlatformBalance, PlatformLedger, User

router = APIRouter(prefix="/admin/wallet", tags=["admin-wallet"])


# ===== helpers =====
def get_current_user(request: Request, db: Session) -> User | None:
    sess = request.session.get("user")
    if not sess:
        return None
    return db.get(User, sess.get("id"))


def require_admin(user: User | None):
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


# =========================
# GET – Wallet page
# =========================
@router.get("", response_class=HTMLResponse)
def wallet_page(
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    balance = db.query(PlatformBalance).first()

    ledger = (
        db.query(PlatformLedger)
        .order_by(PlatformLedger.created_at.desc())
        .limit(50)
        .all()
    )

    return HTMLResponse(
        content=request.app.state.templates.get_template(
            "wallet.html"
        ).render(
            request=request,
            user=user,
            balance=balance,
            ledger=ledger,
        )
    )


# =========================
# POST – Manual top-up
# =========================
@router.post("/topup")
def wallet_topup(
    request: Request,
    amount: float = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    balance = db.query(PlatformBalance).first()
    balance.available_amount += amount

    db.add(
        PlatformLedger(
            type="manual_topup",
            amount=amount,
            direction="in",
            source="admin",
            note=note,
        )
    )

    db.commit()
    return RedirectResponse("/admin/wallet", status_code=303)
