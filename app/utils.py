# app/utils.py
from passlib.context import CryptContext

# ===== إعداد التشفير =====
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ===== حدود bcrypt =====
BCRYPT_MAX_BYTES = 72          # bcrypt يقبل حتى 72 بايت فقط
MAX_FORM_PASSWORD_CHARS = 128  # حد منطقي لطول إدخال كلمة السر من الفورم

def _truncate_for_bcrypt(password: str) -> str:
    """
    يقص كلمة السر إلى 72 بايت (utf-8) حتى لا يرمي bcrypt ValueError.
    """
    if password is None:
        return ""
    b = password.encode("utf-8")
    if len(b) <= BCRYPT_MAX_BYTES:
        return password
    # قص آمن عند حدود البايتات ثم تجاهل أي جزء حرف انقطع
    return b[:BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore")

def hash_password(password: str) -> str:
    """
    نستخدم نفس القص قبل الهاش للحفاظ على الاتساق مع التحقق.
    """
    safe = _truncate_for_bcrypt(password or "")
    return pwd_context.hash(safe)

def verify_password(plain: str, hashed: str) -> bool:
    """
    نتحقق بعد قص كلمة السر إلى 72 بايت، ونتعامل مع أي أخطاء بهدوء.
    """
    try:
        safe = _truncate_for_bcrypt(plain or "")
        return pwd_context.verify(safe, hashed or "")
    except Exception:
        # أي خطأ (مثل backend أو هاش فاسد) → نرجّع False بدل 500
        return False

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