# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# اسم ملف قاعدة البيانات المحلي
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# ✅ تطبيع رابط Postgres تلقائياً ليتوافق مع psycopg v3
# - يحوّل postgres:// → postgresql+psycopg://
# - يحوّل postgresql:// → postgresql+psycopg:// (لو لم يكن محدّد سائق)
# - يحوّل postgresql+psycopg2:// → postgresql+psycopg://
if DB_URL.startswith("postgres://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgres://"):]
elif DB_URL.startswith("postgresql+psycopg2://"):
    DB_URL = DB_URL.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
elif DB_URL.startswith("postgresql://") and "+psycopg" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# إعداد الاتصال (مع خيار sqlite الآمن للخيوط)
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
    pool_pre_ping=True,  # ✅ مفيد مع اتصالات Render/السيرفرات البعيدة
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ✅ هذا هو الـ Base الوحيد الذي يجب استعماله في بقية المشروع
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
