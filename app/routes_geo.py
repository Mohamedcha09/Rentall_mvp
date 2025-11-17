# app/routes_geo.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .utils_geo import EU_COUNTRIES

router = APIRouter(tags=["geo"])

COOKIE_DOMAIN = "sevor.net"
HTTPS_ONLY_COOKIES = True

# نفس القائمة للثقة
EURO_COUNTRIES = EU_COUNTRIES

ALLOWED_COUNTRIES = {"CA", "US"} | EURO_COUNTRIES


def guess_currency_for(code: str):
    c = (code or "").upper()
    if c == "CA": return "CAD"
    if c == "US": return "USD"
    if c in EURO_COUNTRIES: return "EUR"
    return "USD"


@router.get("/geo/set")
def geo_set(request: Request, loc: str = "US"):
    loc = (loc or "").upper()

    if loc not in ALLOWED_COUNTRIES:
        geo = request.session.get("geo") or {}
        return {"ok": True, "ignored": True, "country": geo.get("country"), "currency": geo.get("currency")}

    cur = guess_currency_for(loc)

    request.session["geo"] = {
        "ip": None,
        "country": loc,
        "region": None,
        "city": None,
        "currency": cur,
        "source": "manual",
    }

    resp = JSONResponse({"ok": True, "country": loc, "currency": cur})
    resp.set_cookie(
        "disp_cur",
        cur,
        max_age=60*60*24*180,
        domain=COOKIE_DOMAIN,
        secure=HTTPS_ONLY_COOKIES,
        httponly=False,
        samesite="lax"
    )
    return resp


@router.get("/geo/debug")
def geo_debug(request: Request):
    geo = request.session.get("geo") or {}
    return {
        "ok": True,
        "session_geo": geo,
        "currency_state": getattr(request.state, "display_currency", None),
        "cookie": request.cookies.get("disp_cur")
    }


@router.get("/geo/clear")
def geo_clear(request: Request):
    request.session.pop("geo", None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("disp_cur")
    return resp
