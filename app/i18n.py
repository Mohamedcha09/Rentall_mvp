# app/i18n.py
import gettext
import os
from fastapi import Request, Response

# مجلد ملفات الترجمة
LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")

# اللغات المتاحة
SUPPORTED = ("ar", "en", "fr")

# لغة افتراضية
DEFAULT_LANG = "ar"

COOKIE_NAME = "lang"

def pick_lang_from_header(accept_language: str) -> str:
    if not accept_language:
        return DEFAULT_LANG
    header = accept_language.lower()
    for lang in SUPPORTED:
        if header.startswith(lang) or f"{lang}-" in header:
            return lang
    return DEFAULT_LANG

def get_lang_from_request(request: Request) -> str:
    # 1) من الكوكيز
    if COOKIE_NAME in request.cookies:
        lang = request.cookies[COOKIE_NAME]
        if lang in SUPPORTED:
            return lang
    # 2) من الهيدر
    return pick_lang_from_header(request.headers.get("Accept-Language", ""))

def get_translator(lang: str):
    try:
        return gettext.translation(
            domain="messages",
            localedir=LOCALES_DIR,
            languages=[lang],
            fallback=True,  # لو ناقصة ترجمة
        )
    except Exception:
        return gettext.NullTranslations()

def set_lang_cookie(response: Response, lang: str):
    response.set_cookie(
        key=COOKIE_NAME,
        value=lang,
        max_age=60*60*24*365,
        path="/",
        samesite="lax",
    )
