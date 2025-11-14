from fastapi import APIRouter, Request

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

    # نكتب الشكل الكامل الذي يحتاجه middleware و currency
    cur = guess_currency_for(loc)

    request.session["geo"] = {
        "ip": None,
        "country": loc,
        "region": None,
        "city": None,
        "currency": cur,
        "source": "manual"
    }

    # نكتب الكوكي أيضاً ليقرأها currency_middleware
    response = {"ok": True, "country": loc, "currency": cur}
    return response


@router.get("/geo/debug")
def geo_debug(request: Request):
    return {
        "session_geo": request.session.get("geo"),
        "disp_cur_cookie": request.cookies.get("disp_cur"),
        "state_display_currency": getattr(request.state, "display_currency", None),
    }
