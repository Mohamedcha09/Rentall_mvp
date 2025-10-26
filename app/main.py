# app/main.py

# >>> FIX: حمّل .env مبكّر جدًا قبل أي قراءة للمتغيرات
from dotenv import load_dotenv
load_dotenv()  # آمنة لو استدعيتها مرة ثانية لاحقًا

import cloudinary
import cloudinary.uploader
import os
import difflib
import random  # ← مستخدم للخلط العشوائي

# >>> ADD: Cloudinary secure
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True  # يضمن روابط https
)

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
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
from .payout_connect import router as payout_connect_router   # ✅ هذا الصحيح
from .webhooks import router as webhooks_router
from .disputes import router as disputes_router
from .routes_search import router as search_router
from .routes_users import router as users_router
from .admin_badges import router as admin_badges_router
from .routes_bookings import router as bookings_router
from .notifications import router as notifs_router
from .notifications_api import router as notifications_router
from .split_test import router as split_test_router
from .routes_debug_cloudinary import router as debug_cloudinary_router
# [مضاف] راوتر المفضّلات
from .routes_favorites import router as favorites_router
from .routers.me import router as me_router
from .routes_home import router as home_router

# ✅ [مضاف] راوتر إدارة الودائع (DM / قرارات الوديعة)
from .routes_deposits import router as deposits_router

# ✅ [جديد] راوتر أدلّة الوديعة (رفع/عرض ملفات)
from .routes_evidence import router as evidence_router

# ✅ [جديد] راوتر تشغيل الإفراج التلقائي يدويًا (للاختبار/الأدمن)
from .cron_auto_release import router as cron_router
from .debug_email import router as debug_email_router
from .routes_metrics import router as metrics_router  # ← جديد

# ✅ [جديد جدًا] راوتر البلاغات العامة + راوتر البلاغات الإدارية
from .reports import router as reports_router                 # /reports/*
from .admin_reports import router as admin_reports_router     # /admin/reports/*

app = FastAPI()
@app.get("/whoami")
def whoami(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    info = {"session_user": sess or None}
    if not sess:
        return info
    return {
        "id": sess.get("id"),
        "email": sess.get("email"),
        "role": sess.get("role"),
        "is_verified": bool(sess.get("is_verified")),
        "status": sess.get("status"),
    }

# =========================
# جلسات
# =========================
# >>> ADD: جعل https_only يعتمد على البيئة (HTTPS في الإنتاج، HTTP محليًا)
SITE_URL = os.environ.get("SITE_URL", "")
HTTPS_ONLY_COOKIES = os.getenv(
    "HTTPS_ONLY_COOKIES",
    "1" if SITE_URL.startswith("https") else "0"
) == "1"

COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or "sevor.net"

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-secret"),
    session_cookie="ra_session",
    same_site="lax",
    https_only=HTTPS_ONLY_COOKIES,  # >>> FIX: بدل True ثابتة
    max_age=60 * 60 * 24 * 30,
)

