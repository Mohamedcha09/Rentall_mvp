# app/routes_geo.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from .utils_geo import EU_COUNTRIES, detect_location

router = APIRouter(tags=["geo"])

COOKIE_DOMAIN = "sevor.net"
HTTPS_ONLY_COOKIES = True

# نفس القائمة للثقة
EURO_COUNTRIES = EU_COUNTRIES

# كود خاص لباقي العالم (نستقبل "WORLD" من الواجهة)
REST_OF_WORLD = "WORLD"

# الدول التي عندنا لها منطق ضرائب حقيقي (CA / US / دول اليورو)
ALLOWED_COUNTRIES = {"CA", "US"} | EURO_COUNTRIES

# كل القيم المسموح أن تأتي من الواجهة (باقي العالم + المسموحين)
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
    يضبط الدولة المختارة يدوياً (manual) مع التحقق من الدولة الحقيقية عبر GeoIP/Headers.
    - لو الدولتان مختلفتان (مع دول مدعومة) → لا نحفظ GEO ونرجع ok=False
    - لو نفس الدولة أو لا نستطيع اكتشاف الحقيقية → نقبل ونحفظ manual
    """
    loc = (loc or "").upper()

    # لو القيمة غير مسموحة أصلاً
    if loc not in ALLOWED_LOCS:
        geo = request.session.get("geo") or {}
        return {
            "ok": True,
            "ignored": True,
            "country": geo.get("country"),
            "currency": geo.get("currency"),
        }

    # كشف الدولة الحقيقية من الجهاز
    detected = detect_location(request)
    real = (detected.get("country") or "").upper() if detected else None

    # لا نعمل فحص "الكذب" إلا لـ CA / US / دول اليورو
    # أما REST_OF_WORLD فنسمح به دائماً
    if loc != REST_OF_WORLD:
        if real and real in ALLOWED_COUNTRIES and real != loc:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "country_mismatch",
                    "real": real,
                },
                status_code=400,
            )

    # لا يوجد كذب واضح → نعتمد اختيار المستخدم
    if loc == REST_OF_WORLD:
        # في باقي العالم: نستعمل الدولة الحقيقية إن وجدت لكن العملة دائماً USD
        country_for_session = real if real else None
        cur = "USD"
    else:
        country_for_session = loc
        cur = guess_currency_for(loc)

    request.session["geo"] = {
        "ip": detected.get("ip") if detected else None,
        "country": country_for_session,
        "region": detected.get("region") if detected else None,
        "city": detected.get("city") if detected else None,
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
