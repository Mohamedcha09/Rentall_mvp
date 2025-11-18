# app/utils.py
from passlib.context import CryptContext

# Support multiple schemes so verify can handle legacy hashes
# Default to bcrypt_sha256 (automatically avoids the 72-byte limit)
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt", "pbkdf2_sha256"],
    default="bcrypt_sha256",
    deprecated="auto",
)

# Optional limits for password input from forms
BCRYPT_MAX_BYTES = 72
MAX_FORM_PASSWORD_CHARS = 128

def _truncate_for_bcrypt(password: str) -> str:
    """
    Fallback truncation only if verification/hashing uses classic bcrypt.
    bcrypt_sha256 doesn’t need this, but it won’t hurt.
    """
    if password is None:
        return ""
    b = password.encode("utf-8")
    if len(b) <= BCRYPT_MAX_BYTES:
        return password
    return b[:BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore")

def hash_password(password: str) -> str:
    """
    Create a new hash using the CryptContext default (bcrypt_sha256).
    """
    safe = password or ""
    try:
        return pwd_context.hash(safe)
    except Exception:
        # Rare fallback in unusual environments
        return pwd_context.hash(_truncate_for_bcrypt(safe))

def verify_password(plain: str, hashed: str) -> bool:
    """
    Verification automatically supports bcrypt_sha256, bcrypt, and pbkdf2_sha256.
    """
    try:
        # Try directly (if the hash is bcrypt_sha256 or pbkdf2_sha256)
        if pwd_context.verify(plain or "", hashed or ""):
            return True
        # Second attempt with truncation in case the hash is classic bcrypt
        return pwd_context.verify(_truncate_for_bcrypt(plain or ""), hashed or "")
    except Exception:
        return False

# ===== Categories =====
CATEGORIES = [
    {"key": "vehicle",     "label": "Vehicles"},
    {"key": "housing",     "label": "Housing & Stays"},
    {"key": "electronics", "label": "Electronics"},
    {"key": "furniture",   "label": "Furniture"},
    {"key": "clothing",    "label": "Clothing"},
    {"key": "tools",       "label": "Tools & Equipment"},
    {"key": "other",       "label": "Other"},
]

def category_label(key: str) -> str:
    for c in CATEGORIES:
        if c["key"] == key:
            return c["label"]
    return "Other"


def fx_convert(amount: float, base: str, quote: str, rates: dict):
    if base == quote:
        return round(amount, 2)
    key = (base, quote)
    rate = rates.get(key)
    if not rate:
        return round(amount, 2)
    return round(amount * rate, 2)


# ============================================
# Display currency helper (GLOBAL)
# ============================================
def display_currency(request):
    """
    دالة عامة لقراءة عملة العرض من:
    1) إعدادات الحساب session.user.display_currency
    2) GEO session.geo.currency
    3) الكوكي disp_cur
    4) افتراضي CAD
    """

    allowed = {"CAD", "USD", "EUR"}

    # --- session ---
    try:
        sess = request.session or {}
    except Exception:
        sess = {}

    sess_user = sess.get("user") or {}
    geo_sess  = sess.get("geo") or {}

    # 1) user setting
    cur1 = str(sess_user.get("display_currency") or "").upper()
    if cur1 in allowed:
        request.state.display_currency = cur1
        return cur1

    # 2) geo
    cur2 = str(geo_sess.get("currency") or "").upper()
    if cur2 in allowed:
        request.state.display_currency = cur2
        return cur2

    # 3) cookie
    try:
        cur3 = str(request.cookies.get("disp_cur") or "").upper()
    except Exception:
        cur3 = ""
    if cur3 in allowed:
        request.state.display_currency = cur3
        return cur3

    # 4) fallback
    request.state.display_currency = "CAD"
    return "CAD"
