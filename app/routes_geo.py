from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/geo/set")
def geo_set(request: Request, loc: str = "US"):
    loc = (loc or "US").upper()
    request.session["geo"] = {"country": loc}
    return {"ok": True, "country": loc}

@router.get("/geo/debug")
def geo_debug(request: Request):
    return {
        "session_geo": request.session.get("geo"),
        "disp_cur_cookie": request.cookies.get("disp_cur"),
        "state_display_currency": getattr(request.state, "display_currency", None),
    }


@router.get("/geo/debug2")
def geo_debug2(request: Request):
    return {
        "geo_ip": request.session.get("geo_ip"),
        "geo_country": request.session.get("geo_country"),
        "geo_region": request.session.get("geo_region"),
        "geo_city": request.session.get("geo_city"),
        "geo_currency": request.session.get("geo_currency"),
        "geo_source": request.session.get("geo_source"),
        "disp_cur_cookie": request.cookies.get("disp_cur"),
        "state_display_currency": getattr(request.state, "display_currency", None),
    }
