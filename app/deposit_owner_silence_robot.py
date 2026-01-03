# =====================================================
# deposit_owner_silence_robot.py
# =====================================================
"""
Robot #1 — Owner Silence (After Return)
======================================

FINAL VERSION — WALLET BASED (NO PAYPAL REFUND)

Behavior:
- Item returned OR return marked no problem
- Wait WINDOW_DELTA
- If NO owner dispute opened during window → auto refund FULL deposit
- Refund is sent from Sevor Wallet (PAYOUT), NOT PayPal refund
- If wallet balance insufficient → SKIP (retry later)
- NEVER interfere with MD / Robot #3 flow
- NO CRASH, NO DB CORRUPTION
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import SessionLocal
from app.models import (
    Booking,
    DepositAuditLog,
    User,
    PlatformWallet,
    PlatformWalletLedger,
)
from app.notifications_api import push_notification
from decimal import Decimal

# =====================================================
# ⏱️ WINDOW (TEST = 1 MINUTE, PROD = 24H)
# =====================================================
WINDOW_DELTA = timedelta(minutes=1)   # change to hours=24 in prod
NOW = lambda: datetime.now(timezone.utc)
# =====================================================


def get_system_actor_id(db: Session) -> int:
    admin = (
        db.query(User)
        .filter(User.role == "admin")
        .order_by(User.id.asc())
        .first()
    )
    if not admin:
        raise RuntimeError("No admin user found")
    return admin.id


# =====================================================
# 🔍 FIND ELIGIBLE BOOKINGS
# =====================================================
def find_candidates(db: Session) -> List[Booking]:
    deadline = NOW() - WINDOW_DELTA

    return (
        db.query(Booking)
        .filter(
            # ---- deposit exists and not refunded
            Booking.deposit_amount > 0,
            Booking.deposit_refund_sent == False,

            # ---- item returned
            or_(
                Booking.returned_at.isnot(None),
                and_(
                    Booking.return_check_no_problem == True,
                    Booking.return_check_submitted_at.isnot(None),
                ),
            ),

            # ---- 🚫 NO OWNER DISPUTE
            Booking.owner_dispute_opened_at.is_(None),

            # ---- 🔒 NEVER TOUCH MD FLOW
            or_(
                Booking.dm_decision_amount.is_(None),
                Booking.dm_decision_amount == 0,
            ),
            Booking.renter_24h_window_opened_at.is_(None),

            # ---- ⏱️ window expired
            or_(
                Booking.returned_at <= deadline,
                Booking.return_check_submitted_at <= deadline,
            ),

            # ---- payment done
            Booking.payment_method == "paypal",
        )
        .all()
    )


# =====================================================
# 💰 COMPUTE REFUND
# =====================================================
def compute_refund_amount(bk: Booking) -> Decimal:
    try:
        return Decimal(bk.deposit_amount or 0)
    except Exception:
        return Decimal("0.00")


# =====================================================
# ⚙️ EXECUTE ONE BOOKING
# =====================================================
def execute_one(db: Session, bk: Booking) -> Optional[str]:
    refund_amount = compute_refund_amount(bk)
    if refund_amount <= 0:
        return None

    currency = bk.currency or "CAD"

    # 🔒 Lock wallet row
    wallet = (
        db.query(PlatformWallet)
        .filter(PlatformWallet.currency == currency)
        .with_for_update()
        .first()
    )

    if not wallet:
        print(f"⏭️ Skip booking #{bk.id} (wallet not found)")
        return None

    # ❌ Not enough balance → wait
    if wallet.available_balance < refund_amount:
        print(
            f"⏳ Wallet insufficient for booking #{bk.id} "
            f"({wallet.available_balance} < {refund_amount})"
        )
        bk.deposit_waiting_wallet = True
        bk.deposit_wallet_checked_at = NOW()
        db.commit()
        return None

    # ✅ Wallet OK → execute payout (logical)
    wallet.available_balance -= refund_amount

    db.add(
        PlatformWalletLedger(
            wallet_id=wallet.id,
            booking_id=bk.id,
            type="deposit_out",
            amount=refund_amount,
            currency=currency,
            direction="out",
            source="robot",
            note="Auto refund — owner silence",
        )
    )

    now = NOW()
    bk.deposit_refund_sent = True
    bk.deposit_refund_sent_at = now
    bk.deposit_refund_amount = refund_amount
    bk.deposit_status = "refunded"
    bk.deposit_case_closed = True
    bk.auto_finalized_by_robot = True
    bk.deposit_waiting_wallet = False
    bk.status = "closed"

    db.add(
        DepositAuditLog(
            booking_id=bk.id,
            actor_id=get_system_actor_id(db),
            actor_role="system",
            action="auto_refund_wallet_owner_silence",
            amount=refund_amount,
            reason="Owner did not open dispute within allowed window",
            details=f"wallet_currency={currency}",
        )
    )

    db.commit()
    return "wallet_payout_sent"


# =====================================================
# ▶️ RUN ONCE
# =====================================================
def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)
        print(f"Robot #1 candidates: {len(items)}")
        for bk in items:
            execute_one(db, bk)
    finally:
        db.close()


if __name__ == "__main__":
    run_once()
