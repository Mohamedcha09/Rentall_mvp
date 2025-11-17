# app/routes_geo.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from .utils_geo import EU_COUNTRIES, detect_location

router = APIRouter(tags=["geo"])

COOKIE_DOMAIN = "sevor.net"
HTTPS_ONLY_COOKIES = True

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


@router.get("/geo/pick", response_class=HTMLResponse)
def geo_pick(request: Request):
    app = request.app
    templates = getattr(app, "templates")
    return templates.TemplateResponse("geo_pick.html", {"request": request})


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
    resp.set_cookie(
        "disp_cur",
        cur,
        max_age=60 * 60 * 24 * 180,
        domain=COOKIE_DOMAIN,
        secure=HTTPS_ONLY_COOKIES,
        httponly=False,
        samesite="lax",
    )
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
    resp.delete_cookie("disp_cur")
    return resp
