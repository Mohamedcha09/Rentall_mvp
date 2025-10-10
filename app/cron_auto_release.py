# app/cron_auto_release.py
from __future__ import annotations
from datetime import datetime, timedelta
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, User
from .notifications_api import push_notification, notify_admins

router = APIRouter(tags=["admin"])

# إعداد Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# نفس النافذة الزمنية المعتمدة: 48 ساعة بعد الإرجاع
AUTO_RELEASE_WINDOW_HOURS = 48


def _can_auto_release(bk: Booking, now: datetime) -> bool:
    """
    الشروط:
      - الحجز مُعلّم مُرجع returned/in_review
      - يوجد تفويض وديعة deposit_hold_intent_id
      - لا يوجد نزاع مفتوح (deposit_status != 'in_dispute')
      - مضت 48 ساعة على returned_at دون بلاغ
    """
    if not getattr(bk, "returned_at", None):
        return False
    if getattr(bk, "deposit_status", None) in ("in_dispute", "partially_withheld", "claimed"):
        return False
    if getattr(bk, "deposit_hold_intent_id", None) in (None, ""):
        return False
    if getattr(bk, "status", None) not in ("returned", "in_review"):
        return False

    try:
        deadline = bk.returned_at + timedelta(hours=AUTO_RELEASE_WINDOW_HOURS)
        return now >= deadline
    except Exception:
        return False


def _do_release(bk: Booking) -> None:
    """
    يلغي تفويض الوديعة ويرمز الحالات محليًا.
    """
    pi_id = getattr(bk, "deposit_hold_intent_id", None)
    if not pi_id:
        return

    # محاولة إلغاء التفويض على Stripe (أمان: نتجنب كسر المهمة عند أي خطأ)
    try:
        if stripe.api_key:
            stripe.PaymentIntent.cancel(pi_id)
    except Exception:
        # تجاهل بهدوء—قد يكون مُلغى مسبقًا
        pass

    # تحديث حالة الوديعة والحجز
    try:
        bk.deposit_status = "refunded"
        bk.deposit_charged_amount = 0
    except Exception:
        pass

    # إن كان الحجز ما زال returned/in_review نعتبره مكتمل
    try:
        if getattr(bk, "status", None) in ("returned", "in_review"):
            bk.status = "completed"
    except Exception:
        pass

    # طابع زمني للتحديث
    try:
        bk.updated_at = datetime.utcnow()
    except Exception:
        pass


@router.get("/admin/run/auto-release")
def run_auto_release(
    dry: bool = Query(True, description="وضع التجربة فقط دون تنفيذ فعلي على Stripe/DB"),
    db: Session = Depends(get_db),
):
    """
    لتشغيل الإفراج التلقائي يدويًا من الأدمن أثناء الاختبار.
    - يمرّ على الحجوزات المستحقة ويُلغي تفويض الوديعة إذا انقضت 48 ساعة بعد الإرجاع بدون نزاع.
    - إذا كان dry=true لا يُجري التغييرات، فقط يُرجع ما كان سيفعله.
    """
    # مبدئيًا أي مستخدم يستطيع طلب هذا المسار؟ في الإنتاج اربطه بدور الأدمن فقط.
    now = datetime.utcnow()

    # مرشّح أساسي لتقليل النتائج
    q = (
        db.query(Booking)
        .filter(
            Booking.returned_at.isnot(None),
            Booking.deposit_hold_intent_id.isnot(None),
            Booking.deposit_status.is_(None) | Booking.deposit_status.in_(["held", "refunded", "none", "in_review"]),
            Booking.status.in_(["returned", "in_review"]),
        )
        .order_by(Booking.returned_at.asc())
    )
    candidates = q.all()

    to_release = [bk for bk in candidates if _can_auto_release(bk, now)]
    count = 0
    ids = []

    if not dry:
        for bk in to_release:
            _do_release(bk)
            db.commit()
            count += 1
            ids.append(bk.id)

            # تنبيهات لأطراف الحجز
            try:
                push_notification(
                    db,
                    bk.renter_id,
                    "إفراج وديعة تلقائي",
                    f"أُفرجت وديعة الحجز #{bk.id} تلقائيًا بعد انتهاء مهلة الاعتراض.",
                    f"/bookings/flow/{bk.id}",
                    "deposit",
                )
                push_notification(
                    db,
                    bk.owner_id,
                    "إفراج وديعة تلقائي",
                    f"تم الإفراج عن الوديعة لحجز #{bk.id} بعد انتهاء المهلة.",
                    f"/bookings/flow/{bk.id}",
                    "deposit",
                )
            except Exception:
                pass

        try:
            if count:
                notify_admins(
                    db,
                    "تشغيل الإفراج التلقائي",
                    f"أُفرج تلقائيًا عن {count} وديعة. (IDs: {ids})",
                    "/admin",
                )
        except Exception:
            pass

    return {
        "now": now.isoformat(),
        "dry": dry,
        "candidates": [bk.id for bk in candidates],
        "eligible": [bk.id for bk in to_release],
        "released_count": (count if not dry else 0),
        "released_ids": (ids if not dry else []),
        "window_hours": AUTO_RELEASE_WINDOW_HOURS,
    }