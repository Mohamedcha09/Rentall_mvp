# app/utils_tax.py
from decimal import Decimal

# ============================================================
# كندا — نسب تقريبية (GST/PST/HST)
# ============================================================
CA_TAX = {
    "AB": Decimal("0.05"),
    "BC": Decimal("0.12"),
    "MB": Decimal("0.12"),
    "NB": Decimal("0.15"),
    "NL": Decimal("0.15"),
    "NS": Decimal("0.15"),
    "NT": Decimal("0.05"),
    "NU": Decimal("0.05"),
    "ON": Decimal("0.13"),
    "PE": Decimal("0.15"),
    "QC": Decimal("0.14975"),
    "SK": Decimal("0.11"),
    "YT": Decimal("0.05"),
}

# ============================================================
# الولايات المتحدة — متوسطات تقريبية (state + local)
# ملاحظة: هذه أرقام تقديرية لتبسيط الفوترة الأولية.
# عدّلها لاحقاً أو اربط مزوّد ضرائب (TaxJar/Avalara) لدقة ZIP-code.
# ============================================================
US_TAX = {
    "AL": Decimal("0.092"),   # Alabama
    "AK": Decimal("0.018"),   # Alaska (لا دولة، محلي فقط تقريباً)
    "AZ": Decimal("0.084"),   # Arizona
    "AR": Decimal("0.095"),   # Arkansas
    "CA": Decimal("0.088"),   # California (قد تصل 8.75–10.25 في مدن)
    "CO": Decimal("0.078"),   # Colorado
    "CT": Decimal("0.0635"),  # Connecticut
    "DE": Decimal("0.000"),   # Delaware (لا ضريبة مبيعات)
    "DC": Decimal("0.060"),   # District of Columbia
    "FL": Decimal("0.070"),   # Florida
    "GA": Decimal("0.074"),   # Georgia
    "HI": Decimal("0.045"),   # Hawaii (GET)
    "ID": Decimal("0.060"),   # Idaho
    "IL": Decimal("0.088"),   # Illinois
    "IN": Decimal("0.070"),   # Indiana
    "IA": Decimal("0.069"),   # Iowa
    "KS": Decimal("0.087"),   # Kansas
    "KY": Decimal("0.060"),   # Kentucky
    "LA": Decimal("0.096"),   # Louisiana
    "ME": Decimal("0.055"),   # Maine
    "MD": Decimal("0.060"),   # Maryland
    "MA": Decimal("0.0625"),  # Massachusetts
    "MI": Decimal("0.060"),   # Michigan
    "MN": Decimal("0.075"),   # Minnesota
    "MS": Decimal("0.071"),   # Mississippi
    "MO": Decimal("0.083"),   # Missouri
    "MT": Decimal("0.000"),   # Montana (لا ضريبة مبيعات)
    "NE": Decimal("0.070"),   # Nebraska
    "NV": Decimal("0.082"),   # Nevada
    "NH": Decimal("0.000"),   # New Hampshire (لا ضريبة مبيعات عامة)
    "NJ": Decimal("0.06625"), # New Jersey
    "NM": Decimal("0.076"),   # New Mexico (Gross Receipts)
    "NY": Decimal("0.0888"),  # New York (تقريب NYC 8.875%)
    "NC": Decimal("0.070"),   # North Carolina
    "ND": Decimal("0.070"),   # North Dakota
    "OH": Decimal("0.072"),   # Ohio
    "OK": Decimal("0.090"),   # Oklahoma
    "OR": Decimal("0.000"),   # Oregon (لا ضريبة مبيعات)
    "PA": Decimal("0.063"),   # Pennsylvania
    "RI": Decimal("0.070"),   # Rhode Island
    "SC": Decimal("0.074"),   # South Carolina
    "SD": Decimal("0.064"),   # South Dakota
    "TN": Decimal("0.095"),   # Tennessee
    "TX": Decimal("0.082"),   # Texas
    "UT": Decimal("0.072"),   # Utah
    "VT": Decimal("0.062"),   # Vermont
    "VA": Decimal("0.060"),   # Virginia (تختلف بعض المدن قليلاً)
    "WA": Decimal("0.100"),   # Washington (قد تتجاوز 10% ببعض المدن)
    "WV": Decimal("0.065"),   # West Virginia
    "WI": Decimal("0.054"),   # Wisconsin
    "WY": Decimal("0.054"),   # Wyoming
}

# ============================================================
# الاتحاد الأوروبي — VAT للدول التي تستخدم اليورو
# (النسبة القياسية — Standard rate)
# ============================================================
EU_TAX = {
    "AT": Decimal("0.20"),  # Austria
    "BE": Decimal("0.21"),  # Belgium
    "HR": Decimal("0.25"),  # Croatia
    "CY": Decimal("0.19"),  # Cyprus
    "EE": Decimal("0.22"),  # Estonia
    "FI": Decimal("0.24"),  # Finland
    "FR": Decimal("0.20"),  # France
    "DE": Decimal("0.19"),  # Germany
    "GR": Decimal("0.24"),  # Greece
    "IE": Decimal("0.23"),  # Ireland
    "IT": Decimal("0.22"),  # Italy
    "LV": Decimal("0.21"),  # Latvia
    "LT": Decimal("0.21"),  # Lithuania
    "LU": Decimal("0.17"),  # Luxembourg
    "MT": Decimal("0.18"),  # Malta
    "NL": Decimal("0.21"),  # Netherlands
    "PT": Decimal("0.23"),  # Portugal (يختلف بالأقاليم، هذا القياسي)
    "SK": Decimal("0.20"),  # Slovakia
    "SI": Decimal("0.22"),  # Slovenia
    "ES": Decimal("0.21"),  # Spain
}

def pick_tax_rate(country: str | None, region: str | None, currency: str) -> Decimal:
    """
    ترجع نسبة الضريبة كنسبة عشرية (0.13 = 13%).
    المنطق:
      - كندا: حسب المقاطعة (region = QC/ON/…)
      - أمريكا: حسب الولاية (region = CA/NY/…) — تقريبية
      - أوروبا (اليورو): لو الدولة ضمن EU_TAX و العملة EUR -> VAT
      - غير ذلك: 0%
    """
    c = (country or "").upper().strip()
    r = (region or "").upper().strip()
    cur = (currency or "").upper().strip()

    if c == "CA" and r in CA_TAX:
        return CA_TAX[r]
    if c == "US" and r in US_TAX:
        return US_TAX[r]
    if cur == "EUR" and c in EU_TAX:
        return EU_TAX[c]

    return Decimal("0.00")

def calc_tax_amount(subtotal: Decimal, rate: Decimal) -> Decimal:
    """
    يحسب الضريبة = subtotal * rate (تقريب إلى خانتين عشريتين).
    """
    amt = (subtotal * rate).quantize(Decimal("0.01"))
    return amt
