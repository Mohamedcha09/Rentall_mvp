# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# استخدم DATABASE_URL من البيئة إن وُجد، وإلا SQLite محلي
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# إذا كنا على SQLite نضيف check_same_thread=False، غير ذلك بدون connect_args
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ✅ هذا هو Declarative Base الصحيح
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()