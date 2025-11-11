# app/utili_geo.py
from typing import Optional, Dict
from fastapi import Request
from .utils_geo import detect_location, persist_location_to_session

def geo_from_request(request: Request) -> Dict[str, Optional[str]]:
    """يُرجع البلد والمقاطعة (country, sub) حسب IP أو ?loc=CA-QC (ويُكمّل sub من الجلسة إن وُجدت)."""
    loc_q = request.query_params.get("loc")
    if loc_q:
        p = loc_q.replace("_","-").strip().upper().split("-")
        country = p[0] if p else None
        sub = p[1] if len(p) > 1 else None
        # تكملة المقاطعة من الجلسة إذا country موجود و sub مفقودة
        if country and not sub:
            sess = getattr(request, "session", {}) or {}
            guess = (sess.get("geo_region") or sess.get("region") or (sess.get("geo", {}) or {}).get("region"))
            if guess:
                sub = str(guess).strip().upper() or None
        return {"country": country, "sub": sub}

    info = persist_location_to_session(request) or detect_location(request) or {}
    return {
        "country": info.get("country"),
        "sub": info.get("region"),
    }

def locate_from_request(request: Request):  # alias
    return geo_from_request(request)

def locate_from_session(request: Request):  # alias
    info = persist_location_to_session(request) or {}
    return {"country": info.get("country"), "sub": info.get("region")}
