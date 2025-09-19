# app/main.py
import os
import difflib
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi import Request, Depends, Form

from .database import Base, engine, SessionLocal, get_db
from .models import User, Item

# استيراد الروترات
from .auth import router as auth_router
from .admin import router as admin_router
from .items import router as items_router
from .messages import router as messages_router, unread_count
from .ratings import router as ratings_router
from .profiles import router as profiles_router
from .utils import CATEGORIES, category_label
from .activate import router as activate_router
from .freeze import router as freeze_router
from .payments import router as payments_router
from .checkout import router as checkout_router
from .pay_api import router as pay_api_router
from .payout_connect import router as payout_connect_router
from .webhooks import router as webhooks_router

# NOTE: لا نستورد payouts مباشرةً حتى لا ينهار السيرفر على Render
# from .payouts import router as payouts_router
from .disputes import router as disputes_router
from .bookings import router as bookings_router
# from .payouts import router as payouts_router  # (مكررة في كودك الأصلي)

load_dotenv()

app = FastAPI()

# جلسات (مطلوب لتخزين session_user)
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "dev-secret"))

# مجلّدات static و uploads
BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(os.path.dirname(BASE_DIR), "uploads")
# تأكد من وجود مجلد الرفع على Render
os.makedirs(UPLOADS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# القوالب
templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.templates = templates

# إنشاء الجداول
Base.metadata.create_all(bind=engine)

# يضيف مستخدم admin افتراضيًا إذا غير موجود
def seed_admin():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@example.com").first()
        if not admin:
            from .utils import hash_password
            admin = User(first_name="Admin", last_name="User", email="admin@example.com",
                         phone="0000000000", password_hash=hash_password("admin123"),
                         role="admin", status="approved")
            db.add(admin)
            db.commit()
    finally:
        db.close()

seed_admin()

# ===== تفعيل payouts اختياريًا (حتى لا ينهار التطبيق بدون stripe) =====
PAYOUTS_ENABLED = os.getenv("ENABLE_PAYOUTS", "0") == "1"
payouts_router = None
if PAYOUTS_ENABLED:
    try:
        import stripe  # تأكد وجود المكتبة
        from .payouts import router as _payouts_router
        payouts_router = _payouts_router
        print("[OK] payouts router enabled")
    except Exception as e:
        print(f"[SKIP] payouts router (enabled but failed): {e}")
else:
    print("[INFO] payouts router disabled (set ENABLE_PAYOUTS=1 & STRIPE_SECRET_KEY to enable)")

# تسجيل الروترات — هذا هو المهم لمنع 404
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(items_router)
app.include_router(messages_router)
app.include_router(ratings_router)
app.include_router(profiles_router)
app.include_router(activate_router)
app.include_router(freeze_router)
app.include_router(payments_router)
app.include_router(checkout_router)
app.include_router(pay_api_router)
app.include_router(payout_connect_router)
app.include_router(webhooks_router)

# app.include_router(payouts_router)  # سنحميها بشرط بالأسفل
app.include_router(disputes_router)
app.include_router(bookings_router)
# app.include_router(payouts_router)  # كانت مكررة—نحافظ عليها مشروطة أيضاً

# ضمّن payouts إن توفّر
if payouts_router:
    app.include_router(payouts_router)
if payouts_router:  # نفس التكرار الموجود عندك، ولكن محميّ
    app.include_router(payouts_router)

# الصفحة الرئيسية تعرض العناصر (مع تصنيف اختياري ?category=vehicle مثلا)
@app.get("/")
def home(request: Request,
         db: Session = Depends(get_db),
         category: str = None,
         q: str = None,        # البحث النصي عن المنتج (title/description)
         city: str = None):    # اسم المدينة المراد التصفية بها
    # إذا لم يرَ المستخدم الترحيب بعد، نذهب للـ /welcome
    if not request.cookies.get("seen_welcome"):
        return RedirectResponse(url="/welcome", status_code=303)

    query = db.query(Item).filter(Item.is_active == "yes")
    current_category = None
    if category:
        query = query.filter(Item.category == category)
        current_category = category

    # إذا كان المستخدم يعطينا نص بحث، فلتر على العنوان أو الوصف (substring)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                Item.title.ilike(pattern),
                Item.description.ilike(pattern)
            )
        )

    # ====== دعم البحث بالمدينة مع مطابقة مرنة (fuzzy) ======
    if city:
        # احصل على قائمة المدن المميزة (lowercased)
        cities_raw = db.query(func.lower(Item.city)).distinct().all()
        cities = [c[0] for c in cities_raw if c[0]]
        requested = (city or "").strip().lower()
        matched_cities = []
        if requested:
            # استخدام difflib لمطابقة مرنة؛ cutoff يمكن تعديله (0.6 .. 0.8)
            matches = difflib.get_close_matches(requested, cities, n=8, cutoff=0.6)
            if matches:
                matched_cities = matches
            else:
                # لا توجد مطابقة قريبة: حاول بحث نصي كاحتياط
                # نستخدم ilike ليتعامل مع حالات تحتوي على نص جزئي
                query = query.filter(Item.city.ilike(f"%{city}%"))

        if matched_cities:
            # فلتر العناصر التي تنتمي لإحدى المدن المطابقة
            # ملاحظة: func.lower(Item.city) لأننا خزننا matched_cities بصيغة lower
            query = query.filter(func.lower(Item.city).in_(matched_cities))

    # عناصر عشوائية في كل تحميل للصفحة (أو بناءً على الفلاتر)
    items = query.order_by(func.random()).limit(20).all()

    # أضف خواص مساعدة للقوالب
    for it in items:
        it.category_label = category_label(it.category)

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "title": "Marketplace",
            "items": items,
            "categories": CATEGORIES,
            "current_category": current_category,
            "session_user": request.session.get("user"),
            # للحفاظ على قيم الحقول في الفورم بعد البحث
            "search_q": q or "",
            "search_city": city or "",
        },
    )

