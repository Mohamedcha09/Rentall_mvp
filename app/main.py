# app/main.py
import os
import difflib
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from .database import Base, engine, SessionLocal, get_db
from .models import User, Item

# الروترات
from .auth import router as auth_router
from .admin import router as admin_router
from .items import router as items_router
from .messages import router as messages_router, unread_count
from .ratings import router as ratings_router
from .profiles import router as profiles_router
from .utils import CATEGORIES, category_label
from .activate import router as activate_router
from .freeze import router as freeze_router
from .payments import router as payments_router
from .checkout import router as checkout_router
from .pay_api import router as pay_api_router
from .payout_connect import router as payout_connect_router
from .webhooks import router as webhooks_router
from .disputes import router as disputes_router
from .bookings import router as bookings_router
from .routes_search import router as search_router
from .routes_users import router as users_router
from .admin_badges import router as admin_badges_router  # اختياري

# [مضاف] راوتر المفضّلات
from .routes_favorites import router as favorites_router

load_dotenv()

app = FastAPI()

# =========================
# جلسات مستقرة
# =========================
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-secret"),
    session_cookie="ra_session",
    same_site="lax",
    https_only=True,
    max_age=60 * 60 * 24 * 30,  # 30 يوم
)

# =========================
# static / uploads / templates
# =========================
BASE_DIR = os.path.dirname(_file_)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(os.path.dirname(BASE_DIR), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.templates = templates

# إنشاء الجداول
Base.metadata.create_all(bind=engine)

# يضيف admin افتراضي إذا غير موجود
def seed_admin():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@example.com").first()
        if not admin:
            from .utils import hash_password
            admin = User(
                first_name="Admin",
                last_name="User",
                email="admin@example.com",
                phone="0000000000",
                password_hash=hash_password("admin123"),
                role="admin",
                status="approved",
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()

seed_admin()

# ===== تفعيل payouts اختياريًا =====
PAYOUTS_ENABLED = os.getenv("ENABLE_PAYOUTS", "0") == "1"
payouts_router = None
if PAYOUTS_ENABLED:
    try:
        import stripe  # تأكد أن المكتبة متوفرة
        from .payouts import router as _payouts_router
        payouts_router = _payouts_router
        print("[OK] payouts router enabled")
    except Exception as e:
        print(f"[SKIP] payouts router (enabled but failed): {e}")
else:
    print("[INFO] payouts router disabled (set ENABLE_PAYOUTS=1 & STRIPE_SECRET_KEY to enable)")

# تسجيل الروترات
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(items_router)
app.include_router(messages_router)
app.include_router(ratings_router)
app.include_router(profiles_router)
app.include_router(activate_router)
app.include_router(freeze_router)
app.include_router(payments_router)
app.include_router(checkout_router)
app.include_router(pay_api_router)
app.include_router(payout_connect_router)
app.include_router(webhooks_router)
app.include_router(disputes_router)
app.include_router(bookings_router)
app.include_router(search_router)
app.include_router(users_router)
app.include_router(admin_badges_router)
# [مضاف] تسجيل راوتر المفضّلات
app.include_router(favorites_router)

if payouts_router:
    app.include_router(payouts_router)

# ===== أداة صغيرة لاستخراج كود التصنيف بأشكال مختلفة
def _cat_code(cat) -> str:
    """
    يدعم:
    - dict: code / value / id / slug / key
    - tuple/list مثل: ('cars', 'سيارات')
    - قيمة نصية مباشرة
    """
    if isinstance(cat, dict):
        return (
            cat.get("code")
            or cat.get("value")
            or cat.get("id")
            or cat.get("slug")
            or cat.get("key")
        )
    if isinstance(cat, (list, tuple)) and cat:
        return str(cat[0])
    return str(cat) if cat is not None else None

# =========================
# الصفحة الرئيسية — أقسام شائعة/تصنيفات/مختلط
# =========================
@app.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
    category: str = None,
    q: str = None,
    city: str = None,
):
    # توجيه للترحيب للزائر فقط
    if not request.cookies.get("seen_welcome") and not request.session.get("user"):
        return RedirectResponse(url="/welcome", status_code=303)

    query = db.query(Item).filter(Item.is_active == "yes")
    current_category = None

    if category:
        query = query.filter(Item.category == category)
        current_category = category

    # بحث نصي
    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(Item.title.ilike(pattern), Item.description.ilike(pattern)))

    # بحث مدينة بمطابقة مرنة
    if city:
        cities_raw = db.query(func.lower(Item.city)).distinct().all()
        cities = [c[0] for c in cities_raw if c[0]]
        requested = (city or "").strip().lower()
        matched_cities = []
        if requested:
            matches = difflib.get_close_matches(requested, cities, n=8, cutoff=0.6)
            if matches:
                matched_cities = matches
            else:
                query = query.filter(Item.city.ilike(f"%{city}%"))
        if matched_cities:
            query = query.filter(func.lower(Item.city).in_(matched_cities))

    # قائمة عامة
    items = query.order_by(func.random()).limit(20).all()
    for it in items:
        it.category_label = category_label(it.category)

    # ===== أقسام الرئيسية =====
    popular_items = (
        db.query(Item)
        .filter(Item.is_active == "yes")
        .order_by(func.random())
        .limit(12)
        .all()
    )

    items_by_category = {}
    for cat in CATEGORIES:
        code = _cat_code(cat)
        if not code:
            continue
        items_by_category[code] = (
            db.query(Item)
            .filter(Item.is_active == "yes", Item.category == code)
            .order_by(func.random())
            .limit(10)
            .all()
        )

    mixed_items = (
        db.query(Item)
        .filter(Item.is_active == "yes")
        .order_by(func.random())
        .limit(24)
        .all()
    )

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "title": "Marketplace",
            "items": items,
            "categories": CATEGORIES,
            "current_category": current_category,
            "session_user": request.session.get("user"),
            "search_q": q or "",
            "search_city": city or "",
            # جديد
            "popular_items": popular_items,
            "items_by_category": items_by_category,
            "mixed_items": mixed_items,
            "category_label": category_label,
        },
    )

