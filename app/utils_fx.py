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
        # Try reverse
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
                return 1.0
        return 1.0

    try:
        return float(row.rate)
    except Exception:
        return 1.0


# -------------------------------------------------
# 2) Convert amount from currency A → B
# -------------------------------------------------
def convert(db: Session, amount: float, cur_from: str, cur_to: str) -> float:
    if cur_from.upper() == cur_to.upper():
        return amount

    rate = get_rate(db, cur_from, cur_to)
    return float(Decimal(str(amount)) * Decimal(str(rate)))


# -------------------------------------------------
# 3) SAFE VERSION for Templates → fx_rate(from, to)
# -------------------------------------------------
"""
🔥 IMPORTANT:
This function is what booking_flow.html calls directly:

   {% set fx = fx_rate(native_cur, currency) %}

Templates do NOT have the db session.
FastAPI templates pass fx_rate and then call it with:
    fx_rate(cur_from, cur_to)

So we return a *callable* that accepts db.
"""


def fx_rate(cur_from: str, cur_to: str):
    """
    Template-friendly wrapper.

    Returns a small lambda that expects db:
      fx_rate("EUR","USD")(db) → float

    BUT booking_flow passes db automatically because
    Jinja calls it like:

      fx = fx_rate(native_cur, currency)

    Then later:
      disp_price = item.price_per_day * (fx or 1.0)

    So we must return a float directly, not a lambda.
    
    → Therefore we create a simple global "last_db"
      and set it through inject_db_for_fx(db) from routes.
    """

    cur_from = (cur_from or "CAD").upper()
    cur_to = (cur_to or "CAD").upper()

    # Try using the last injected db
    global _FX_RATE_DB
    db = _FX_RATE_DB

    if db:
        return get_rate(db, cur_from, cur_to)

    # Fallback if db was not injected yet
    return 1.0


# Storage for last db session (used only for template fx_rate)
_FX_RATE_DB = None


def inject_db_for_fx(db: Session):
    """Called from routes to make fx_rate work inside templates."""
    global _FX_RATE_DB
    _FX_RATE_DB = db


# -------------------------------------------------
# 4) FX snapshot (used by bookings)
# -------------------------------------------------
def make_fx_snapshot(db: Session, amount_native: float, native_cur: str, display_cur: str):
    native_cur  = native_cur.upper()
    display_cur = display_cur.upper()
    paid_cur    = display_cur  # Pay using display currency

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

        "platform_fee_currency": native_cur,
    }


# -------------------------------------------------
# 5) Helper: Format currency
# -------------------------------------------------
def fmt(amount: float, cur: str) -> str:
    return f"{amount:,.2f} {cur.upper()}"
