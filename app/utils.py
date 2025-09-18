# app/utils.py
from passlib.context import CryptContext

# تشفير/تحقق كلمات السر
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# ===== التصنيفات (للتصفية في /items و /owner/items/new) =====
CATEGORIES = [
    {"key": "vehicle",     "label": "مركبات"},
    {"key": "housing",     "label": "سكن وإقامات"},
    {"key": "electronics", "label": "إلكترونيات"},
    {"key": "furniture",   "label": "أثاث"},
    {"key": "clothing",    "label": "ملابس"},
    {"key": "tools",       "label": "معدات وأدوات"},
    {"key": "other",       "label": "أخرى"},
]

def category_label(key: str) -> str:
    for c in CATEGORIES:
        if c["key"] == key:
            return c["label"]
    return "أخرى"
