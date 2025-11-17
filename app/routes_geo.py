# app/routes_geo.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from .utils_geo import EU_COUNTRIES, detect_location

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

@router.get("/geo/pick", response_class=HTMLResponse)
def geo_pick(request: Request):
    app = request.app
    templates = getattr(app, "templates")
    return templates.TemplateResponse("geo_pick.html", {"request": request})


@router.get("/geo/set")
def geo_set(request: Request, loc: str = "US"):
    """
    يضبط الدولة المختارة يدوياً (manual) مع التحقق من الدولة الحقيقية عبر GeoIP/Headers.
    - لو الدولتان مختلفتان → لا نحفظ GEO ونرجع ok=False
    - لو نفس الدولة أو لا نستطيع اكتشاف الحقيقية → نقبل ونحفظ manual
    """
    loc = (loc or "").upper()

    # لو الدولة غير مسموحة أصلاً
    if loc not in ALLOWED_COUNTRIES:
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

    # لو استطعنا اكتشاف دولة حقيقية و هي أيضاً من ALLOWED وكانت مختلفة → كذب
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
    cur = guess_currency_for(loc)

    request.session["geo"] = {
        "ip": detected.get("ip") if detected else None,
        "country": loc,
        "region": detected.get("region") if detected else None,
        "city": detected.get("city") if detected else None,
        "currency": cur,
        "source": "manual",
    }

    resp = JSONResponse({"ok": True, "country": loc, "currency": cur})
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
        "cookie": request.cookies.get("disp_cur")
    }


@router.get("/geo/clear")
def geo_clear(request: Request):
    request.session.pop("geo", None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("disp_cur")
    return resp
