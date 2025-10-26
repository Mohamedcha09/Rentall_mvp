# app/database.py
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# =========================================================
# 1) قراءة رابط قاعدة البيانات + تطبيع سائق Postgres تلقائياً
# =========================================================
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# psycopg (v3) هو السائق الموصى به الآن لـ SQLAlchemy مع Postgres
# نحول تلقائياً أي صيغة قديمة إلى postgresql+psycopg://
if DB_URL.startswith("postgres://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgres://"):]
elif DB_URL.startswith("postgresql+psycopg2://"):
    DB_URL = DB_URL.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
elif DB_URL.startswith("postgresql://") and "+psycopg" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# =========================================================
# 2) إنشاء الـ Engine و Session
# =========================================================
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
    pool_pre_ping=True,  # مفيد جداً مع استضافات بعيدة (Render وغيرها)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# الـ Base الوحيد المستخدم في بقية المشروع
Base = declarative_base()


def get_db():
    """Dependency لحقن جلسة DB داخل المسارات."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================================================
# 3) Helpers للتوافق (استكشاف نوع المحرك وفحص الأعمدة بأمان)
# =========================================================
def _backend_name() -> str:
    try:
        # متاح في SQLAlchemy >=2
        return getattr(engine.url, "get_backend_name", lambda: "")()
    except Exception:
        return getattr(getattr(engine, "dialect", None), "name", "") or ""


def _has_column(table: str, col: str) -> bool:
    """
    يفحص وجود عمود في الجدول مع دعم Postgres و SQLite.
    لو حدث خطأ نعيد False (أفضل من أن نتصرف كأن العمود موجود).
    """
    backend = _backend_name()
    try:
        with engine.begin() as conn:
            if str(backend).startswith("postgres"):
                rows = conn.exec_driver_sql(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=:t
                    """,
                ).mappings().params(t=table).all()
                return col in [r["column_name"] for r in rows]
            else:
                rows = conn.exec_driver_sql(f"PRAGMA table_info('{table}')").all()
                # في SQLite: (cid, name, type, notnull, dflt_value, pk)
                return any(r[1] == col for r in rows)
    except Exception:
        return False


# =========================================================
# 4) Hotfix: تأكيد أعمدة reports (لو كانت ناقصة في Postgres قديم)
# =========================================================
def _ensure_reports_columns() -> None:
    """
    يضيف بأمان الأعمدة 'tag' و 'updated_at' في جدول reports على Postgres فقط
    (باستخدام IF NOT EXISTS). لا يفعل شيئاً على SQLite.
    آمن حتى لو كانت الأعمدة موجودة (يتجاهل).
    """
    backend = _backend_name()
    if not str(backend).startswith("postgres"):
        return
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS tag VARCHAR(24);")
            conn.exec_driver_sql("ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;")
    except Exception as e:
        # لا نوقف التطبيق بسبب هذا — فقط نطبع تحذيراً
        print("[WARN] ensure reports columns failed:", e)


# =========================================================
# 5) Hotfix: تفعيل جميع صلاحيات الإدمن تلقائياً عند الإقلاع
# =========================================================
def _promote_all_admins() -> None:
    """
    يفعّل كل الصلاحيات/الأعلام لحسابات role='admin' بدون كسر قواعد
    لا تحتوي تلك الأعمدة — نضبط فقط الأعمدة الموجودة فعلياً.
    """
    sets = []

    if _has_column("users", "is_verified"):
        sets.append("is_verified = TRUE")
    if _has_column("users", "status"):
        sets.append("status = 'active'")
    if _has_column("users", "is_mod"):
        sets.append("is_mod = TRUE")
    if _has_column("users", "badge_admin"):
        sets.append("badge_admin = TRUE")
    if _has_column("users", "is_deposit_manager"):
        sets.append("is_deposit_manager = TRUE")
    if _has_column("users", "payouts_enabled"):
        sets.append("payouts_enabled = TRUE")
    if _has_column("users", "verified_at"):
        # لا نغيّر verified_at إن كان له قيمة — نملأه فقط لو كان NULL
        sets.append("verified_at = COALESCE(verified_at, CURRENT_TIMESTAMP)")

    if not sets:
        return  # لا يوجد أعمدة نضبطها، نخرج بهدوء

    set_sql = ", ".join(sets)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(f"""
                    UPDATE users
                    SET {set_sql}
                    WHERE LOWER(COALESCE(role, '')) = 'admin'
                """)
            )
    except Exception as e:
        print("[WARN] promote admins failed:", e)


# =========================================================
# 6) نفّذ الهوت-فيكسات عند تحميل الموديول
# =========================================================
try:
    _ensure_reports_columns()
except Exception as _e:
    print("[WARN] reports hotfix error:", _e)

try:
    _promote_all_admins()
except Exception as _e:
    print("[WARN] promote admins hotfix error:", _e)