# app/webhooks.py
import os
import stripe
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .database import SessionLocal
# سنستعمل المعالج الحقيقي من pay_api
from .pay_api import _handle_checkout_completed

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
    هذا المسار يستقبل Webhooks من Stripe (عندك الإندبوينت مضبوط عليه).
    بعد التحقق من التوقيع، نحول الحدث إلى نفس المعالج المستخدم داخل pay_api.py
    كي يتم تحديث الحجز في قاعدة البيانات، وبالتالي تختفي الأزرار تلقائيًا.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        return JSONResponse({"error": "Missing STRIPE_WEBHOOK_SECRET"}, status_code=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # لوج تشخيصي مفيد
    try:
        print("✅ Webhook received:", event.get("type"))
    except Exception:
        pass

    # >>> أهم سطرين: استدعاء نفس منطق التحديث الحقيقي
    if event.get("type") == "checkout.session.completed":
        session_obj = event["data"]["object"]
        db = SessionLocal()
        try:
            _handle_checkout_completed(session_obj, db)
        finally:
            db.close()

    return {"received": True}