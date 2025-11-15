from fastapi import APIRouter, Request, Body
from fastapi.responses import JSONResponse

from .utils_geo import EU_COUNTRIES  # نستخدمها للثقة (high/low)


router = APIRouter(tags=["geo"])

# -------- إعدادات الكوكي --------
COOKIE_DOMAIN = "sevor.net"
HTTPS_ONLY_COOKIES = True


# -------- قائمة دول اليورو --------
EURO_COUNTRIES = {
    "FR", "NL", "DE", "BE", "ES", "IT", "PT", "FI", "AT", "IE", "EE", "LV",
    "LT", "LU", "SK", "SI", "MT", "CY", "GR"
}
# كل الدول المسموح بها في /geo/set
ALLOWED_COUNTRIES = {"CA", "US"} | EURO_COUNTRIES | EU_COUNTRIES


# -------- تحديد العملة حسب الدولة --------
def guess_currency_for(code: str) -> str:
    if code == "US":
        return "USD"
    if code == "CA":
        return "CAD"
    if code in EURO_COUNTRIES:
        return "EUR"
    return "USD"  # باقي الدول = USD

@router.get("/geo/set")
def geo_set(request: Request, loc: str = "US"):
    """
    أنت فقط (كمطوّر) تستعمل هذا الروت للاختبار.
    هنا نمنع القيم الغلط مثل XYZ أو FRANCE
    ونقبل فقط الأكواد الصحيحة (CA / US + دول أوروبا).
    """
    # نطبّع المدخل
    loc = (loc or "").strip().upper()

    # لو القيمة غير صالحة → لا نلمس الجلسة ولا الكوكي
    if not loc or loc not in ALLOWED_COUNTRIES:
        # نقرأ ما هو مخزّن حاليًا (إن وجد) فقط للشفافية في الرد
        geo = request.session.get("geo") or {}
        prev_country = (geo.get("country") or "").upper() or None
        prev_currency = geo.get("currency")

        return JSONResponse({
            "ok": True,
            "ignored": True,          # هذا فقط معلومة لك، لا يكسر شيء في الواجهة
            "reason": "invalid_loc",  # loc غير معروف → لم نغيّر شيئًا
            "country": prev_country,
            "currency": prev_currency,
        })

    # هنا loc صالح (CA / US / دولة أوروبية)
    cur = guess_currency_for(loc)

    # نخزّن الدولة والعملة في الجلسة
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
    sess = request.session or {}

    # نحاول نقرأ dict جاهز اسمه geo
    geo_dict = sess.get("geo")
    if not geo_dict:
        # نركّب dict من القيم المسطّحة geo_country / geo_currency ...
        geo_dict = {
            "ip": sess.get("geo_ip"),
            "country": sess.get("geo_country"),
            "region": sess.get("geo_region"),
            "city": sess.get("geo_city"),
            "currency": sess.get("geo_currency"),
            "source": sess.get("geo_source"),
        }

    country = (geo_dict.get("country") or "").upper() if geo_dict else ""
    # مستوى الثقة مثل Airbnb: معروف ولا لا؟
    if country in ("CA", "US") or country in EU_COUNTRIES:
        confidence = "high"
    else:
        confidence = "low"

    disp_cookie = request.cookies.get("disp_cur")
    state = getattr(request.state, "display_currency", None)

    return {
        "ok": True,
        "session_geo": geo_dict,
        "disp_cur_cookie": disp_cookie,
        "state_display_currency": state,
        "confidence": confidence,
    }
def _load_geo(session):
    geo = session.get("geo")
    if not geo:
        geo = {
            "ip": session.get("geo_ip"),
            "country": session.get("geo_country"),
            "region": session.get("geo_region"),
            "city": session.get("geo_city"),
            "currency": session.get("geo_currency"),
            "source": session.get("geo_source"),
        }
    if geo is None:
        geo = {}
    return geo

def _save_geo(session, geo):
    session["geo"] = geo
    session["geo_ip"] = geo.get("ip")
    session["geo_country"] = geo.get("country")
    session["geo_region"] = geo.get("region")
    session["geo_city"] = geo.get("city")
    session["geo_currency"] = geo.get("currency")
    session["geo_source"] = geo.get("source")

@router.post("/geo/locale")
async def geo_locale(request: Request, lang: str = Body(..., embed=True)):
    lang = (lang or "").lower()
    session = request.session

    geo = _load_geo(session)

    # لو المستخدم غيّر العملة يدويًا → لا نلمسها
    if (geo.get("source") or "") in ("manual", "settings"):
        return {"ok": True}

    # استنتاج البلد من لغة المتصفح (fr-dz, ar-dz, fr-ca, en-us ...)
    parts = lang.split("-")
    if len(parts) == 2:
        country_code = parts[1].upper()
    else:
        country_code = None

    # حالة الجزائر
    if country_code == "DZ":
        geo["country"] = "DZ"
        geo["currency"] = "USD"
        geo["source"] = "locale"
        _save_geo(session, geo)
        return {"ok": True, "fixed": "dz"}

    return {"ok": True}


@router.post("/geo/set_currency")
async def geo_set_currency(request: Request, currency: str = Body(..., embed=True)):
    session = request.session
    geo = _load_geo(session)

    geo["currency"] = (currency or "USD").upper()
    geo["source"] = "manual"

    _save_geo(session, geo)
    return {"ok": True}
