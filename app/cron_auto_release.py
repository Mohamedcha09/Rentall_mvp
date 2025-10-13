# app/cron_auto_release.py
from __future__ import annotations
from datetime import datetime, timedelta
import os

import stripe
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking
from .notifications_api import push_notification, notify_admins

router = APIRouter(tags=["admin"])

# إعداد Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# نفس النافذة الزمنية المعتمدة: 48 ساعة بعد الإرجاع
AUTO_RELEASE_WINDOW_HOURS = 48

# [إضافة] مهلة ردّ المستأجر: 24 ساعة بعد قرار DM مع تعليق التنفيذ
DM_RESPONSE_WINDOW_HOURS = 24


# =======================
# أدوات مساعدة (Helpers)
# =======================
def _currency(num: int) -> str:
    try:
        return f"{int(num):,}"
    except Exception:
        return str(num)


def _stripe_capture(pi_id: str, amount: int) -> bool:
    """
    Stripe يتعامل بالمئات (cents) لذا نضرب ×100.
    """
    try:
        stripe.PaymentIntent.capture(pi_id, amount_to_capture=int(amount) * 100)
        return True
    except Exception:
        return False


def _stripe_cancel(pi_id: str) -> bool:
    try:
        stripe.PaymentIntent.cancel(pi_id)
        return True
    except Exception:
        return False


def _has_dispute_open(bk: Booking) -> bool:
    return (getattr(bk, "deposit_status", None) or "").lower() in (
        "in_dispute", "partially_withheld", "claimed"
    )


def _has_renter_replied(bk: Booking) -> bool:
    """
    يعتبر المستأجر قد ردّ إذا كان لدينا ختم زمني للرد.
    (لو لديك منطق إضافي يعتمد على وجود أدلة المستأجر، يمكنك توسيعه لاحقًا.)
    """
    return getattr(bk, "renter_response_at", None) is not None


# ==========================
# منطق الإفراج التلقائي 48h
# ==========================
def _can_auto_release(bk: Booking, now: datetime) -> bool:
    """
    الشروط:
      - الحجز مُعلّم مُرجع returned/in_review
      - يوجد تفويض وديعة deposit_hold_intent_id
      - لا يوجد نزاع مفتوح
      - مضت 48 ساعة على returned_at دون بلاغ
    """
    if not getattr(bk, "returned_at", None):
        return False
    if _has_dispute_open(bk):
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


# ======================================================
# تنفيذ قرار DM تلقائيًا بعد مهلة ردّ المستأجر (24h)
# ======================================================
def _can_execute_dm_decision(bk: Booking, now: datetime) -> bool:
    """
    الشروط العامة للتنفيذ التلقائي بعد مهلة الرد:
      - يوجد PaymentIntent (تفويض وديعة)
      - يوجد قرار DM محفوظ bk.dm_decision (withhold/partial/release)
      - الحالة الحالية للحجز: awaiting_renter (أمان)
      - لم يردّ المستأجر قبل انتهاء المهلة (renter_response_at == None)
      - تم ضبط bk.renter_response_deadline_at، وانتهت المهلة
      - لم يُنفّذ القرار سابقًا (dm_decision_at == None)
    """
    pi_id = getattr(bk, "deposit_hold_intent_id", None)
    decision = (getattr(bk, "dm_decision", None) or "").lower()
    deadline = getattr(bk, "renter_response_deadline_at", None)
    already_executed = getattr(bk, "dm_decision_at", None) is not None
    deposit_status = (getattr(bk, "deposit_status", None) or "").lower()

    if not pi_id:
        return False
    if decision not in ("withhold", "partial", "release"):
        return False
    # ✅ تنفيذ تلقائي فقط عندما نكون بانتظار المستأجر
    if deposit_status != "awaiting_renter":
        return False
    # ✅ إيقاف التنفيذ التلقائي إذا المستأجر ردّ قبل انتهاء المهلة
    if _has_renter_replied(bk):
        return False
    if not deadline:
        return False
    if already_executed:
        return False

    try:
        return now >= deadline
    except Exception:
        return False


