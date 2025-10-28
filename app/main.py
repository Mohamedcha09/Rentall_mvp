# app/main.py

# 1) حمّل .env مبكرًا جدًا
from dotenv import load_dotenv
load_dotenv()

# 2) إعدادات عامة
import os
import random
import difflib

# 3) Cloudinary (اختياري)
import cloudinary
import cloudinary.uploader
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

# 4) FastAPI & أُسس المشروع
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .database import Base, engine, SessionLocal, get_db
from .models import User, Item
from .utils import CATEGORIES, category_label

# 5) الروترات
from .auth import router as auth_router
from .admin import router as admin_router
from .items import router as items_router
from .messages import router as messages_router, unread_count
from .ratings import router as ratings_router
from .profiles import router as profiles_router
from .activate import router as activate_router
from .freeze import router as freeze_router
from .payments import router as payments_router
from .checkout import router as checkout_router
from .pay_api import router as pay_api_router
from .payout_connect import router as payout_connect_router
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
from .routes_favorites import router as favorites_router
from .routers.me import router as me_router
from .routes_home import router as home_router
from .routes_deposits import router as deposits_router          # DM
from .routes_evidence import router as evidence_router          # Deposit evidences
from .cron_auto_release import router as cron_router            # Manual trigger (test/admin)
from .debug_email import router as debug_email_router
from .routes_metrics import router as metrics_router
from .reports import router as reports_router
from .admin_reports import router as admin_reports_router

# -----------------------------------------------------------------------------
# إنشاء التطبيق
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# الجلسات (الكوكيز آمنة على الإنتاج فقط) + ضبط الدومين
# -----------------------------------------------------------------------------
SITE_URL = os.environ.get("SITE_URL", "")
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", "sevor.net")   # ← مهم جدًا
HTTPS_ONLY_COOKIES = bool(int(os.environ.get("HTTPS_ONLY_COOKIES", "1" if SITE_URL.startswith("https") else "0")))

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-secret"),
    session_cookie="ra_session",
    same_site="lax",
    https_only=HTTPS_ONLY_COOKIES,
    max_age=60 * 60 * 24 * 30,
    domain=COOKIE_DOMAIN,  # ← يضمن أن الكوكيز تُكتَب لدومين sevor.net
)

# -----------------------------------------------------------------------------
# فرض التحويل إلى الدومين الأساسي (sevor.net) لمنع ضياع الجلسة
# -----------------------------------------------------------------------------
@app.middleware("http")
async def force_primary_domain(request: Request, call_next):
    try:
        host = request.headers.get("host", "")
        primary = os.environ.get("COOKIE_DOMAIN", "sevor.net")
        # أي دومين غير الأساسي يتحوّل 301 إلى sevor.net مع نفس المسار والكويري
        if host and host != primary:
            new_url = f"https://{primary}{request.url.path}"
            if request.url.query:
                new_url += f"?{request.url.query}"
            return RedirectResponse(new_url, status_code=301)
    except Exception:
        pass
    return await call_next(request)