# =========================
# static / uploads / templates
# =========================
BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# ✅ توحيد مسار uploads ليكون على نفس جذر المشروع (Rentall_mvp/uploads)
APP_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
UPLOADS_DIR = os.path.join(APP_ROOT, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.templates = templates

# 🔽 أضف هذا الفلتر مباشرةً هنا
def media_url(path: str | None) -> str:
    """يُرجع رابط Cloudinary كما هو، أو يسبق المسار المحلي بـ '/'."""
    if not path:
        return ""
    p = str(path).strip()
    if p.startswith("http://") or p.startswith("https://"):
        return p
    # لو المسار أصلاً يبدأ بـ / اتركه
    if p.startswith("/"):
        return p
    return "/" + p

# تسجيل الفلتر في بيئة Jinja
app.templates.env.filters["media_url"] = media_url

# إنشاء الجداول
Base.metadata.create_all(bind=engine)

# =========================
# ✅ [إضافة] هوت-فيكس لتأمين أعمدة مفقودة في SQLite
# =========================
def ensure_sqlite_columns():
    """
    هوت-فيكس يضيف أعمدة ناقصة عند استخدام SQLite فقط (يتجاهل Postgres):
      - deposit_evidences.uploader_id
      - reports.status / reports.tag / reports.updated_at
    """
    try:
        # لو القاعدة ليست SQLite لا نفعل شيئًا
        try:
            backend = engine.url.get_backend_name()
        except Exception:
            backend = getattr(getattr(engine, "dialect", None), "name", "")
        if backend != "sqlite":
            return  # ✅ لا تشغّل PRAGMA على Postgres

        with engine.begin() as conn:
            # === deposit_evidences.uploader_id ===
            try:
                cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('deposit_evidences')").all()}
                if "uploader_id" not in cols:
                    conn.exec_driver_sql("ALTER TABLE deposit_evidences ADD COLUMN uploader_id INTEGER;")
            except Exception as e:
                print(f"[WARN] ensure_sqlite_columns: deposit_evidences.uploader_id → {e}")

            # === reports: status/tag/updated_at ===
            try:
                rcols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('reports')").all()}
                if "status" not in rcols:
                    conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'open';")
                if "tag" not in rcols:
                    conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN tag VARCHAR(24);")
                if "updated_at" not in rcols:
                    conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN updated_at TIMESTAMP;")
            except Exception as e:
                print(f"[WARN] ensure_sqlite_columns: reports.* → {e}")

        print("[OK] ensure_sqlite_columns(): columns verified/added")

    except Exception as e:
        print(f"[WARN] ensure_sqlite_columns skipped/failed: {e}")

# ✅ مهم: استدعِ الهوت-فيكس بعد إنشاء الجداول
ensure_sqlite_columns()

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

PAYOUTS_ENABLED = os.getenv("ENABLE_PAYOUTS", "0") == "1"
if PAYOUTS_ENABLED:
    print("[OK] payouts enabled via env")
else:
    print("[INFO] payouts disabled (set ENABLE_PAYOUTS=1 to show callout)")

# =========================
# ✅ صور الـ HERO (البانرز) — كما كانت
# =========================
BANNERS_DIR = os.path.join(STATIC_DIR, "img", "banners")
BANNERS_URL_PREFIX = "/static/img/banners"
ALLOWED_BANNER_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
BANNERS_SHUFFLE = os.getenv("BANNERS_SHUFFLE", "1") == "1"

def list_banner_images() -> list[str]:
    try:
        os.makedirs(BANNERS_DIR, exist_ok=True)
        files = []
        for name in os.listdir(BANNERS_DIR):
            p = os.path.join(BANNERS_DIR, name)
            if not os.path.isfile(p):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in ALLOWED_BANNER_EXTS:
                files.append(f"{BANNERS_URL_PREFIX}/{name}")
        # رتب أبجديًا للحصول على ترتيب ثابت، ثم اعمل shuffle إذا مفعّل
        files.sort()
        if BANNERS_SHUFFLE:
            random.shuffle(files)
        return files
    except Exception as e:
        print("[WARN] list_banner_images failed:", e)
        return []

# =========================
# ✅ جديد: صور السلايدر العلوي (الطولية 1024×1536)
# ضع الصور هنا: app/static/img/top_slider/
# =========================
TOP_SLIDER_DIR = os.path.join(STATIC_DIR, "img", "top_slider")
TOP_SLIDER_URL_PREFIX = "/static/img/top_slider"
ALLOWED_TOP_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

def list_top_slider_images() -> list[str]:
    """
    يعيد روابط الصور داخل static/img/top_slider بامتدادات مسموحة.
    """
    try:
        os.makedirs(TOP_SLIDER_DIR, exist_ok=True)
        files = []
        for name in os.listdir(TOP_SLIDER_DIR):
            p = os.path.join(TOP_SLIDER_DIR, name)
            if not os.path.isfile(p):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in ALLOWED_TOP_EXTS:
                files.append(f"{TOP_SLIDER_URL_PREFIX}/{name}")
        files.sort()  # ترتيب ثابت
        return files
    except Exception as e:
        print("[WARN] list_top_slider_images failed:", e)
        return []

def split_into_three_columns(urls: list[str]) -> list[list[str]]:
    """
    يقسم القائمة إلى ثلاث قوائم (عمود 1/2/3) بالتناوب.
    """
    cols = [[], [], []]
    for i, u in enumerate(urls):
        cols[i % 3].append(u)
    return cols

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
app.include_router(split_test_router)
# ✅ نُسجّل راوتر Stripe Connect الصحيح (يدعم GET/POST)
app.include_router(payout_connect_router)
# مع بقية include_router(...)
app.include_router(debug_cloudinary_router)
app.include_router(home_router)
app.include_router(metrics_router)  # ← جديد

app.include_router(webhooks_router)
app.include_router(disputes_router)
app.include_router(search_router)
app.include_router(users_router)
app.include_router(admin_badges_router)
app.include_router(bookings_router)
app.include_router(favorites_router)
app.include_router(notifs_router)
app.include_router(notifications_router)
app.include_router(me_router)
app.include_router(debug_email_router)

# ✅ [مضاف] تسجيل مسارات إدارة الودائع (DM)
app.include_router(deposits_router)

# ✅ [مضاف] تسجيل مسارات أدلّة الوديعة
app.include_router(evidence_router)

# ✅ [مضاف] تسجيل مسار تشغيل الإفراج التلقائي يدويًا (الاستيراد القديم)
app.include_router(cron_router)

# ✅ [جديد جدًا] تسجيل راوتر البلاغات العامة + الإدارية
app.include_router(reports_router)          # /reports/*
app.include_router(admin_reports_router)    # /admin/reports/*

def _cat_code(cat) -> str:
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

@app.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
    category: str = None,
    q: str = None,
    city: str = None,
):
    if not request.cookies.get("seen_welcome") and not request.session.get("user"):
        return RedirectResponse(url="/welcome", status_code=303)

    query = db.query(Item).filter(Item.is_active == "yes")
    current_category = None

    if category:
        query = query.filter(Item.category == category)
        current_category = category

    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(Item.title.ilike(pattern), Item.description.ilike(pattern)))

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

    items = query.order_by(func.random()).limit(20).all()
    for it in items:
        it.category_label = category_label(it.category)

    popular_items = (
        db.query(Item).filter(Item.is_active == "yes").order_by(func.random()).limit(12).all()
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
        db.query(Item).filter(Item.is_active == "yes").order_by(func.random()).limit(24).all()
    )

    # ✅ صور الـ HERO
    banners = list_banner_images()

    # ✅ صور السلايدر الطولي (من مجلد واحد) وتقسيمها لأعمدة
    top_all = list_top_slider_images()
    top_strip_cols = split_into_three_columns(top_all)

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
            "popular_items": popular_items,
            "items_by_category": items_by_category,
            "mixed_items": mixed_items,
            "category_label": category_label,
            "banners": banners,
            "top_strip_cols": top_strip_cols,  # ← مهم
        },
    )

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

