# app/main.py

# 1) Load .env as early as possible
from dotenv import load_dotenv
load_dotenv()

# 2) General settings
import os
import random
import difflib
from datetime import date
from typing import Optional
import requests

from datetime import datetime, timedelta
from .models import FxRate  # ← بجانب استيراد User, Item

# 3) Cloudinary (optional)
import cloudinary
import cloudinary.uploader
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

# 4) FastAPI & project foundations
from fastapi import FastAPI, Request, Depends, APIRouter, Query, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from .database import Base, engine, SessionLocal, get_db
from .models import User, Item
from .utils import CATEGORIES, category_label
from .utils_geo import persist_location_to_session
# 5) Routers
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
from .support import router as support_router
import app.cs as cs_routes
from . import mod as mod_routes
from .md import router as md_router
from .reviews import router as reviews_router
from .routes_geo import router as geo_router

# -----------------------------------------------------------------------------
# Create the app
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
# Sessions (cookies are secure only in production) + set domain
# -----------------------------------------------------------------------------
SITE_URL = os.environ.get("SITE_URL", "")
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", "sevor.net")   # ← Very important
HTTPS_ONLY_COOKIES = bool(int(os.environ.get("HTTPS_ONLY_COOKIES", "1" if SITE_URL.startswith("https") else "0")))

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-secret"),
    session_cookie="ra_session",
    same_site="lax",
    https_only=HTTPS_ONLY_COOKIES,
    max_age=60 * 60 * 24 * 30,
    domain=COOKIE_DOMAIN,  # ← ensures cookies are written for sevor.net
)

# -----------------------------------------------------------------------------
# Enforce redirect to the primary domain (sevor.net) to prevent session loss
# -----------------------------------------------------------------------------
@app.middleware("http")
async def force_primary_domain(request: Request, call_next):
    try:
        host = request.headers.get("host", "")
        path = request.url.path
        primary = os.environ.get("COOKIE_DOMAIN", "sevor.net")

        # ✅ Skip redirect if the path is a Stripe Webhook
        if path.startswith("/webhooks/"):
            return await call_next(request)

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