def _execute_dm_decision(db: Session, bk: Booking) -> str:
    """
    ينفّذ قرار DM المحفوظ في الحجز بعد انتهاء مهلة ردّ المستأجر:
      - withhold/partial: التقاط dm_decision_amount (ويُفرج Stripe تلقائياً عن الباقي)
      - release: إلغاء تفويض الوديعة
    يُحدّث حالات الحجز ويرسل إشعارات للطرفين.
    يعيد نصًا مختصرًا عمّا حصل.
    """
    pi_id = getattr(bk, "deposit_hold_intent_id", None)
    decision = (getattr(bk, "dm_decision", None) or "").lower()
    amount = int(getattr(bk, "dm_decision_amount", 0) or 0)
    deposit_total = int(
        (getattr(bk, "deposit_amount", None)
         or getattr(bk, "hold_deposit_amount", None)
         or 0)
    )

    if not pi_id or not decision:
        return "skipped:no_pi_or_decision"

    if decision in ("withhold", "partial"):
        if amount <= 0:
            return "skipped:zero_amount"

        ok = _stripe_capture(pi_id, amount)
        if not ok:
            return "error:stripe_capture_failed"

        # تحديث الحالة
        try:
            bk.deposit_charged_amount = amount
            if deposit_total > 0 and amount >= deposit_total:
                bk.deposit_status = "claimed"
            else:
                bk.deposit_status = "partially_withheld"
            bk.status = "closed"
            bk.dm_decision_at = datetime.utcnow()
            bk.updated_at = datetime.utcnow()
        except Exception:
            pass

        db.commit()

        # إشعارات
        try:
            push_notification(
                db, bk.owner_id,
                "تم تنفيذ قرار الخصم",
                f"تم تعويضك بمبلغ { _currency(amount) } من وديعة الحجز #{bk.id}.",
                f"/bookings/flow/{bk.id}",
                "deposit",
            )
            push_notification(
                db, bk.renter_id,
                "انتهت مهلة الرد",
                f"تم خصم { _currency(amount) } من وديعتك للحجز #{bk.id} لعدم تقديم أدلة خلال المهلة.",
                f"/bookings/flow/{bk.id}",
                "deposit",
            )
            notify_admins(db, "تنفيذ قرار وديعة تلقائي", f"حجز #{bk.id} — خصم {amount}.", f"/dm/deposits/{bk.id}")
        except Exception:
            pass

        return f"captured:{amount}"

    elif decision == "release":
        ok = _stripe_cancel(pi_id)
        if not ok:
            # قد يكون التفويض منتهيًا أو مُلغى مسبقًا — نكمل التحديثات
            pass

        try:
            bk.deposit_status = "refunded"
            bk.deposit_charged_amount = 0
            bk.status = "closed"
            bk.dm_decision_at = datetime.utcnow()
            bk.updated_at = datetime.utcnow()
        except Exception:
            pass

        db.commit()

        try:
            push_notification(
                db, bk.owner_id,
                "تم إرجاع الوديعة",
                f"تقرر إرجاع وديعة الحجز #{bk.id} بعد انتهاء المهلة.",
                f"/bookings/flow/{bk.id}",
                "deposit",
            )
            push_notification(
                db, bk.renter_id,
                "تم إرجاع الوديعة",
                f"انتهت مهلة الرد، وتم إرجاع وديعتك للحجز #{bk.id}.",
                f"/bookings/flow/{bk.id}",
                "deposit",
            )
            notify_admins(db, "تنفيذ قرار وديعة تلقائي", f"حجز #{bk.id} — إرجاع كامل.", f"/dm/deposits/{bk.id}")
        except Exception:
            pass

        return "released"

    return "skipped:unknown_decision"


@router.get("/admin/run/auto-release")
def run_auto_release(
    dry: bool = Query(True, description="وضع التجربة فقط دون تنفيذ فعلي على Stripe/DB"),
    db: Session = Depends(get_db),
):
    """
    لتشغيل الإفراج التلقائي يدويًا من الأدمن أثناء الاختبار.
    - يمرّ على الحجوزات المستحقة ويُلغي تفويض الوديعة إذا انقضت 48 ساعة بعد الإرجاع بدون نزاع.
    - إذا كان dry=true لا يُجري التغييرات، فقط يُرجع ما كان سيفعله.

    [إضافة]
    - كذلك ينفّذ قرارات DM المؤجلة تلقائيًا بعد انتهاء مهلة ردّ المستأجر (24 ساعة)،
      بشرط أن تكون الحالة awaiting_renter ولم يردّ المستأجر قبل انتهاء المهلة.
    """
    now = datetime.utcnow()

    # -------------------------------
    # الجزء الأصلي: Auto Release 48h
    # -------------------------------
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

    released_count = 0
    released_ids = []

    if not dry:
        for bk in to_release:
            _do_release(bk)
            db.commit()
            released_count += 1
            released_ids.append(bk.id)

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
            if released_count:
                notify_admins(
                    db,
                    "تشغيل الإفراج التلقائي",
                    f"أُفرج تلقائيًا عن {released_count} وديعة. (IDs: {released_ids})",
                    "/admin",
                )
        except Exception:
            pass

    # -------------------------------------------------------
    # تنفيذ قرارات DM بعد انتهاء مهلة ردّ المستأجر 24h
    # -------------------------------------------------------
    q2 = (
        db.query(Booking)
        .filter(
            Booking.deposit_hold_intent_id.isnot(None),
            Booking.renter_response_deadline_at.isnot(None),
        )
        .order_by(Booking.renter_response_deadline_at.asc())
    )
    dm_candidates = q2.all()
    dm_eligible = [bk for bk in dm_candidates if _can_execute_dm_decision(bk, now)]

    dm_results = {}
    if not dry:
        for bk in dm_eligible:
            res = _execute_dm_decision(db, bk)
            dm_results[bk.id] = res

    return {
        "now": now.isoformat(),
        "dry": dry,
        # الجزء الأصلي
        "candidates": [bk.id for bk in candidates],
        "eligible": [bk.id for bk in to_release],
        "released_count": (released_count if not dry else 0),
        "released_ids": (released_ids if not dry else []),
        "window_hours": AUTO_RELEASE_WINDOW_HOURS,
        # الإضافات لقرارات DM
        "dm_candidates": [bk.id for bk in dm_candidates],
        "dm_eligible": [bk.id for bk in dm_eligible],
        "dm_window_hours": DM_RESPONSE_WINDOW_HOURS,
        "dm_results": (dm_results if not dry else {}),
    }