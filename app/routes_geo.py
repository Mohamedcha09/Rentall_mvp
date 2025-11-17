# app/utils_geo.py
import os
from fastapi import Request

# إن كانت عندك قاعدة بيانات GeoIP حقيقية
# ضع مسارها هنا – وإلا لا مشكلة
GEOIP_DB_PATH = os.path.join(
    os.path.dirname(__file__),
    "GeoLite2-City.mmdb"
)

# دول الاتحاد الأوروبي
EU_COUNTRIES = {
    "FR","NL","DE","BE","ES","IT","PT","FI","AT","IE",
    "EE","LV","LT","LU","SK","SI","MT","CY","GR","HR"
}

# نفس القائمة لكن للثقة
EURO_COUNTRIES = EU_COUNTRIES.copy()


# ------------------------------
# 1) تحديد العملة من البلد
# ------------------------------
def guess_currency(country: str) -> str:
    c = (country or "").upper()
    if c == "CA":
        return "CAD"
    if c == "US":
        return "USD"
    if c in EURO_COUNTRIES:
        return "EUR"
    return "USD"


# ------------------------------
# 2) استخلاص البلد (لو لديك Cloudflare)
# ------------------------------
def detect_country_from_headers(request: Request) -> str | None:
    # Cloudflare
    cf = request.headers.get("CF-IPCountry")
    if cf:
        return cf.upper()

    # Custom header (لو تستعمله)
    h = request.headers.get("X-Country")
    if h:
        return h.upper()

    return None


# ------------------------------
# 3) وظيفة رئيسية: كتابة GEO في السيشن
# ------------------------------
def persist_location_to_session(request: Request):
    """
    هذه الدالة تُستدعى من geo_session_middleware
    وتكتب session["geo"] بالشكل الموحّد الجديد.
    """

    # 1) حاول أخذ البلد من الهيدر
    country = detect_country_from_headers(request)

    # 2) لو لم يوجد بلد → اجعله CA (حل آمن)
    if not country:
        country = "CA"

    country = country.upper()

    # 3) حدد العملة
    currency = guess_currency(country)

    # 4) الشكل الجديد الصحيح – مهم جداً
    request.session["geo"] = {
        "ip": None,
        "country": country,
        "region": None,
        "city": None,
        "currency": currency,
        "source": "auto",
    }


# ------------------------------
# 4) وظيفة detect_location (اختيارية)
# ------------------------------
def detect_location(request: Request) -> dict:
    """
    ترجع dict فيها معلومات البلد والعملة بعد الكتابة في session.
    """

    sess_geo = request.session.get("geo") or {}

    return {
        "ok": True,
        "country": sess_geo.get("country"),
        "currency": sess_geo.get("currency"),
        "source": sess_geo.get("source"),
    }
