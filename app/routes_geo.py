# app/routes_geo.py
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from .utils_geo import EU_COUNTRIES, detect_location

router = APIRouter(tags=["geo"])

# Keep the geo cookies on the same configured site domain as the session
# middleware.  Production uses ``sevor.net``; making this configurable keeps
# the two sources of cookie scope from drifting apart in other environments.
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", "sevor.net")
HTTPS_ONLY_COOKIES = True
GEO_PREFERENCE_MAX_AGE = 60 * 60 * 24 * 180

EURO_COUNTRIES = EU_COUNTRIES

# "WORLD" = باقي العالم
REST_OF_WORLD = "WORLD"

# دول عندنا لها منطق ضرائب خاص
ALLOWED_COUNTRIES = {"CA", "US"} | EURO_COUNTRIES
# كل القيم المسموحة من الواجهة
ALLOWED_LOCS = ALLOWED_COUNTRIES | {REST_OF_WORLD}


def guess_currency_for(code: str):
    c = (code or "").upper()
    if c == "CA":
        return "CAD"
    if c == "US":
        return "USD"
    if c in EURO_COUNTRIES:
        return "EUR"
    if c == REST_OF_WORLD:
        return "USD"
    return "USD"


def _set_geo_preference_cookie(response: JSONResponse, name: str, value: str) -> None:
    """Persist a visitor-level geo preference with the app's configured scope."""
    response.set_cookie(
        name,
        value,
        max_age=GEO_PREFERENCE_MAX_AGE,
        domain=COOKIE_DOMAIN,
        secure=HTTPS_ONLY_COOKIES,
        httponly=False,
        samesite="lax",
    )


@router.get("/geo/pick", response_class=HTMLResponse)
def geo_pick(request: Request):
    app = request.app
    templates = getattr(app, "templates")
    return templates.TemplateResponse(
        request=request,
        name="geo_pick.html",
        context={"request": request},
    )


@router.get("/geo/set")
def geo_set(request: Request, loc: str = "US"):
    """
    نأخذ اختيار المستخدم كما هو (بدون فحص كذب IP)،
    ونخزن:
      - country
      - currency
      - source = manual
    """
    loc = (loc or "").upper()

    # لو القيمة غير معروفة نهائياً → نتجاهلها
    if loc not in ALLOWED_LOCS:
        geo = request.session.get("geo") or {}
        return {
            "ok": True,
            "ignored": True,
            "country": geo.get("country"),
            "currency": geo.get("currency"),
        }

    # نقرأ معلومات تقريبية فقط (IP, city...) لو موجودة
    detected = detect_location(request) or {}
    real = (detected.get("country") or "").upper() or None

    # country في الجلسة:
    # - لو WORLD → نخزن الدولة الحقيقية إن وُجدت، وإلا None
    # - غير ذلك → نخزن الكود نفسه (CA/US/FR/…)
    if loc == REST_OF_WORLD:
        country_for_session = real
    else:
        country_for_session = loc

    cur = guess_currency_for(loc)

    request.session["geo"] = {
        "ip": detected.get("ip"),
        "country": country_for_session,
        "region": detected.get("region"),
        "city": detected.get("city"),
        "currency": cur,
        "source": "manual",
    }

    resp = JSONResponse(
        {"ok": True, "country": country_for_session, "currency": cur}
    )
    _set_geo_preference_cookie(resp, "disp_cur", cur)
    # A durable acknowledgement is deliberately separate from the currency:
    # it also protects a manual choice if a transient session is recreated.
    _set_geo_preference_cookie(resp, "geo_manual_done", "1")
    return resp


@router.post("/geo/dismiss")
def geo_dismiss():
    """Persist a visitor's explicit 'Not now' choice without changing currency."""
    resp = JSONResponse({"ok": True})
    _set_geo_preference_cookie(resp, "geo_manual_done", "1")
    return resp


@router.get("/geo/debug")
def geo_debug(request: Request):
    geo = request.session.get("geo") or {}
    return {
        "ok": True,
        "session_geo": geo,
        "currency_state": getattr(request.state, "display_currency", None),
        "cookie": request.cookies.get("disp_cur"),
    }


@router.get("/geo/clear")
def geo_clear(request: Request):
    request.session.pop("geo", None)
    resp = JSONResponse({"ok": True})
    # These cookies were set with an explicit domain, so clear them with that
    # same scope.  A reset should allow the picker to be shown again.
    resp.delete_cookie("disp_cur", domain=COOKIE_DOMAIN, secure=HTTPS_ONLY_COOKIES, samesite="lax")
    resp.delete_cookie("geo_manual_done", domain=COOKIE_DOMAIN, secure=HTTPS_ONLY_COOKIES, samesite="lax")
    return resp
