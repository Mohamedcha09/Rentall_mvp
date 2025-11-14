from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["geo"])

# -------- إعدادات الكوكي --------
COOKIE_DOMAIN = "sevor.net"
HTTPS_ONLY_COOKIES = True


# -------- قائمة دول اليورو --------
EURO_COUNTRIES = {
    "FR", "NL", "DE", "BE", "ES", "IT", "PT", "FI", "AT", "IE", "EE", "LV",
    "LT", "LU", "SK", "SI", "MT", "CY", "GR"
}


# -------- تحديد العملة حسب الدولة --------
def guess_currency_for(code: str) -> str:
    if code == "US":
        return "USD"
    if code == "CA":
        return "CAD"
    if code in EURO_COUNTRIES:
        return "EUR"
    return "USD"  # باقي الدول = USD


# ===========================
#     /geo/set (الحل النهائي)
# ===========================
@router.get("/geo/set")
def geo_set(request: Request, loc: str = "US"):
    loc = (loc or "US").upper()
    cur = guess_currency_for(loc)

    # تخزين الدولة والعمل في الجلسة
    request.session["geo"] = {
        "ip": None,
        "country": loc,
        "region": None,
        "city": None,
        "currency": cur,
        "source": "manual",
    }

    # الرد + كتابة كوكي العملة
    resp = JSONResponse({"ok": True, "country": loc, "currency": cur})
    resp.set_cookie(
        "disp_cur",
        cur,
        max_age=60 * 60 * 24 * 180,  # 6 شهور
        httponly=False,
        samesite="lax",
        domain=COOKIE_DOMAIN,
        secure=HTTPS_ONLY_COOKIES,
    )
    return resp


# ===========================
#     /geo/debug
# ===========================
@router.get("/geo/debug")
def geo_debug(request: Request):
    session_geo = request.session.get("geo")
    disp_cookie = request.cookies.get("disp_cur")
    state = getattr(request.state, "display_currency", None)

    return {
        "session_geo": session_geo,
        "disp_cur_cookie": disp_cookie,
        "state_display_currency": state,
    }
