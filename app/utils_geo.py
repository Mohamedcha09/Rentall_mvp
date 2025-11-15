# app/utils_geo.py
from __future__ import annotations
from typing import Optional, Dict
import os

import geoip2.database  # جديد

GEOIP_DB_PATH = os.getenv("GEOIP_DB_PATH")
_geoip_reader = None

try:
    if GEOIP_DB_PATH and os.path.exists(GEOIP_DB_PATH):
        _geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
except Exception:
    _geoip_reader = None

# دول الاتحاد الأوروبي (الأساسية المتداولة باليورو)
EU_COUNTRIES = {
    "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR",
    "HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"
}

# بعض المزودين (CDN/Proxy) يضيفون هيدرز جاهزة للبلد/الولاية
# سنقرأ أوسع مجموعة ممكنة + Fallback ذكي
HDRS_COUNTRY = [
    "CF-IPCountry",                 # Cloudflare
    "X-AppEngine-Country",          # Google App Engine / some proxies
    "X-Geo-Country", "X-Country",
    "X-Fastly-Country-Code",        # Fastly
    "X-Akamai-Edgescape-Country",
    "X-Edge-Country", "X-Ip-Country"
]
# المدينة/المنطقة (قد تأتي بصيغ مختلفة)
HDRS_REGION = [
    "X-AppEngine-Region", "X-Geo-Region", "X-Region", "X-Edge-Region",
    "X-Ip-Region", "X-Akamai-Edgescape-Region"
]
HDRS_CITY = [
    "X-AppEngine-City","X-Geo-City","X-City","X-Ip-City","X-Edge-City"
]

def _normalize(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    return v

def _two_upper(v: Optional[str]) -> Optional[str]:
    v = _normalize(v)
    return v.upper() if v else None

def _guess_currency(country: Optional[str]) -> str:
    c = (country or "").upper()
    if c == "CA": return "CAD"
    if c == "US": return "USD"
    if c in EU_COUNTRIES: return "EUR"
    # باقي دول العالم → USD
    return "USD"


def _get_client_ip(request) -> str:
    # نحاول أخذ أفضل IP حقيقي من هيدرز الوكالات
    hdrs = request.headers
    for key in ("CF-Connecting-IP","X-Forwarded-For","X-Real-IP","X-Client-IP","X-Forwarded","Forwarded"):
        val = hdrs.get(key)
        if val:
            # X-Forwarded-For قد يحتوي عدة IPs، نأخذ الأول
            ip = str(val).split(",")[0].strip()
            if ip:
                return ip
    try:
        return request.client.host or ""
    except Exception:
        return ""

def _country_from_geoip(ip: Optional[str]) -> Optional[str]:
    if not ip or not _geoip_reader:
        return None
    try:
        resp = _geoip_reader.country(ip)
        code = resp.country.iso_code
        if code and code != "ZZ":
            return code.upper()
    except Exception:
        return None
    return None


def detect_location(request) -> Dict[str, Optional[str]]:
    q = dict(request.query_params or {})

    loc_q = _normalize(q.get("loc") or q.get("geo") or q.get("location"))
    country_q, region_q = None, None
    if loc_q:
        parts = loc_q.replace("_","-").split("-")
        if len(parts) == 1:
            country_q = parts[0].upper()
        elif len(parts) >= 2:
            country_q, region_q = parts[0].upper(), parts[1].upper()

    hdrs = request.headers

    ip = _get_client_ip(request)

    country = country_q or None
    region  = region_q  or None
    city    = None
    source  = "query" if loc_q else None

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
                if not source:
                    source = f"header:{k}"
                break

    if not city:
        for k in HDRS_CITY:
            v = _normalize(hdrs.get(k))
            if v:
                city = v
                if not source:
                    source = f"header:{k}"
                break

    if country in (None, "", "ZZ"):
        country = None

    if not country and ip:
        geoip_country = _country_from_geoip(ip)
        if geoip_country:
            country = geoip_country
            if not source:
                source = "geoip"

    currency = _guess_currency(country)

    return {
        "ip": ip or None,
        "country": country,
        "region": region,
        "city": city,
        "currency": currency,
        "source": source or "unknown",
    }

def persist_location_to_session(request) -> dict:
    """
    يكشف الموقع ويُخزّنه في session إذا لم يكن مخزّنًا أو إذا طلبنا تغييرًا عبر ?loc=...
    يعيد نسخة القيم المخزنة.
    """
    sess = getattr(request, "session", None)
    if sess is None:
        return {}

    # إذا أعطى المستخدم override، نجبر التحديث
    has_override = any(k in request.query_params for k in ("loc","geo","location"))

    if not has_override and sess.get("geo_country"):
        # مخزّن مسبقًا — أعِد الموجود
        return {
            "ip": sess.get("geo_ip"),
            "country": sess.get("geo_country"),
            "region": sess.get("geo_region"),
            "city": sess.get("geo_city"),
            "currency": sess.get("geo_currency"),
            "source": sess.get("geo_source") or "session",
        }

    info = detect_location(request)
    sess["geo_ip"]       = info.get("ip")
    sess["geo_country"]  = info.get("country")
    sess["geo_region"]   = info.get("region")
    sess["geo_city"]     = info.get("city")
    sess["geo_currency"] = info.get("currency")
    sess["geo_source"]   = info.get("source")
    return {
        "ip": sess["geo_ip"],
        "country": sess["geo_country"],
        "region": sess["geo_region"],
        "city": sess["geo_city"],
        "currency": sess["geo_currency"],
        "source": sess["geo_source"],
    }
