# app/webhooks.py
from __future__ import annotations
import os
import stripe
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# نحتاج جلسة DB + معالج الويبهوك الحقيقي من pay_api
from .database import SessionLocal
from .pay_api import _handle_checkout_completed  # نستخدمه كما هو

router = APIRouter()

@router.get("/stripe/webhook/ping")
def webhook_ping():
    """
    فحص سريع أن المسار شغّال (لا يتطلب توقيع).
    """
    return {"ok": True, "msg": "stripe webhook endpoint is alive"}

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    هذا هو مسار الويبهوك الفعّال المربوط في لوحة Stripe.
    - نتحقق من التوقيع باستخدام STRIPE_WEBHOOK_SECRET من .env
    - عند checkout.session.completed نستدعي المنطق الحقيقي لتحديث الحجز
      الموجود في pay_api._handle_checkout_completed
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        return JSONResponse({"error": "Missing STRIPE_WEBHOOK_SECRET"}, status_code=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        # فشل التحقق من التوقيع / بارس
        return JSONResponse({"error": str(e)}, status_code=400)

    # لوج تشخيصي
    try:
        print("✅ Webhook received:", event.get("type"))
    except Exception:
        pass

    processed = False
    # نفتح جلسة DB مؤقتة لاستدعاء منطق التحديث
    db = SessionLocal()
    try:
        if event.get("type") == "checkout.session.completed":
            session_obj = event["data"]["object"]
            # استدعاء المعالجة الحقيقية داخل pay_api
            _handle_checkout_completed(session_obj, db)
            processed = True
        # يمكنك إضافة أنواع أخرى إذا رغبت، لكن غير ضروري الآن
    finally:
        db.close()

    return JSONResponse({"received": True, "processed": processed})