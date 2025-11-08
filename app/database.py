# app/database.py
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# =========================================================
# 1) Read the database URL + automatically normalize Postgres driver
# =========================================================
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# psycopg (v3) is the recommended driver for SQLAlchemy with Postgres
# Automatically convert any legacy format to postgresql+psycopg://
if DB_URL.startswith("postgres://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgres://"):]
elif DB_URL.startswith("postgresql+psycopg2://"):
    DB_URL = DB_URL.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
elif DB_URL.startswith("postgresql://") and "+psycopg" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# =========================================================
# 2) Create Engine and Session
# =========================================================
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
    pool_pre_ping=True,  # Very useful for remote hosts (Render, etc.)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# The only Base used throughout the project
Base = declarative_base()


def get_db():
    """Dependency to inject DB session inside routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================================================
# 3) Helpers for compatibility (engine detection and safe column checking)
# =========================================================
def _backend_name() -> str:
    try:
        # Available in SQLAlchemy >=2
        return getattr(engine.url, "get_backend_name", lambda: "")()
    except Exception:
        return getattr(getattr(engine, "dialect", None), "name", "") or ""


def _has_column(table: str, col: str) -> bool:
    backend = _backend_name()
    try:
        with engine.begin() as conn:
            if str(backend).startswith("postgres"):
                rows = conn.exec_driver_sql(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%(t)s
                    """,
                    {"t": table},
                ).mappings().all()
                return col in [r["column_name"] for r in rows]
            else:
                rows = conn.exec_driver_sql(f"PRAGMA table_info('{table}')").all()
                return any(r[1] == col for r in rows)
    except Exception:
        return False

# =========================================================
# 4) Hotfix: ensure reports columns (if missing in old Postgres)
# =========================================================
def _ensure_reports_columns() -> None:
    """
    Safely adds the 'tag' and 'updated_at' columns in the reports table for Postgres only
    (using IF NOT EXISTS). Does nothing on SQLite.
    Safe even if columns already exist (ignored).
    """
    backend = _backend_name()
    if not str(backend).startswith("postgres"):
        return
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS tag VARCHAR(24);")
            conn.exec_driver_sql("ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;")
    except Exception as e:
        # Do not stop the app because of this — just print a warning
        print("[WARN] ensure reports columns failed:", e)


# =========================================================
# 5) Hotfix: automatically promote all admin privileges at startup
# =========================================================
def _promote_all_admins() -> None:
    """
    Enables all privileges/flags for accounts with role='admin' without breaking databases
    that don't contain those columns — only updates existing ones.
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
        # Do not modify verified_at if it already has a value — fill only if NULL
        sets.append("verified_at = COALESCE(verified_at, CURRENT_TIMESTAMP)")

    if not sets:
        return  # No columns to set, exit quietly

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
# 6) Execute hotfixes when module loads
# =========================================================
try:
    _ensure_reports_columns()
except Exception as _e:
    print("[WARN] reports hotfix error:", _e)

try:
    _promote_all_admins()
except Exception as _e:
    print("[WARN] promote admins hotfix error:", _e)
