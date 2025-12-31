# app/platform_wallet.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text

# جدول: platform_balance (صف واحد فقط)
# جدول: platform_ledger (سجل العمليات)


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


def get_balance_row_locked(db: Session) -> dict:
    """
    يرجّع صف الرصيد مع قفل FOR UPDATE (مهم ضد التزامن).
    """
    row = db.execute(
        text("""
            SELECT id, available_amount, hold_amount
            FROM platform_balance
            ORDER BY id ASC
            LIMIT 1
            FOR UPDATE
        """)
    ).mappings().first()

    if not row:
        # لو ما فيه صف، ننشئ واحد
        db.execute(text("INSERT INTO platform_balance (available_amount, hold_amount) VALUES (0,0)"))
        row = db.execute(
            text("""
                SELECT id, available_amount, hold_amount
                FROM platform_balance
                ORDER BY id ASC
                LIMIT 1
                FOR UPDATE
            """)
        ).mappings().first()

    return dict(row)


def ledger_add(
    db: Session,
    type: str,
    amount,
    direction: str,
    source: str,
    booking_id: Optional[int] = None,
    note: Optional[str] = None,
):
    db.execute(
        text("""
            INSERT INTO platform_ledger (type, amount, direction, source, booking_id, note)
            VALUES (:type, :amount, :direction, :source, :booking_id, :note)
        """),
        {
            "type": type,
            "amount": float(_dec(amount)),
            "direction": direction,
            "source": source,
            "booking_id": booking_id,
            "note": note,
        },
    )


def add_hold(db: Session, amount, source="paypal", booking_id: Optional[int] = None, note: str = ""):
    """
    عند دخول ديبو للمنصّة كـ HOLD
    hold += amount
    """
    amt = _dec(amount)
    if amt <= 0:
        return

    bal = get_balance_row_locked(db)
    new_hold = _dec(bal["hold_amount"]) + amt

    db.execute(
        text("UPDATE platform_balance SET hold_amount=:h, updated_at=NOW() WHERE id=:id"),
        {"h": float(new_hold), "id": bal["id"]},
    )
    ledger_add(db, "deposit_hold_in", amt, "in", source, booking_id, note)


def hold_to_available(db: Session, amount, source="paypal", booking_id: Optional[int] = None, note: str = ""):
    """
    لما يصير الـ HOLD “valid / available”
    hold -= amount
    available += amount
    """
    amt = _dec(amount)
    if amt <= 0:
        return

    bal = get_balance_row_locked(db)
    hold = _dec(bal["hold_amount"])
    avail = _dec(bal["available_amount"])

    if hold < amt:
        # ما نكسر السيستم، نخليها صفر ونكمل (لكن نسجل)
        amt = hold

    new_hold = hold - amt
    new_avail = avail + amt

    db.execute(
        text("""
            UPDATE platform_balance
            SET hold_amount=:h, available_amount=:a, updated_at=NOW()
            WHERE id=:id
        """),
        {"h": float(new_hold), "a": float(new_avail), "id": bal["id"]},
    )
    ledger_add(db, "hold_to_available", amt, "in", source, booking_id, note)


def spend_available(db: Session, amount, source="robot", booking_id: Optional[int] = None, note: str = ""):
    """
    عند خروج فلوس من رصيد المنصّة (Refund / payout etc)
    available -= amount
    """
    amt = _dec(amount)
    if amt <= 0:
        return

    bal = get_balance_row_locked(db)
    avail = _dec(bal["available_amount"])
    if avail < amt:
        raise ValueError(f"Not enough platform available balance. Have={avail}, need={amt}")

    new_avail = avail - amt
    db.execute(
        text("UPDATE platform_balance SET available_amount=:a, updated_at=NOW() WHERE id=:id"),
        {"a": float(new_avail), "id": bal["id"]},
    )
    ledger_add(db, "platform_spend", amt, "out", source, booking_id, note)


def refund_revert(db: Session, amount, source="system", booking_id: Optional[int] = None, note: str = ""):
    """
    لو خصمنا ثم فشل PayPal، نرجع المبلغ للـ available
    """
    amt = _dec(amount)
    if amt <= 0:
        return

    bal = get_balance_row_locked(db)
    avail = _dec(bal["available_amount"])
    new_avail = avail + amt

    db.execute(
        text("UPDATE platform_balance SET available_amount=:a, updated_at=NOW() WHERE id=:id"),
        {"a": float(new_avail), "id": bal["id"]},
    )
    ledger_add(db, "refund_revert", amt, "in", source, booking_id, note)
