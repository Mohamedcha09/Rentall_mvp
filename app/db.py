# app/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("DATABASE_URI")
    or "sqlite:///./app.db"
)

# future=True to use SQLAlchemy 2.x API
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
