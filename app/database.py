import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# اسم ملف قاعدة البيانات: app.db
DB_URL = "sqlite:///./app.db"

# إعدادات الاتصال
engine = create_engine(
    DB_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
