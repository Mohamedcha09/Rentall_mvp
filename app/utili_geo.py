# app/utili_geo.py
from typing import Optional, Dict
from fastapi import Request
from .utils_geo import detect_location, persist_location_to_session

def geo_from_request(request: Request) -> Dict[str, Optional[str]]:
    """
    يرجّع البلد، الولاية، IP، العملة، source، وثقة عالية إذا جاءت من GeoIP.
    هذا هو الـ FULL OBJECT النهائي الذي تحتاجه /geo/debug و /geo/set.
    """

    # --- override: loc=? ---
    loc_q = request.query_params.get("loc")
    if loc_q:
        p = loc_q.replace("_","-").strip().upper().split("-")
        country = p[0] if p else None
        sub = p[1] if len(p) > 1 else None

        return {
            "ip": None,
            "country": country,
            "region": sub,
            "city": None,
            "currency": None,
            "source": "manual",
            "confidence": "high",
        }

    # --- session + auto detection ---
    info = persist_location_to_session(request) or {}

    return {
        "ip": info.get("ip"),
        "country": info.get("country"),
        "region": info.get("region"),
        "city": info.get("city"),
        "currency": info.get("currency"),
        "source": info.get("source"),
        "confidence": "high" if info.get("source") == "geoip" else "low",
    }


def locate_from_request(request: Request):
    return geo_from_request(request)


def locate_from_session(request: Request):
    info = persist_location_to_session(request) or {}
    return {
        "ip": info.get("ip"),
        "country": info.get("country"),
        "region": info.get("region"),
        "city": info.get("city"),
        "currency": info.get("currency"),
        "source": info.get("source"),
        "confidence": "high" if info.get("source") == "geoip" else "low",
    }
