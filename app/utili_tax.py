# app/utili_tax.py
from decimal import Decimal
from typing import Dict, Any, List
from .utils_tax import pick_tax_rate, calc_tax_amount, CA_TAX, US_TAX, EU_TAX

def _line(name: str, rate: Decimal, base: Decimal) -> Dict[str, Any]:
    amt = calc_tax_amount(base, rate)
    return {"name": name, "rate": float(rate), "amount": float(amt)}

def compute_order_taxes(subtotal: float, geo: Dict[str, str]) -> Dict[str, Any]:
    """يحاول حساب الضرائب يدويًا حسب الدولة والمقاطعة."""
    base = Decimal(str(subtotal or 0))
    if base <= 0:
        return {"lines": [], "total": 0.0, "grand_total": float(base)}

    country = (geo.get("country") or "").upper()
    sub     = (geo.get("sub") or "").upper()

    lines: List[Dict[str, Any]] = []

    # 🇨🇦 كندا
    if country == "CA":
        if sub in ("ON","NB","NL","NS","PE"):
            lines.append(_line("HST", Decimal("0.13" if sub=="ON" else "0.15"), base))
        elif sub == "QC":
            lines.append(_line("GST", Decimal("0.05"), base))
            lines.append(_line("QST", Decimal("0.09975"), base))
        elif sub in ("BC","MB","SK"):
            pst_map = {"BC":Decimal("0.07"),"MB":Decimal("0.07"),"SK":Decimal("0.06")}
            lines.append(_line("GST", Decimal("0.05"), base))
            lines.append(_line("PST", pst_map[sub], base))
        elif sub in ("AB","NT","NU","YT"):
            lines.append(_line("GST", Decimal("0.05"), base))
        else:
            lines.append(_line("GST", Decimal("0.05"), base))

    # 🇺🇸 أمريكا
    elif country == "US" and sub in US_TAX:
        lines.append(_line("Sales tax", US_TAX[sub], base))

    # 🇪🇺 أوروبا
    elif country in EU_TAX:
        lines.append(_line("VAT", EU_TAX[country], base))

    else:
        # دول أخرى — لا ضرائب
        return {}

    total = round(sum(x["amount"] for x in lines), 2)
    return {
        "lines": lines,
        "total": total,
        "grand_total": round(float(base) + total, 2),
    }
