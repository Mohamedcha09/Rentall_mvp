# app/utils_geo.py
from __future__ import annotations
from typing import Optional, Dict
import os
import geoip2.database

GEOIP_DB_PATH = os.getenv("GEOIP_DB_PATH")
_geoip_reader = None

try:
    if GEOIP_DB_PATH and os.path.exists(GEOIP_DB_PATH):
        _geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
except Exception:
    _geoip_reader = None

EU_COUNTRIES = {
    "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR",
    "HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"
}

HDRS_COUNTRY = [
    "CF-IPCountry", "X-AppEngine-Country", "X-Geo-Country", "X-Country",
    "X-Fastly-Country-Code", "X-Akamai-Edgescape-Country",
    "X-Edge-Country", "X-Ip-Country"
]
HDRS_REGION = [
    "X-AppEngine-Region", "X-Geo-Region", "X-Region",
    "X-Edge-Region", "X-Ip-Region"
]
HDRS_CITY = [
    "X-AppEngine-City","X-Geo-City","X-City","X-Ip-City","X-Edge-City"
]

def _normalize(v: Optional[str]):
    if not v:
        return None
    s = str(v).strip()
    return s or None

def _two_upper(v: Optional[str]):
    v = _normalize(v)
    return v.upper() if v else None

def _guess_currency(country: Optional[str]) -> str:
    c = (country or "").upper()
    if c == "CA": return "CAD"
    if c == "US": return "USD"
    if c in EU_COUNTRIES: return "EUR"
    return "USD"

def _get_client_ip(request):
    hdrs = request.headers
    for key in ("CF-Connecting-IP","X-Forwarded-For","X-Real-IP"):
        val = hdrs.get(key)
        if val:
            return val.split(",")[0].strip()
    return request.client.host if request.client else ""

def _country_from_geoip(ip):
    if not ip or not _geoip_reader:
        return None
    try:
        data = _geoip_reader.country(ip)
        code = data.country.iso_code
        return code.upper() if code else None
    except Exception:
        return None

def detect_location(request) -> dict:
    q = request.query_params
    loc_q = _normalize(q.get("loc") or q.get("geo") or q.get("location"))

    country = None
    region = None
    city = None
    source = None

    if loc_q:
        parts = loc_q.replace("_","-").split("-")
        if len(parts) == 1:
            country = parts[0].upper()
        elif len(parts) >= 2:
            country, region = parts[0].upper(), parts[1].upper()
        source = "query"

    hdrs = request.headers
    ip = _get_client_ip(request)

    if not country:
        for k in HDRS_COUNTRY:
            v = _two_upper(hdrs.get(k))
            if v:
                country = v
                source = source or f"header:{k}"
                break

    if not region:
        for k in HDRS_REGION:
            v = _two_upper(hdrs.get(k))
            if v:
                region = v
                source = source or f"header:{k}"
                break

    if not city:
        for k in HDRS_CITY:
            v = _normalize(hdrs.get(k))
            if v:
                city = v
                source = source or f"header:{k}"
                break

    if not country and ip:
        c = _country_from_geoip(ip)
        if c:
            country = c
            source = source or "geoip"

    currency = _guess_currency(country)

    return {
        "ip": ip,
        "country": country,
        "region": region,
        "city": city,
        "currency": currency,
        "source": source or "unknown",
    }

# ============= النسخة الجديدة فقط =============
def persist_location_to_session(request):
    """
    تكتشف موقع الزائر الحقيقي وتخزّنه في session["geo"]،
    لكن إذا كان لدينا مصدر "manual" من قبل، لا تلمس الجلسة.
    """
    sess = request.session

    # لو عندنا GEO من قبل ومصدرها manual → لا نلمسه نهائياً
    existing = sess.get("geo") or {}
    if isinstance(existing, dict) and existing.get("source") == "manual":
        return existing

    info = detect_location(request)

    sess["geo"] = {
        "ip": info["ip"],
        "country": info["country"],
        "region": info["region"],
        "city": info["city"],
        "currency": info["currency"],
        "source": info["source"] or "auto",
    }

    return sess["geo"]