# =========================
# صفحات عامة
# =========================
@app.get("/welcome", response_class=HTMLResponse)
def welcome(request: Request):
    u = request.session.get("user")
    return templates.TemplateResponse("welcome.html", {"request": request, "session_user": u})

@app.post("/welcome/continue")
def welcome_continue():
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("seen_welcome", "1", max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    return resp

@app.get("/about", response_class=HTMLResponse)
def about(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    return templates.TemplateResponse("about.html", {"request": request, "session_user": u})

# API شارة الرسائل
@app.get("/api/unread_count")
def api_unread_count(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return JSONResponse({"count": 0})
    return JSONResponse({"count": unread_count(u["id"], db)})

# =========================
# Middleware: مزامنة session_user بأمان
# =========================
@app.middleware("http")
async def sync_user_flags(request: Request, call_next):
    try:
        if hasattr(request, "session"):
            sess_user = request.session.get("user")
            if sess_user and "id" in sess_user:
                db_gen = get_db()
                db: Session = next(db_gen)
                try:
                    db_user = db.query(User).filter(User.id == sess_user["id"]).first()
                    if db_user:
                        # قيم أساسية
                        sess_user["is_verified"] = bool(getattr(db_user, "is_verified", False))
                        sess_user["role"] = getattr(db_user, "role", sess_user.get("role"))
                        sess_user["status"] = getattr(db_user, "status", sess_user.get("status"))
                        sess_user["payouts_enabled"] = bool(getattr(db_user, "payouts_enabled", False))

                        # شارات اختيارية إن وُجدت
                        for key in [
                            "badge_admin", "badge_new_yellow", "badge_pro_green", "badge_pro_gold",
                            "badge_purple_trust", "badge_renter_green", "badge_orange_stars"
                        ]:
                            try:
                                sess_user[key] = bool(getattr(db_user, key))
                            except Exception:
                                pass

                        request.session["user"] = sess_user
                except Exception:
                    pass
                finally:
                    try:
                        next(db_gen)
                    except StopIteration:
                        pass
    except Exception:
        pass

    response = await call_next(request)
    return response

# Health Check
@app.get("/healthz")
def healthz():
    return {"status": "up"}

# =========================
# /lang: مسار بسيط غير مرتبط بترجمة — فقط يحفظ كوكي
# =========================
@app.get("/lang/{lang}")
def switch_language(lang: str, request: Request):
    referer = request.headers.get("referer") or "/"
    resp = RedirectResponse(url=referer, status_code=302)
    resp.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    return resp