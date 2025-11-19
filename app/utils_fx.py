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

def make_fx_snapshot(db: Session, amount_native: float, native_cur: str, display_cur: str):
    """
    Returns an FX snapshot dict:
      - currency_native
      - amount_native
      - currency_display
      - amount_display
      - currency_paid  (same as display)
      - fx_rate_native_to_paid
      - platform_fee_currency
    """
    native_cur  = native_cur.upper()
    display_cur = display_cur.upper()
    paid_cur    = display_cur       # Always pay using display currency

    # Native → Display
    rate_native_to_display = get_rate(db, native_cur, display_cur)
    amount_display = round(float(amount_native) * rate_native_to_display, 2)

    # FX rate native → paid
    rate_native_to_paid = rate_native_to_display

    return {
        "currency_native": native_cur,
        "amount_native": float(amount_native),

        "currency_display": display_cur,
        "amount_display": float(amount_display),

        "currency_paid": paid_cur,
        "fx_rate_native_to_paid": float(rate_native_to_paid),

        "platform_fee_currency": native_cur  # platform fee uses item currency
    }


# -------------------------------------------------
# 4) Helper: Format currency
# -------------------------------------------------
def fmt(amount: float, cur: str) -> str:
    return f"{amount:,.2f} {cur.upper()}"
