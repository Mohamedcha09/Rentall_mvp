# app/webhooks.py
import os, stripe
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/stripe/webhook/ping")
def webhook_ping():
    """
    فحص سريع أن المسار شغّال (لا يتطلب توقيع).
    """
    return {"ok": True, "msg": "stripe webhook endpoint is alive"}

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        return JSONResponse({"error": "Missing STRIPE_WEBHOOK_SECRET"}, status_code=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        # نفس السطر الأصلي مع إرجاع خطأ واضح
        return JSONResponse({"error": str(e)}, status_code=400)

    # ✅ السطر الأصلي (لا نحذفه)
    print("✅ Webhook received:", event["type"])

    # ===== إضافات غير مدمّرة: لوج تفصيلي عندما تكتمل جلسة الدفع =====
    try:
        if event.get("type") == "checkout.session.completed":
            session = event["data"]["object"]
            intent_id = session.get("payment_intent")
            kind = None
            booking_id = None
            try:
                if intent_id:
                    pi = stripe.PaymentIntent.retrieve(intent_id)
                    md = dict(pi.metadata or {})
                    kind = md.get("kind")
                    booking_id = md.get("booking_id")
            except Exception as _e:
                print("⚠️ couldn't retrieve PaymentIntent for logging:", _e)

            print(
                "[Stripe][checkout.session.completed] "
                f"intent={intent_id} kind={kind} booking_id={booking_id}"
            )
    except Exception as e:
        # لا نكسر الاستدعاء بسبب لوج فقط
        print("⚠️ logging block error:", e)

    # لا نحدّث قاعدة البيانات هنا، التحديث الفعلي يتم في pay_api.py (/webhooks/stripe)
    return {"received": True}