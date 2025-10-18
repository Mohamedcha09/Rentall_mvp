# app/admin.py
from datetime import datetime
import os

from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Document, MessageThread, Message
from .notifications_api import push_notification  # إشعار داخل الموقع
from .email_service import send_email             # إرسال البريد عبر SendGrid

router = APIRouter()

BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")


# ---------------------------
# Helpers
# ---------------------------
def require_admin(request: Request) -> bool:
    u = request.session.get("user")
    return bool(u and (u.get("role") or "").lower() == "admin")


def _open_or_create_admin_thread(db: Session, admin_id: int, user_id: int) -> MessageThread:
    """افتح أو أنشئ خيط رسائل بين الأدمِن والمستخدم."""
    thread = (
        db.query(MessageThread)
        .filter(
            ((MessageThread.user_a_id == admin_id) & (MessageThread.user_b_id == user_id)) |
            ((MessageThread.user_a_id == user_id) & (MessageThread.user_b_id == admin_id))
        )
        .order_by(MessageThread.created_at.desc())
        .first()
    )
    if not thread:
        thread = MessageThread(user_a_id=admin_id, user_b_id=user_id, item_id=None)
        db.add(thread)
        db.commit()
        db.refresh(thread)
    return thread


def _refresh_session_user_if_self(request: Request, user: User) -> None:
    """لو الأدمِن عدّل نفسه، حدّث القيم داخل session حتى تظهر فورًا في الواجهة."""
    sess = request.session.get("user")
    if not sess or sess.get("id") != user.id:
        return
    sess["role"] = user.role
    sess["status"] = user.status
    sess["is_verified"] = bool(user.is_verified)
    for k in [
        "badge_admin", "badge_new_yellow", "badge_pro_green", "badge_pro_gold",
        "badge_purple_trust", "badge_renter_green", "badge_orange_stars",
    ]:
        if hasattr(user, k):
            sess[k] = getattr(user, k)
    if hasattr(user, "is_deposit_manager"):
        sess["is_deposit_manager"] = bool(getattr(user, "is_deposit_manager", False))
    request.session["user"] = sess


# ---------------------------
# لوحة الأدمِن
# ---------------------------
@router.get("/admin")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    pending_users = (
        db.query(User)
        .filter(User.status == "pending")
        .order_by(User.created_at.desc())
        .all()
    )
    all_users = db.query(User).order_by(User.created_at.desc()).all()

    return request.app.templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "title": "لوحة الأدمين",
            "pending_users": pending_users,
            "all_users": all_users,
            "session_user": request.session.get("user"),
        },
    )


# ---------------------------
# قرارات التسجيل
# ---------------------------
@router.post("/admin/users/{user_id}/approve")
def approve_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """
    موافقة الأدمن: نفعّل زر الحجز عبر تغيير status إلى approved،
    ونرسل بريداً يوضّح الحالة.
    """
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    user.status = "approved"

    for d in (user.documents or []):
        d.review_status = "approved"
        d.reviewed_at = datetime.utcnow()

    db.commit()
    _refresh_session_user_if_self(request, user)

    # إرسال إيميل بحسب حالة تفعيل البريد
    try:
        home_url = f"{BASE_URL}/"
        logo = f"{BASE_URL}/static/images/ok.png"
        brand = f"{BASE_URL}/static/images/base.png"

        if bool(getattr(user, "is_verified", False)):
            subject = "تم تفعيل حسابك 100% — يمكنك الحجز الآن 🎉"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>تفعيل 100%</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,'Segoe UI',sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0">تم تفعيل حسابك 100% — يمكنك الحجز الآن</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b0f1a;padding:24px 12px">
    <tr><td align="center">
      <table role="presentation" width="640" cellspacing="0" cellpadding="0"
             style="width:100%;max-width:640px;background:#0f172a;border:1px solid #1f2937;border-radius:16px;overflow:hidden">
        <tr>
          <td style="padding:20px 24px;background:linear-gradient(90deg,#111827,#0b1220)">
            <table width="100%"><tr>
              <td align="right"><img src="{brand}" alt="" style="height:22px;opacity:.95"></td>
              <td align="left"><img src="{logo}" alt="" style="height:36px;border-radius:8px"></td>
            </tr></table>
          </td>
        </tr>
        <tr><td style="padding:28px 26px">
          <h2 style="margin:0 0 12px;font-size:22px;color:#fff;">مرحبًا {user.first_name or ''} 👋</h2>
          <p style="margin:0 0 12px;line-height:1.9;color:#cbd5e1">
            تمت موافقة الأدمين على حسابك، وحسابك الآن <b style="color:#fff">مفعّل 100%</b>.
          </p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:26px auto">
            <tr><td bgcolor="#16a34a" style="border-radius:10px;">
              <a href="{home_url}" target="_blank"
                 style="font-family:Tahoma,Arial,sans-serif;font-size:16px;line-height:16px;text-decoration:none;
                        padding:14px 22px;display:inline-block;color:#ffffff;border-radius:10px;font-weight:700">
                ابدأ الآن
              </a>
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:18px 24px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          إذا لم تطلب هذه العملية، تجاهل الرسالة.
        </td></tr>
      </table>
      <div style="color:#64748b;font-size:11px;margin-top:12px">&copy; {year} RentAll</div>
    </td></tr>
  </table>
