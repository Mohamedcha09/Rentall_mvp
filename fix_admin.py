# scripts/fix_admin.py
import os
from app.database import SessionLocal
from app.models import User
from app.utils import hash_password

db = SessionLocal()
try:
    email = "admin@example.com"
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(
            first_name="Admin",
            last_name="User",
            email=email,
            phone="0000000000",
            password_hash=hash_password("admin123"),
        )
        db.add(u)
        db.commit()
        db.refresh(u)

    # اجعل الحساب أدمن ومفعّلًا بالكامل
    u.role = "admin"
    u.status = "approved"
    u.is_verified = True
    u.is_deposit_manager = True
    u.is_mod = True
    u.badge_admin = True
    u.payouts_enabled = True

    db.add(u)
    db.commit()
    print("[OK] admin fixed and fully enabled")
finally:
    db.close()
