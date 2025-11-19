# app/utils_fx.py
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from .models import FxRate


# -------------------------------------------------
# 1) Get latest FX rate between any two currencies
# -------------------------------------------------
def get_rate(db: Session, base: str, quote: str) -> float:
    """
    Returns latest available FX rate base→quote.
    Example: get_rate(db, "EUR", "USD") → 1.078
    """

    base = base.upper()
    quote = quote.upper()

    if base == quote:
        return 1.0

    row = (
        db.query(FxRate)
        .filter(FxRate.base == base, FxRate.quote == quote)
        .order_by(FxRate.effective_date.desc())
        .first()
    )

    if not row:
        # No direct rate → try reverse
        reverse = (
            db.query(FxRate)
            .filter(FxRate.base == quote, FxRate.quote == base)
            .order_by(FxRate.effective_date.desc())
            .first()
        )
        if reverse:
            try:
                return 1 / float(reverse.rate)
            except Exception:
                return 1.0  # fallback safe

        # No rate at all
        return 1.0

    try:
        return float(row.rate)
    except Exception:
        return 1.0


# -------------------------------------------------
# 2) Convert amount from currency A → B
# -------------------------------------------------
def convert(db: Session, amount: float, cur_from: str, cur_to: str) -> float:
    """
    Convert using today's FX rate.
    Example: convert(db, 100, "EUR", "CAD")
    """
    if cur_from.upper() == cur_to.upper():
        return amount

    rate = get_rate(db, cur_from, cur_to)
    return float(Decimal(str(amount)) * Decimal(str(rate)))


# -------------------------------------------------
# 3) Store booking FX snapshot
# -------------------------------------------------
def snapshot_booking_fx(bk, native_cur: str, paid_cur: str, display_cur: str, db: Session):
    """
    Store all FX values inside booking model safely.
    """

    native_cur  = native_cur.upper()
    paid_cur    = paid_cur.upper()
    display_cur = display_cur.upper()

    # Native → Paid rate
    rate_np = get_rate(db, native_cur, paid_cur)

    # Native → Display
    amount_display = convert(db, bk.amount_native, native_cur, display_cur)

    # Save
    try:
        bk.currency_native = native_cur
        bk.currency_paid = paid_cur
        bk.currency_display = display_cur

        bk.fx_rate_native_to_paid = rate_np
        bk.amount_display = int(round(amount_display))
        bk.platform_fee_currency = paid_cur
    except Exception:
        pass


# -------------------------------------------------
# 4) Helper: Format currency
# -------------------------------------------------
def fmt(amount: float, cur: str) -> str:
    return f"{amount:,.2f} {cur.upper()}"