</body></html>"""
            text = f"مرحبًا {user.first_name}\n\nتم تفعيل حسابك 100% ويمكنك الآن الحجز.\n{home_url}"
        else:
            verify_page = f"{BASE_URL}/verify-email?email={user.email}"
            subject = "تمت موافقة الأدمن — فعّل بريدك لإكمال 100%"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>أكمل تفعيل البريد</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,'Segoe UI',sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0">تمت الموافقة — أكمل تفعيل البريد لإتمام حسابك</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b0f1a;padding:24px 12px">
    <tr><td align="center">
      <table role="presentation" width="640" cellspacing="0" cellpadding="0"
             style="width:100%;max-width:640px;background:#0f172a;border:1px solid #1f2937;border-radius:16px;overflow:hidden">
        <tr>
          <td style="padding:20px 24px;background:linear-gradient(90deg,#111827,#0b1220)">
            <table width="100%"><tr>
              <td align="right"><img src="{brand}" alt="" style="height:22px;opacity:.95"></td>
              <td align="left"><img src="{logo}" alt="" style="height:36px;border-radius:8px"></td>
            </tr></table>
          </td>
        </tr>
        <tr><td style="padding:28px 26px">
          <h2 style="margin:0 0 12px;font-size:22px;color:#fff;">مرحبًا {user.first_name or ''} 👋</h2>
          <p style="margin:0 0 12px;line-height:1.9;color:#cbd5e1">
            تمت موافقة الأدمين على حسابك. بقي خطوة واحدة لإكمال التفعيل 100%: <b style="color:#fff">فعّل بريدك</b>.
          </p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:26px auto">
            <tr><td bgcolor="#2563eb" style="border-radius:10px;">
              <a href="{verify_page}" target="_blank"
                 style="font-family:Tahoma,Arial,sans-serif;font-size:16px;line-height:16px;text-decoration:none;
                        padding:14px 22px;display:inline-block;color:#ffffff;border-radius:10px;font-weight:700">
                تعليمات التفعيل
              </a>
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:18px 24px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          إذا لم تطلب هذه العملية، تجاهل الرسالة.
        </td></tr>
      </table>
      <div style="color:#64748b;font-size:11px;margin-top:12px">&copy; {year} RentAll</div>
    </td></tr>
  </table>
</body></html>"""
            text = f"مرحبًا {user.first_name}\n\nتمت موافقة الأدمن. لإكمال 100% فعّل بريدك من رسالة التفعيل.\n{verify_page}"

        send_email(user.email, subject, html, text_body=text)
    except Exception:
        pass

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/reject")
def reject_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    user.status = "rejected"
    for d in (user.documents or []):
        d.review_status = "rejected"
        d.reviewed_at = datetime.utcnow()
    db.commit()
    _refresh_session_user_if_self(request, user)

    # إيميل رفض (اختياري)
    try:
        subject = "لم يتم قبول حسابك حالياً"
        html = f"""
        <div style="font-family:Tahoma,Arial,sans-serif;direction:rtl;text-align:right;line-height:1.8">
          <p>نعتذر، لم يتم قبول حسابك حالياً. يمكنك إعادة رفع صور واضحة لبطاقتك وصورتك الشخصية ثم طلب المراجعة مرة أخرى.</p>
          <p><a href="{BASE_URL}/activate">إكمال التفعيل</a></p>
        </div>
        """
        send_email(user.email, subject, html, text_body="لم يتم قبول حسابك حالياً.")
    except Exception:
        pass

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# التوثيق (Verification)
# ---------------------------
@router.post("/admin/users/{user_id}/verify")
def verify_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    user.is_verified = True
    if hasattr(user, "verified_at"):
        user.verified_at = datetime.utcnow()
    if hasattr(user, "verified_by_id") and admin:
        user.verified_by_id = admin.get("id")
    db.commit()
    _refresh_session_user_if_self(request, user)

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/unverify")
def unverify_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    user.is_verified = False
    if hasattr(user, "verified_at"):
        user.verified_at = None
    if hasattr(user, "verified_by_id"):
        user.verified_by_id = None
    db.commit()
    _refresh_session_user_if_self(request, user)

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# مراجعة وثائق فردية
# ---------------------------
@router.post("/admin/documents/{doc_id}/approve")
def approve_document(doc_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    doc = db.query(Document).get(doc_id)
    if doc:
        doc.review_status = "approved"
        doc.reviewed_at = datetime.utcnow()
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/documents/{doc_id}/reject")
def reject_document(doc_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    doc = db.query(Document).get(doc_id)
    if doc:
        doc.review_status = "rejected"
        doc.reviewed_at = datetime.utcnow()
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# مراسلة المستخدم + طلب تصحيح
# ---------------------------
@router.post("/admin/users/{user_id}/message")
def admin_message_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    if not admin:
        return RedirectResponse(url="/login", status_code=303)

    thread = _open_or_create_admin_thread(db, admin["id"], user_id)

    first_msg = db.query(Message).filter(Message.thread_id == thread.id).first()
    if not first_msg:
        db.add(Message(thread_id=thread.id, sender_id=admin["id"], body="مرحبًا! يرجى استكمال/تصحيح بيانات التحقق."))
        db.commit()

    return RedirectResponse(url=f"/messages/{thread.id}", status_code=303)


@router.post("/admin/users/{user_id}/request_fix")
def admin_request_fix(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    reason: str = Form("نحتاج صورة أوضح أو وثيقة صالحة.")
):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    if not admin:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    for d in (user.documents or []):
        d.review_status = "needs_fix"
        d.reviewed_at = datetime.utcnow()
        if d.review_note:
            d.review_note = f"{d.review_note.strip()}\n- {reason.strip()}"
        else:
            d.review_note = reason.strip()

    db.commit()

    thread = _open_or_create_admin_thread(db, admin["id"], user_id)
    fix_link = "/profile/docs"
    body = f"مرحبًا {user.first_name}،\nهناك ملاحظات على مستندات التحقق:\n- {reason}\nيرجى التصحيح هنا: {fix_link}"
    db.add(Message(thread_id=thread.id, sender_id=admin["id"], body=body))
    db.commit()

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# إدارة الشارات (Badges)
# ---------------------------
@router.post("/users/{user_id}/badges")
def set_badges(
    user_id: int,
    badge_purple_trust: str | None = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if not u:
        return RedirectResponse(url="/admin", status_code=303)

    u.badge_purple_trust = bool(badge_purple_trust)
    u.is_verified = u.badge_purple_trust
    db.add(u)
    db.commit()
    db.refresh(u)
    _refresh_session_user_if_self(request, u)
    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# إدارة صلاحية متحكّم الوديعة + (إشعار + بريد)
# ---------------------------
@router.post("/admin/users/{user_id}/deposit_manager/enable")
def enable_deposit_manager(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_deposit_manager"):
        u.is_deposit_manager = True
        db.commit()
        _refresh_session_user_if_self(request, u)

        # إشعار داخل الموقع
        push_notification(
            db, u.id,
            "تم منحك دور متحكّم الوديعة 🎉",
            "يمكنك الآن مراجعة الودائع واتخاذ القرارات.",
            "/dm/deposits",
            "role"
        )

        # بريد: قبول الدور
        try:
            subject = "🎉 تم منحك دور متحكّم الوديعة — أهلاً بك في لوحة المراجعة"
            home = f"{BASE_URL}/dm/deposits"
            logo = f"{BASE_URL}/static/images/ok.png"
            brand = f"{BASE_URL}/static/images/base.png"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>تم منحك دور متحكّم الوديعة</title></head>
<body style="margin:0;background:#0b0f1a;font-family:Tahoma,Arial,sans-serif;color:#e5e7eb">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;background:#0b0f1a">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:640px;border-radius:20px;overflow:hidden;
                    background:linear-gradient(135deg,rgba(17,24,39,.85),rgba(2,6,23,.85));
                    border:1px solid rgba(148,163,184,.25);backdrop-filter:blur(8px)">
        <tr>
          <td style="padding:18px 22px;background:linear-gradient(90deg,#111827,#0b1220)">
            <table width="100%"><tr>
              <td align="right"><img src="{brand}" style="height:22px;opacity:.95" alt=""></td>
              <td align="left"><img src="{logo}" style="height:36px;border-radius:10px" alt=""></td>
            </tr></table>
          </td>
        </tr>
        <tr><td style="padding:28px 26px">
          <h2 style="margin:0 0 10px;color:#fff">مرحبًا {u.first_name or 'صديقنا'} 🎉</h2>
          <p style="margin:0 0 12px;line-height:1.9;color:#cbd5e1">
            تم منحك <b style="color:#fff">دور متحكّم الوديعة</b>. يمكنك الآن الدخول إلى لوحة إدارة القضايا،
            مراجعة الأدلة، و اتخاذ القرارات النهائية.
          </p>
          <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:22px auto">
            <tr><td bgcolor="#16a34a" style="border-radius:12px">
              <a href="{home}" target="_blank"
                 style="display:inline-block;padding:14px 22px;color:#fff;text-decoration:none;font-weight:700;border-radius:12px">
                 فتح لوحة الودائع
              </a>
            </td></tr>
          </table>
          <p style="margin:8px 0 0;color:#94a3b8;font-size:13px">نصيحة: فعّل التنبيهات لتصلك تحديثات القضايا فورًا.</p>
        </td></tr>
        <tr><td style="padding:16px 22px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          &copy; {year} RentAll
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
            text = f"تم منحك دور متحكّم الوديعة. لوحة الإدارة: {home}"
            send_email(u.email, subject, html, text_body=text)
        except Exception:
            pass

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/deposit_manager/disable")
def disable_deposit_manager(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_deposit_manager"):
        u.is_deposit_manager = False
        db.commit()
        _refresh_session_user_if_self(request, u)

        push_notification(
            db, u.id,
            "تم إلغاء دور متحكّم الوديعة",
            "لم تعد تملك صلاحية إدارة الودائع.",
            "/",
            "role"
        )

        # بريد: إلغاء الدور
        try:
            subject = "تم إلغاء دور متحكّم الوديعة"
            home = f"{BASE_URL}/"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>إلغاء الصلاحية</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;background:#0b0f1a">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:640px;border-radius:18px;overflow:hidden;background:#0f172a;border:1px solid #1f2937">
        <tr><td style="padding:26px 24px">
          <h3 style="margin:0 0 8px;color:#fff">تم إلغاء دور متحكّم الوديعة</h3>
          <p style="margin:0;line-height:1.9;color:#cbd5e1">
            تم إلغاء صلاحية إدارة الودائع من حسابك. لا يزال بإمكانك استخدام بقية مزايا الموقع كالمعتاد.
          </p>
          <p style="margin:18px 0 0"><a href="{home}" style="color:#60a5fa;text-decoration:none">العودة للصفحة الرئيسية</a></p>
        </td></tr>
        <tr><td style="padding:14px 22px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          &copy; {year} RentAll
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
            text = f"تم إلغاء دور متحكّم الوديعة من حسابك. لمزيد من التفاصيل: {home}"
            send_email(u.email, subject, html, text_body=text)
        except Exception:
            pass

    return RedirectResponse(url="/admin", status_code=303)