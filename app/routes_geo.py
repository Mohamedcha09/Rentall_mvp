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