@app.get("/api/unread_count")
def api_unread_count(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return JSONResponse({"count": 0})
    return JSONResponse({"count": unread_count(u["id"], db)})

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
                        sess_user["is_verified"] = bool(getattr(db_user, "is_verified", False))
                        sess_user["role"] = getattr(db_user, "role", sess_user.get("role"))
                        sess_user["status"] = getattr(db_user, "status", sess_user.get("status"))
                        sess_user["payouts_enabled"] = bool(getattr(db_user, "payouts_enabled", False))
                        # ===== [إضافة مهمة] أعلام الوديعة =====
                        sess_user["is_deposit_manager"] = bool(getattr(db_user, "is_deposit_manager", False))
                        sess_user["can_manage_deposits"] = bool(
                            sess_user.get("is_deposit_manager") or
                            (str(sess_user.get("role","")).lower() == "admin")
                        )
                        # ===== [إضافة مهمة] علم مُدقّق المحتوى (MOD) =====
                        try:
                            sess_user["is_mod"] = bool(getattr(db_user, "is_mod", False))
                        except Exception:
                            pass
                        # الشارات
                        for key in [
                            "badge_admin","badge_new_yellow","badge_pro_green","badge_pro_gold",
                            "badge_purple_trust","badge_renter_green","badge_orange_stars"
                        ]:
                            try: sess_user[key] = bool(getattr(db_user, key))
                            except Exception: pass
                        request.session["user"] = sess_user
                except Exception:
                    pass
                finally:
                    try: next(db_gen)
                    except StopIteration: pass
    except Exception:
        pass
    response = await call_next(request)
    return response

@app.get("/healthz")
def healthz():
    return {"status": "up"}

@app.get("/lang/{lang}")
def switch_language(lang: str, request: Request):
    referer = request.headers.get("referer") or "/"
    resp = RedirectResponse(url=referer, status_code=302)
    resp.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    return resp


@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        "notifications.html",
        {"request": request, "session_user": u, "title": "الإشعارات"}
    )