# صفحة ملفّي
@app.get("/profile")
def profile(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    user = db.query(User).get(u["id"])
    return templates.TemplateResponse("profile.html", {"request": request, "title": "صفحتي", "user": user, "session_user": u})

@app.get("/welcome", response_class=HTMLResponse)
def welcome(request: Request):
    u = request.session.get("user")
    return templates.TemplateResponse(
        "welcome.html",
        {"request": request, "session_user": u}
    )

# زر "ابدأ" من الترحيب → يضع كوكي ويذهب للرئيسية
@app.post("/welcome/continue")
def welcome_continue():
    resp = RedirectResponse(url="/", status_code=303)
    # سنة كاملة
    resp.set_cookie("seen_welcome", "1", max_age=60*60*24*365, httponly=False, samesite="lax")
    return resp

@app.get("/about", response_class=HTMLResponse)
def about(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    return templates.TemplateResponse(
        "about.html",
        {"request": request, "session_user": u}
    )

# ====== NEW: API صغيرة لتحديث شارة الرسائل ======
@app.get("/api/unread_count")
def api_unread_count(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return JSONResponse({"count": 0})
    return JSONResponse({"count": unread_count(u["id"], db)})

# ====== Middleware: يضيف unread_messages للقوالب ======
@app.middleware("http")
async def sync_user_flags(request: Request, call_next):
    """
    يزامن قيم session_user مع قاعدة البيانات في كل طلب
    (خصوصاً is_verified) حتى تظهر الشارة الزرقاء فوراً
    بدون الحاجة لإعادة تسجيل الدخول.
    """
    try:
        # تأكد أن عندنا سيشن
        if hasattr(request, "session"):
            sess_user = request.session.get("user")
            if sess_user and "id" in sess_user:
                # افتح جلسة DB سريعة
                db_gen = get_db()
                db: Session = next(db_gen)
                try:
                    db_user = db.query(User).get(sess_user["id"])
                    if db_user:
                        # حدّث القيم المهمة
                        sess_user["is_verified"] = bool(db_user.is_verified)
                        sess_user["role"] = db_user.role
                        sess_user["status"] = db_user.status
                        # أعد حفظها في السيشن
                        request.session["user"] = sess_user
                finally:
                    # أغلق gen
                    try:
                        next(db_gen)
                    except StopIteration:
                        pass
    except Exception:
        # ما نكسرش الطلب لو صار خطأ
        pass

    response = await call_next(request)
    return response

# ====== Health Check مفيد لـ Render ======
@app.get("/healthz")
def healthz():
    return {"status": "up"}
