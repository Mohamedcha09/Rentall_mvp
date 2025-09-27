# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# اسم ملف قاعدة البيانات المحلي
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# إعداد الاتصال (مع خيار sqlite الآمن للخيوط)
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
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