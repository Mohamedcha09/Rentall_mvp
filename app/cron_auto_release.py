"""
app/cron_auto_release.py
------------------------
هذا السكربت مسؤول عن "الإفراج التلقائي" عن الودائع بعد انتهاء مهلة الاعتراض (48 ساعة)
في حال لم يُفتح أي بلاغ من المالك ولم تكن هناك حالة نزاع.

يمكن تشغيله:
  - يدويًا عبر المتصفح من الراوتر:  GET /admin/run/auto-release
  - أو مجدول (cron job) كل ساعة مثلاً.

"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from sqlalchemy import and_
from app.database import SessionLocal
from app.models import Booking
from app.utils import notify_user

router = APIRouter()

AUTO_RELEASE_DELAY_HOURS = 48  # 48 ساعة بعد الإرجاع

def auto_release_logic(db):
    """
    يمرّ على جميع الحجوزات التي:
      - حالتها returned
      - ومرت 48 ساعة منذ وقت الإرجاع
      - ولم تُفتح قضية أو نزاع
      - ولم تُفرج وديعتها بعد
    ثم يعيد الوديعة للمستأجر.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=AUTO_RELEASE_DELAY_HOURS)

    bookings = db.query(Booking).filter(
        and_(
            Booking.status == "returned",
            Booking.returned_at != None,
            Booking.returned_at < cutoff,
            Booking.deposit_status.notin_(["in_dispute", "claimed", "partially_withheld", "refunded"]),
        )
    ).all()

    released_count = 0
    for bk in bookings:
        bk.deposit_status = "refunded"
        bk.updated_at = now
        released_count += 1
        db.add(bk)
        # إشعار المستخدمين
        try:
            notify_user(bk.renter_id, f"✅ تم الإفراج التلقائي عن الوديعة لحجز #{bk.id}")
            notify_user(bk.owner_id, f"ℹ️ تم الإفراج التلقائي عن وديعة حجز #{bk.id}")
        except Exception:
            pass

    db.commit()
    return released_count


@router.get("/admin/run/auto-release")
def run_auto_release():
    """
    راوتر إداري لتشغيل العملية يدويًا أثناء التطوير أو الاختبار.
    """
    db = SessionLocal()
    try:
        count = auto_release_logic(db)
        return {"status": "ok", "released": count}
    finally:
        db.close()


if __name__ == "__main__":
    # يمكن تشغيل هذا الملف مباشرة: python app/cron_auto_release.py
    db = SessionLocal()
    count = auto_release_logic(db)
    print(f"✅ تم الإفراج التلقائي عن {count} وديعة/ودائع منتهية المهلة.")
    db.close()