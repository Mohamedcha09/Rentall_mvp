from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

EU_COUNTRIES = {
    "FR","DE","ES","IT","NL","BE","PT","LU","IE","FI","AT","GR","CY",
    "EE","LV","LT","MT","SI","SK","HR"
}

def guess_currency_for(country: str | None):
    if not country:
        return "USD"
    if country == "CA":
        return "CAD"
    if country == "US":
        return "USD"
    if country in EU_COUNTRIES:
        return "EUR"
    return "USD"



@router.get("/geo/set")
def geo_set(request: Request, loc: str = "US"):
    loc = (loc or "US").upper()
    cur = guess_currency_for(loc)

    # Save manual geo override
    request.session["geo"] = {
        "ip": None,
        "country": loc,
        "region": None,
        "city": None,
        "currency": cur,
        "source": "manual"
    }

    # Final response WITH COOKIE
    resp = JSONResponse({"ok": True, "country": loc, "currency": cur})
    resp.set_cookie(
        "disp_cur",
        cur,
        max_age=60 * 60 * 24 * 180,
        httponly=False,
        samesite="lax",
        domain=COOKIE_DOMAIN,
        secure=HTTPS_ONLY_COOKIES,
    )
    return resp


@router.get("/geo/debug")
def geo_debug(request: Request):
    return {
        "session_geo": request.session.get("geo"),
        "disp_cur_cookie": request.cookies.get("disp_cur"),
        "state_display_currency": getattr(request.state, "display_currency", None),
    }
