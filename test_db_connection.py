from sqlalchemy import text
from app.database import SessionLocal

try:
    db = SessionLocal()
    result = db.execute(text("SELECT current_database();")).scalar()
    print(f"✅ Connected to database: {result}")
    db.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
