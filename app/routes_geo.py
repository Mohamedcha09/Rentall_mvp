from fastapi import APIRouter, Request, Query

router = APIRouter()

@router.post("/api/geo/set")
def api_geo_set(request: Request, lat: float = Query(...), lon: float = Query(...)):
    s = request.session
    s["geo_enabled"] = True
    s["geo_lat"] = lat
    s["geo_lon"] = lon
    return {"ok": True}