# -----------------------------------------------------------------------------
# Static / Templates / Uploads
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# اجعل مجلد الرفع موحّدًا على مستوى المشروع (خارج app/)
APP_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
UPLOADS_DIR = os.path.join(APP_ROOT, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.templates = templates

def media_url(path: str | None) -> str:
    """يُرجع رابط Cloudinary كما هو، أو يسبق المسار المحلي بـ '/'."""
    if not path:
        return ""
    p = str(path).strip()
    if p.startswith("http://") or p.startswith("https://"):
        return p
    return p if p.startswith("/") else "/" + p

app.templates.env.filters["media_url"] = media_url

# -----------------------------------------------------------------------------
# قواعد البيانات
# -----------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

def ensure_sqlite_columns():
    """
    هوت-فيكس أعمدة ناقصة عند استخدام SQLite فقط (يتجاهل Postgres):
      - users.is_mod / users.is_deposit_manager (لصلاحيات المود و DM)
      - deposit_evidences.uploader_id
      - reports.status / reports.tag / reports.updated_at
    """
    try:
        try:
            backend = engine.url.get_backend_name()
        except Exception:
            backend = getattr(getattr(engine, "dialect", None), "name", "")
        if backend != "sqlite":
            return

        with engine.begin() as conn:
            # ===== users: is_mod / is_deposit_manager =====
            try:
                ucols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('users')").all()}
                if "is_mod" not in ucols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_mod BOOLEAN NOT NULL DEFAULT 0;")
                if "is_deposit_manager" not in ucols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_deposit_manager BOOLEAN NOT NULL DEFAULT 0;")
            except Exception as e:
                print(f"[WARN] ensure_sqlite_columns: users.* → {e}")

            # ===== deposit_evidences.uploader_id =====
            try:
                ecols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('deposit_evidences')").all()}
                if "uploader_id" not in ecols:
                    conn.exec_driver_sql("ALTER TABLE deposit_evidences ADD COLUMN uploader_id INTEGER;")
            except Exception as e:
                print(f"[WARN] ensure_sqlite_columns: deposit_evidences.uploader_id → {e}")

            # ===== reports: status/tag/updated_at =====
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

# === جديد: تهيئة أعمدة users.is_mod / users.badge_admin على جميع المحركات
def ensure_users_columns():
    """
    يضمن وجود users.is_mod و users.badge_admin على SQLite و Postgres.
    """
    try:
        try:
            backend = engine.url.get_backend_name()
        except Exception:
            backend = getattr(getattr(engine, "dialect", None), "name", "")

        with engine.begin() as conn:
            if backend == "sqlite":
                cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('users')").all()}
                if "is_mod" not in cols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_mod BOOLEAN DEFAULT 0;")
                if "badge_admin" not in cols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN badge_admin BOOLEAN DEFAULT 0;")
            elif str(backend).startswith("postgres"):
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_mod BOOLEAN DEFAULT false;")
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS badge_admin BOOLEAN DEFAULT false;")
        print("[OK] ensure_users_columns(): users.is_mod / badge_admin ready")
    except Exception as e:
        print(f"[WARN] ensure_users_columns failed: {e}")

ensure_sqlite_columns()
ensure_users_columns()

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

# إظهار حالة تفعيل المدفوعات (اختياري)
PAYOUTS_ENABLED = os.getenv("ENABLE_PAYOUTS", "0") == "1"
print("[OK] payouts enabled via env" if PAYOUTS_ENABLED else "[INFO] payouts disabled (set ENABLE_PAYOUTS=1)")

# -----------------------------------------------------------------------------
# صور الواجهة (Hero + Top slider)
# -----------------------------------------------------------------------------
BANNERS_DIR = os.path.join(STATIC_DIR, "img", "banners")
BANNERS_URL_PREFIX = "/static/img/banners"
ALLOWED_BANNER_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
BANNERS_SHUFFLE = os.getenv("BANNERS_SHUFFLE", "1") == "1"

def list_banner_images() -> list[str]:
    try:
        os.makedirs(BANNERS_DIR, exist_ok=True)
        files = [
            f"{BANNERS_URL_PREFIX}/{name}"
            for name in sorted(os.listdir(BANNERS_DIR))
            if os.path.isfile(os.path.join(BANNERS_DIR, name))
            and os.path.splitext(name)[1].lower() in ALLOWED_BANNER_EXTS
        ]
        if BANNERS_SHUFFLE:
            random.shuffle(files)
        return files
    except Exception as e:
        print("[WARN] list_banner_images failed:", e)
        return []

TOP_SLIDER_DIR = os.path.join(STATIC_DIR, "img", "top_slider")
TOP_SLIDER_URL_PREFIX = "/static/img/top_slider"
ALLOWED_TOP_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

def list_top_slider_images() -> list[str]:
    try:
        os.makedirs(TOP_SLIDER_DIR, exist_ok=True)
        return [
            f"{TOP_SLIDER_URL_PREFIX}/{name}"
            for name in sorted(os.listdir(TOP_SLIDER_DIR))
            if os.path.isfile(os.path.join(TOP_SLIDER_DIR, name))
            and os.path.splitext(name)[1].lower() in ALLOWED_TOP_EXTS
        ]
    except Exception as e:
        print("[WARN] list_top_slider_images failed:", e)
        return []

def split_into_three_columns(urls: list[str]) -> list[list[str]]:
    cols = [[], [], []]
    for i, u in enumerate(urls):
        cols[i % 3].append(u)
    return cols

# -----------------------------------------------------------------------------
# تسجيل الروترات
# -----------------------------------------------------------------------------
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
app.include_router(debug_cloudinary_router)
app.include_router(home_router)
app.include_router(metrics_router)
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
app.include_router(deposits_router)
app.include_router(evidence_router)
app.include_router(cron_router)
app.include_router(reports_router)
app.include_router(admin_reports_router)

# -----------------------------------------------------------------------------
# مسار قديم → تحويل إلى صفحة البلاغات الجديدة
# -----------------------------------------------------------------------------
@app.get("/mod/reports")
def legacy_mod_reports_redirect():
    return RedirectResponse(url="/admin/reports", status_code=308)

# -----------------------------------------------------------------------------
# الصفحات العامة
# -----------------------------------------------------------------------------
def _cat_code(cat) -> str:
    if isinstance(cat, dict):
        return cat.get("code") or cat.get("value") or cat.get("id") or cat.get("slug") or cat.get("key")
    if isinstance(cat, (list, tuple)) and cat:
        return str(cat[0])
    return str(cat) if cat is not None else None

@app.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
    category: str | None = None,
    q: str | None = None,
    city: str | None = None,
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
        matched = difflib.get_close_matches(requested, cities, n=8, cutoff=0.6) if requested else []
        if matched:
            query = query.filter(func.lower(Item.city).in_(matched))
        elif city:
            query = query.filter(Item.city.ilike(f"%{city}%"))

    items = query.order_by(func.random()).limit(20).all()
    for it in items:
        it.category_label = category_label(it.category)

    popular_items = db.query(Item).filter(Item.is_active == "yes").order_by(func.random()).limit(12).all()

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

    mixed_items = db.query(Item).filter(Item.is_active == "yes").order_by(func.random()).limit(24).all()

    banners = list_banner_images()
    top_strip_cols = split_into_three_columns(list_top_slider_images())

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
            "top_strip_cols": top_strip_cols,
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

# -----------------------------------------------------------------------------
# مزامنة أعلام المستخدم من القاعدة إلى الجلسة
# -----------------------------------------------------------------------------
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
                        sess_user["is_deposit_manager"] = bool(getattr(db_user, "is_deposit_manager", False))
                        try:
                            sess_user["is_mod"] = bool(getattr(db_user, "is_mod", False))
                        except Exception:
                            pass
                        for key in [
                            "badge_admin","badge_new_yellow","badge_pro_green","badge_pro_gold",
                            "badge_purple_trust","badge_renter_green","badge_orange_stars"
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

# -----------------------------------------------------------------------------
# خدمات بسيطة
# -----------------------------------------------------------------------------
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
    return templates.TemplateResponse("notifications.html", {"request": request, "session_user": u, "title": "الإشعارات"})