# Make the uploads folder unified at the project level (outside app/)
APP_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
UPLOADS_DIR = os.path.join(APP_ROOT, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.templates = templates

def media_url(path: str | None) -> str:
    """Returns the Cloudinary URL as-is, or prefixes a local path with '/'."""
    if not path:
        return ""
    p = str(path).strip()
    if p.startswith("http://") or p.startswith("https://"):
        return p
    return p if p.startswith("/") else "/" + p

app.templates.env.filters["media_url"] = media_url

# -----------------------------------------------------------------------------
# Currencies (NEW)
# -----------------------------------------------------------------------------
SUPPORTED_CURRENCIES = ["CAD", "USD", "EUR"]
# ---------- FX storage helpers ----------
# ---------- FX storage helpers ----------
def _fx_upsert(db: Session, base: str, quote: str, rate: float, day: date):
    """
    insert-or-update صف واحد لليوم المعطى.
    ملاحظة: جدول fx_rates لا يحتوي على id، المفتاح (base, quote, effective_date).
    """
    # هل يوجد صف لهذا (base, quote, effective_date)؟
    q_sel = text("""
        SELECT 1
        FROM fx_rates
        WHERE base = :b AND quote = :q AND effective_date = :d
        LIMIT 1
    """)
    row = db.execute(q_sel, {"b": base, "q": quote, "d": day}).fetchone()

    if row:
        # حدّث السطر باستخدام المفتاح المركّب
        db.execute(
            text("""
                UPDATE fx_rates
                SET rate = :r
                WHERE base = :b AND quote = :q AND effective_date = :d
            """),
            {"r": rate, "b": base, "q": quote, "d": day}
        )
    else:
        # أضف صف جديد
        db.add(FxRate(base=base, quote=quote, rate=rate, effective_date=day))

def _fx_fetch_today_from_api() -> dict[str, float]:
    try:
        resp = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "EUR", "symbols": "USD,CAD"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        eur_usd = float(data["rates"]["USD"])
        eur_cad = float(data["rates"]["CAD"])
    except Exception:
        # Fallback محافظ إن فشل الجلب (أرقام تقريبية – لن تمنع العمل)
        eur_usd = 1.08
        eur_cad = 1.47

    usd_eur = 1.0 / eur_usd
    cad_eur = 1.0 / eur_cad
    usd_cad = eur_cad / eur_usd
    cad_usd = 1.0 / usd_cad
    return {
        "EUR->USD": eur_usd, "USD->EUR": usd_eur,
        "EUR->CAD": eur_cad, "CAD->EUR": cad_eur,
        "USD->CAD": usd_cad, "CAD->USD": cad_usd,
        "CAD->CAD": 1.0, "USD->USD": 1.0, "EUR->EUR": 1.0,
    }


def fx_sync_today(db: Session) -> None:
    today = date.today()
    try:
        rates = _fx_fetch_today_from_api()
    except Exception:
        rates = {
            "CAD->CAD": 1.0, "USD->USD": 1.0, "EUR->EUR": 1.0,
        }  # أقل شيء لمنع الفراغ
    for k, r in rates.items():
        base, quote = k.split("->")
        _fx_upsert(db, base, quote, float(r), today)
    db.commit()


app.state.fx_last_sync_at: datetime | None = None

def _fx_ensure_daily_sync():
    """يشغَّل عند الإقلاع وأول طلب في اليوم فقط."""
    try:
        now = datetime.utcnow()
        if app.state.fx_last_sync_at and (now - app.state.fx_last_sync_at) < timedelta(hours=20):
            return
        db = SessionLocal()
        try:
            fx_sync_today(db)
            app.state.fx_last_sync_at = now
            print("[OK] FX synced")
        finally:
            db.close()
    except Exception as e:
        print("[WARN] FX sync failed:", e)

def geoip_guess_currency(request: Request) -> str:
    """
    تخمين بسيط لعملة العرض من البلد/المنطقة الموجودة في الـ session.
    نحاول قراءة geo من:
      - session["geo"]  ← الشكل الجديد
      - أو المفاتيح القديمة geo_country / geo_currency  ← fallback
    """
    try:
        sess = getattr(request, "session", {}) or {}

        # الشكل الجديد
        sess_geo = sess.get("geo") or {}
        country = (sess_geo.get("country") or "").upper()

        # fallback
        if not country:
            country = (sess.get("geo_country") or "").upper()

        if country == "CA":
            return "CAD"
        if country == "US":
            return "USD"

        euro_countries = {
            "FR","DE","ES","IT","PT","NL","BE","LU","IE","FI",
            "AT","GR","CY","EE","LV","LT","MT","SI","SK","HR"
        }
        if country in euro_countries:
            return "EUR"

        return "USD"
    except Exception:
        return "CAD"


def _fetch_rate(db: Session, base: str, quote: str) -> Optional[float]:
    """
    اقرأ سعر الصرف من جدول fx_rates.
    1) جرّب effective_date = اليوم
    2) إن لم يوجد، خذ أحدث سجل متاح لتلك العملة (أكبر effective_date)
    """
    if base == quote:
        return 1.0
    # اليوم
    today = date.today().isoformat()
    q1 = text(
        "SELECT rate FROM fx_rates WHERE base=:b AND quote=:q AND effective_date=:d LIMIT 1"
    )
    r1 = db.execute(q1, {"b": base, "q": quote, "d": today}).fetchone()
    if r1 and r1[0] is not None:
        return float(r1[0])
    # أحدث تاريخ متاح
    q2 = text(
        """
        SELECT rate FROM fx_rates
        WHERE base=:b AND quote=:q
        ORDER BY effective_date DESC
        LIMIT 1
        """
    )
    r2 = db.execute(q2, {"b": base, "q": quote}).fetchone()
    if r2 and r2[0] is not None:
        return float(r2[0])
    return None

def fx_convert(db: Session, amount: float | int | None, base: str, quote: str) -> float:
    """
    يحوّل مبلغ من base إلى quote باستخدام fx_rates.
    إن لم يجد سعراً مباشراً، يحاول via CAD كجسر (base→CAD→quote) للتغطية.
    """
    try:
        amt = float(amount or 0)
    except Exception:
        amt = 0.0
    base = (base or "CAD").upper()
    quote = (quote or "CAD").upper()
    if base == quote:
        return amt

    # مباشرة
    r = _fetch_rate(db, base, quote)
    if r:
        return amt * r

    # جسر عبر CAD
    if base != "CAD" and quote != "CAD":
        r1 = _fetch_rate(db, base, "CAD")
        r2 = _fetch_rate(db, "CAD", quote)
        if r1 and r2:
            return amt * r1 * r2

    # فشل → رجّع المبلغ كما هو
    return amt
def _convert_filter(amount, base, quote):
    db = SessionLocal()
    try:
        return fx_convert(db, amount, (base or "CAD"), (quote or "CAD"))
    finally:
        db.close()

templates.env.filters["convert"] = _convert_filter

def _format_money(amount: float | int, cur: str) -> str:
    """تنسيق بسيط للأرقام (فواصل آلاف + خانتان عشريتان) مع رمز العملة."""
    try:
        val = float(amount or 0)
    except Exception:
        val = 0.0
    s = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
    return f"{s} {cur}"

# اجعل أدوات العملة متاحة خارجياً أيضًا لو احتجت في ملفات أخرى:
app.state.fx_convert = fx_convert
app.state.supported_currencies = SUPPORTED_CURRENCIES

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

def ensure_sqlite_columns():
    """
    Hot-fix missing columns when using SQLite only (ignored on Postgres):
      - users.is_mod / users.is_deposit_manager (for mod and DM privileges)
      - users.is_support (customer support agent)  ✅ New
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
            # ===== users: is_mod / is_deposit_manager / is_support =====
            try:
                ucols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('users')").all()}
                if "is_mod" not in ucols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_mod BOOLEAN NOT NULL DEFAULT 0;")
                if "is_deposit_manager" not in ucols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_deposit_manager BOOLEAN NOT NULL DEFAULT 0;")
                if "is_support" not in ucols:  # ✅ New
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_support BOOLEAN NOT NULL DEFAULT 0;")
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

# === New: initialize users.is_mod / users.badge_admin / users.is_support columns on all backends
def ensure_users_columns():
    """
    Ensures users.is_mod, users.badge_admin, and users.is_support exist on SQLite and Postgres.
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
                if "is_support" not in cols:  # ✅ New
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_support BOOLEAN DEFAULT 0;")
            elif str(backend).startswith("postgres"):
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_mod BOOLEAN DEFAULT false;")
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS badge_admin BOOLEAN DEFAULT false;")
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_support BOOLEAN DEFAULT false;")  # ✅ New
        print("[OK] ensure_users_columns(): users.is_mod / badge_admin / is_support ready")
    except Exception as e:
        print(f"[WARN] ensure_users_columns failed: {e}")

# === New: initialize support_tickets columns to support CS/MOD/MD even if the column is not defined in the model
def ensure_support_ticket_columns():
    """
    Ensures support_tickets columns used by CS/MOD/MD:
      - queue VARCHAR(10)      ← queue routing: cs / md / mod
      - last_from VARCHAR(10)  ← 'user' / 'agent'
      - last_msg_at TIMESTAMP
      - unread_for_user BOOLEAN
      - unread_for_agent BOOLEAN
      - assigned_to_id INTEGER (FK to users.id)
      - resolved_at TIMESTAMP
      - updated_at TIMESTAMP
    Works safely on both SQLite and Postgres.
    """
    try:
        try:
            backend = engine.url.get_backend_name()
        except Exception:
            backend = getattr(getattr(engine, "dialect", None), "name", "")

        with engine.begin() as conn:
            if backend == "sqlite":
                cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('support_tickets')").all()}
                if "queue" not in cols:
                    conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN queue VARCHAR(10);")
                if "last_from" not in cols:
                    conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN last_from VARCHAR(10) NOT NULL DEFAULT 'user';")
                if "last_msg_at" not in cols:
                    conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN last_msg_at TIMESTAMP;")
                if "unread_for_user" not in cols:
                    conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN unread_for_user BOOLEAN NOT NULL DEFAULT 0;")
                if "unread_for_agent" not in cols:
                    conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN unread_for_agent BOOLEAN NOT NULL DEFAULT 1;")
                if "assigned_to_id" not in cols:
                    conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN assigned_to_id INTEGER;")
                if "resolved_at" not in cols:
                    conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN resolved_at TIMESTAMP;")
                if "updated_at" not in cols:
                    conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN updated_at TIMESTAMP;")
            elif str(backend).startswith("postgres"):
                # Postgres: use IF NOT EXISTS for each column
                conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS queue VARCHAR(10);")
                conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS last_from VARCHAR(10) NOT NULL DEFAULT 'user';")
                conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS last_msg_at TIMESTAMP NULL;")
                conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS unread_for_user BOOLEAN NOT NULL DEFAULT false;")
                conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS unread_for_agent BOOLEAN NOT NULL DEFAULT true;")
                conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS assigned_to_id INTEGER NULL;")
                conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP NULL;")
                conn.exec_driver_sql("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;")
        print("[OK] ensure_support_ticket_columns(): support_tickets ready")
    except Exception as e:
        print(f"[WARN] ensure_support_ticket_columns failed: {e}")

ensure_sqlite_columns()
ensure_users_columns()
ensure_support_ticket_columns()   # ⬅️ Now defined

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

# Show payouts enablement (optional)
PAYOUTS_ENABLED = os.getenv("ENABLE_PAYOUTS", "0") == "1"
print("[OK] payouts enabled via env" if PAYOUTS_ENABLED else "[INFO] payouts disabled (set ENABLE_PAYOUTS=1)")

# -----------------------------------------------------------------------------
# UI images (Hero + Top slider)
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
# Currency Middleware + Jinja globals/filters (NEW)
# -----------------------------------------------------------------------------
def _get_session_user(request: Request) -> Optional[dict]:
    try:
        return request.session.get("user")
    except Exception:
        return None

@app.middleware("http")
async def fx_autosync_mw(request: Request, call_next):
    _fx_ensure_daily_sync()
    return await call_next(request)


@app.middleware("http")
async def geo_session_middleware(request: Request, call_next):
    """
    يحفظ geo في شكلين:
      1) المفاتيح القديمة geo_country / geo_region / geo_currency …
      2) المفتاح الموحد session["geo"] ← المهم لعمل كل شيء
    """

    # 0) لو session غير متوفرة في scope (بعض أنواع الطلبات الخاصة) → مرّر الطلب مباشرة
    if "session" not in request.scope:
        return await call_next(request)

    # 1) لو geo مضبوط يدويًا (manual من /geo/set) → لا نغيّره أبداً
    try:
        geo_sess = request.session.get("geo")
    except AssertionError:
        # لو SessionMiddleware مش شغال لسبب ما، لا نكسر التطبيق
        return await call_next(request)

    if isinstance(geo_sess, dict) and geo_sess.get("source") == "manual":
        # المستخدم غيّر البلد يدويًا (مثلاً من /geo/set?loc=US) → نتركه كما هو
        return await call_next(request)

    # 2) الحالة العادية: نحدّث الـ geo من IP / headers / ?loc
    try:
        if not request.url.path.startswith("/webhooks/"):
            info = persist_location_to_session(request) or {}

            try:
                request.session["geo"] = {
                    "ip": info.get("ip"),
                    "country": info.get("country"),
                    "region": info.get("region"),
                    "city": info.get("city"),
                    "currency": info.get("currency"),
                    "source": info.get("source"),
                }
            except Exception:
                # لا نكسر كل الطلب لو session فشلت لأي سبب
                pass
    except Exception:
        pass

    response = await call_next(request)
    return response
@app.middleware("http")
async def currency_middleware(request: Request, call_next):
    """
    من يحدد عملة العرض؟
      1) المستخدم المسجَّل (users.display_currency) إن وجدت
      2) session["geo"]["currency"]  سواء كانت manual أو من detect_location
      3) كوكي disp_cur
      4) geoip_guess_currency (fallback)
    """
    try:
        path = request.url.path or ""

        # ❌ لا نلمس webhooks ولا مسارات geo
        if path.startswith("/webhooks/") or path.startswith("/geo/"):
            return await call_next(request)

        disp = None

        # --------- نقرأ الـ session مرة واحدة ---------
        try:
            sess = request.session or {}
        except Exception:
            sess = {}

        sess_user = sess.get("user") or {}
        geo_sess  = sess.get("geo") or {}

        # 1) المستخدم المسجَّل له أولوية أعلى من كل شيء
        cur_user = (sess_user.get("display_currency") or "").upper()
        if cur_user in SUPPORTED_CURRENCIES:
            disp = cur_user

        # 2) إن لم توجد من المستخدم → استعمل عملة الـ geo (سواء manual أو auto)
        if not disp:
            cur_geo = (geo_sess.get("currency") or "").upper()
            if cur_geo in SUPPORTED_CURRENCIES:
                disp = cur_geo

        # 3) إن لم توجد → كوكي disp_cur
        if not disp:
            cur_cookie = (request.cookies.get("disp_cur") or "").upper()
            if cur_cookie in SUPPORTED_CURRENCIES:
                disp = cur_cookie

        # 4) آخر شيء: تخمين من البلد
        if not disp:
            disp = geoip_guess_currency(request)

        # حارس أخير
        if disp not in SUPPORTED_CURRENCIES:
            disp = "CAD"

        # نجعلها متاحة للتمبليت
        request.state.display_currency = disp

        # نكمل الطلب
        response = await call_next(request)

        # نكتب الكوكي بنفس العملة التي استعملناها فعليًا
        try:
            response.set_cookie(
                "disp_cur",
                disp,
                max_age=60 * 60 * 24 * 180,
                httponly=False,
                samesite="lax",
                domain=COOKIE_DOMAIN,
                secure=HTTPS_ONLY_COOKIES,
            )
        except Exception:
            pass

        return response

    except Exception:
        # لو حصل أي خطأ، لا نكسر الموقع
        return await call_next(request)

# اجعل عملة العرض متاحة للتمبليت عبر global callable
templates.env.globals["display_currency"] = lambda request: getattr(request.state, "display_currency", "CAD")

# فلتر money(amount, cur)
def _money_filter(amount, cur="CAD"):
    return _format_money(amount, (cur or "CAD").upper())

templates.env.filters["money"] = _money_filter

# -----------------------------------------------------------------------------
# Register routers
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
app.include_router(support_router)
app.include_router(cs_routes.router)
app.include_router(mod_routes.router)
app.include_router(reviews_router)
app.include_router(md_router)
app.include_router(geo_router)  # ⬅️ New

# -----------------------------------------------------------------------------
# Legacy path → redirect to the new reports page
# -----------------------------------------------------------------------------
@app.get("/mod/reports")
def legacy_mod_reports_redirect():
    return RedirectResponse(url="/admin/reports", status_code=308)

# -----------------------------------------------------------------------------
# Public pages
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
# Sync user flags from DB into session
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
                        # ✅ New: sync customer support flag
                        try:
                            sess_user["is_support"] = bool(getattr(db_user, "is_support", False))
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
# Currency routes (NEW)
# -----------------------------------------------------------------------------
@app.get("/set-currency")
def set_currency_quick(cur: str, request: Request, db: Session = Depends(get_db)):
    """
    تغيير سريع عبر GET (من الهيدر). يتحقق ثم يكتب الكوكي،
    وإن كان المستخدم مسجّلاً يحدّث users.display_currency.
    """
    cur = (cur or "").upper()
    referer = request.headers.get("referer") or "/"
    if cur not in SUPPORTED_CURRENCIES:
        return RedirectResponse(url=referer, status_code=303)

    # اكتب الكوكي
    resp = RedirectResponse(url=referer, status_code=303)
    try:
        resp.set_cookie(
            "disp_cur",
            cur,
            max_age=60 * 60 * 24 * 180,
            httponly=False,
            samesite="lax",
            domain=COOKIE_DOMAIN,
            secure=HTTPS_ONLY_COOKIES,
        )
    except Exception:
        pass

    # حدّث المستخدم (إن وُجد)
    sess_user = request.session.get("user")
    if sess_user and "id" in sess_user:
        try:
            u = db.query(User).filter(User.id == sess_user["id"]).first()
            if u:
                u.display_currency = cur
                db.commit()
        except Exception:
            db.rollback()
    return resp

@app.post("/settings/currency")
def settings_currency(
    request: Request,
    cur: str = Form(...),
    db: Session = Depends(get_db),
):
    cur = (cur or "").upper()
    referer = request.headers.get("referer") or "/settings"

    if cur not in SUPPORTED_CURRENCIES:
        return RedirectResponse(url=referer, status_code=303)

    # --- 1) عدل المستخدم في قاعدة البيانات ---
    sess_user = request.session.get("user")
    if sess_user and "id" in sess_user:
        try:
            u = db.query(User).filter(User.id == sess_user["id"]).first()
            if u:
                u.display_currency = cur
                db.commit()

            # أيضاً عدل النسخة داخل session فوراً
            sess_user["display_currency"] = cur
            request.session["user"] = sess_user
        except Exception:
            db.rollback()

    # --- 2) اكتب الكوكي الجديدة فوراً ---
    resp = RedirectResponse(url=referer + "?cur_saved=1", status_code=303)
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

# -----------------------------------------------------------------------------
# Simple services
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
    return templates.TemplateResponse("notifications.html", {"request": request, "session_user": u, "title": "Notifications"})

@app.on_event("startup")
def _startup_fx_seed():
    _fx_ensure_daily_sync()



@app.get("/geo/debug")
def geo_debug(request: Request):
    return {
        "session_geo": request.session.get("geo"),
        "disp_cur_cookie": request.cookies.get("disp_cur"),
        "state_display_currency": getattr(request.state, "display_currency", None),
    }
