# app/utils.py
from passlib.context import CryptContext

# ندعم عدة مخططات حتى يستطيع verify التعامل مع هاشات قديمة
# ونضبط الافتراضي على bcrypt_sha256 (يتفادى حد 72 بايت تلقائياً)
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt", "pbkdf2_sha256"],
    default="bcrypt_sha256",
    deprecated="auto",
)

# حدود اختيارية لإدخال كلمة السر من الفورم
BCRYPT_MAX_BYTES = 72
MAX_FORM_PASSWORD_CHARS = 128

def _truncate_for_bcrypt(password: str) -> str:
    """
    قص احتياطي فقط إذا تم التحقق/الهاش عبر bcrypt التقليدي.
    bcrypt_sha256 لا يحتاج هذا، لكن لن يضر.
    """
    if password is None:
        return ""
    b = password.encode("utf-8")
    if len(b) <= BCRYPT_MAX_BYTES:
        return password
    return b[:BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore")

def hash_password(password: str) -> str:
    """
    إنشاء هاش جديد باستخدام default في الـ CryptContext (bcrypt_sha256).
    """
    safe = password or ""
    try:
        return pwd_context.hash(safe)
    except Exception:
        # fallback نادر في بيئات غريبة
        return pwd_context.hash(_truncate_for_bcrypt(safe))

def verify_password(plain: str, hashed: str) -> bool:
    """
    التحقق يدعم bcrypt_sha256 و bcrypt و pbkdf2_sha256 تلقائياً.
    """
    try:
        # المحاولة مباشرة (لو كان الهاش bcrypt_sha256 أو pbkdf2_sha256)
        if pwd_context.verify(plain or "", hashed or ""):
            return True
        # محاولة ثانية مقصوصة في حال كان الهاش bcrypt تقليدي
        return pwd_context.verify(_truncate_for_bcrypt(plain or ""), hashed or "")
    except Exception:
        return False

# ===== التصنيفات =====
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