# app/models.py
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Date, Boolean, Float, event, func
)
from sqlalchemy.orm import relationship, column_property
from sqlalchemy.sql import literal

# ✅ استيراد الدوال/الكائنات الصحيحة من database (بدون تعريف محلي لـ _has_column)
from .database import Base, engine, _has_column

# -------------------------
# Helper: عمود إن وُجد وإلا literal(None)
# -------------------------
def col_or_literal(table: str, name: str, type_, **kwargs):
    """
    لو العمود موجود فعلاً في الجدول → Column(type_, **kwargs)
    لو غير موجود (في قواعد قديمة) → column_property(literal(None)) حتى لا تنكسر النماذج.
    """
    if _has_column(table, name):
        return Column(type_, **kwargs)
    return column_property(literal(None))


# === Force admin flags helper ===
def _force_admin_flags(u) -> None:
    """اضبط جميع أعلام التفعيل للأدمن مهما كانت الشروط الأخرى."""
    try:
        role = (getattr(u, "role", "") or "").lower()
        if role == "admin":
            if _has_column("users", "is_verified"): u.is_verified = True
            if _has_column("users", "status"): u.status = "approved"
            if _has_column("users", "is_mod"): u.is_mod = True
            if _has_column("users", "badge_admin"): u.badge_admin = True
            if _has_column("users", "is_deposit_manager"): u.is_deposit_manager = True
            if _has_column("users", "payouts_enabled"): u.payouts_enabled = True
            if _has_column("users", "verified_at") and not getattr(u, "verified_at", None):
                u.verified_at = datetime.utcnow()
    except Exception:
        # لا تكسر أي شيء لو أعمدة ناقصة
        pass


# =========================
# Users & Documents
# =========================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(200), unique=True, nullable=False, index=True)
    phone = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)

    # Stripe / Payouts
    stripe_account_id = col_or_literal("users", "stripe_account_id", String, nullable=True)
    payouts_enabled   = col_or_literal("users", "payouts_enabled", Boolean, default=False)

    role   = Column(String(20), default="user")
    status = Column(String(20), default="pending")

    is_verified = col_or_literal("users", "is_verified", Boolean, default=False, nullable=False)
    verified_at = col_or_literal("users", "verified_at", DateTime, nullable=True)

    if _has_column("users", "verified_by_id"):
        verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    else:
        verified_by_id = column_property(literal(None))

    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = col_or_literal("users", "updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    avatar_path = col_or_literal("users", "avatar_path", String(500), nullable=True)

    # شارات
    badge_admin         = col_or_literal("users", "badge_admin", Boolean, default=False)
    badge_new_yellow    = col_or_literal("users", "badge_new_yellow", Boolean, default=False)
    badge_pro_green     = col_or_literal("users", "badge_pro_green", Boolean, default=False)
    badge_pro_gold      = col_or_literal("users", "badge_pro_gold", Boolean, default=False)
    badge_purple_trust  = col_or_literal("users", "badge_purple_trust", Boolean, default=False)
    badge_renter_green  = col_or_literal("users", "badge_renter_green", Boolean, default=False)
    badge_orange_stars  = col_or_literal("users", "badge_orange_stars", Boolean, default=False)

    # صلاحيات
    is_deposit_manager = col_or_literal("users", "is_deposit_manager", Boolean, default=False, nullable=False)
    is_mod             = col_or_literal("users", "is_mod", Boolean, default=False, nullable=False)
    # ✅ موظف خدمة الزبائن
    is_support         = col_or_literal("users", "is_support", Boolean, default=False, nullable=False)

    # العلاقات
    documents        = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    items            = relationship("Item", back_populates="owner", cascade="all, delete-orphan")
    favorites        = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    sent_messages    = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    ratings_given    = relationship("Rating", foreign_keys="Rating.rater_id", back_populates="rater")
    ratings_received = relationship("Rating", foreign_keys="Rating.rated_user_id", back_populates="rated_user")

    # علاقات الحجوزات
    bookings_rented = relationship("Booking", foreign_keys="[Booking.renter_id]", back_populates="renter")
    bookings_owned  = relationship("Booking", foreign_keys="[Booking.owner_id]", back_populates="owner")

    # علاقات البلاغات/الإجراءات (اختيارية)
    reports_filed  = relationship("Report", foreign_keys="[Report.reporter_id]", back_populates="reporter", cascade="all, delete-orphan")
    report_actions = relationship("ReportActionLog", foreign_keys="[ReportActionLog.actor_id]", back_populates="actor", cascade="all, delete-orphan")

    # توثيق
    if _has_column("users", "verified_by_id"):
        verified_by = relationship(
            "User",
            remote_side=[id],
            foreign_keys="[User.verified_by_id]",
            backref="verified_users",
            uselist=False
        )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def five_star_count(self) -> int:
        return sum(1 for r in (self.ratings_received or []) if r.stars == 5)

    @property
    def is_auto_verifiable(self) -> bool:
        return self.five_star_count >= 10

    @property
    def can_manage_deposits(self) -> bool:
        role = (getattr(self, "role", None) or "").lower()
        return bool(getattr(self, "is_deposit_manager", False) or role == "admin")

    @property
    def is_super_admin(self) -> bool:
        return (str(getattr(self, "role", "")).lower() == "admin") or bool(getattr(self, "badge_admin", False))

    def mark_verified(self, admin_id: int | None = None) -> None:
        if _has_column("users", "is_verified"):
            self.is_verified = True
        if _has_column("users", "verified_at"):
            self.verified_at = datetime.utcnow()
        if _has_column("users", "verified_by_id"):
            self.verified_by_id = admin_id

    def unverify(self) -> None:
        if _has_column("users", "is_verified"):
            self.is_verified = False
        if _has_column("users", "verified_at"):
            self.verified_at = None
        if _has_column("users", "verified_by_id"):
            self.verified_by_id = None


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    doc_type = Column(String(50))
    country = Column(String(100))
    expiry_date = Column(Date, nullable=True)
    file_front_path = Column(String(500))
    file_back_path = Column(String(500), nullable=True)
    review_status = Column(String(20), default="pending")
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="documents")


# =========================
# Items
# =========================
class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    city = Column(String(120), nullable=True)

    # إحداثيات اختيارية
    latitude  = col_or_literal("items", "latitude",  Float,  nullable=True)
    longitude = col_or_literal("items", "longitude", Float,  nullable=True)

    price_per_day = Column(Integer, nullable=False, default=0)
    category      = Column(String(50), nullable=False, default="other")
    image_path    = Column(String(500), nullable=True)
    is_active     = Column(String(10), default="yes")
    created_at    = Column(DateTime, default=datetime.utcnow)

    owner           = relationship("User", back_populates="items")
    message_threads = relationship("MessageThread", back_populates="item", cascade="all, delete-orphan")
    favorited_by    = relationship("Favorite", back_populates="item", cascade="all, delete-orphan")


# =========================
# Favorites
# =========================
class Favorite(Base):
    __tablename__ = "favorites"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="favorites")
    item = relationship("Item", back_populates="favorited_by")


# =========================
# Messaging
# =========================
class MessageThread(Base):
    __tablename__ = "message_threads"

    id = Column(Integer, primary_key=True, index=True)
    user_a_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_b_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id   = Column(Integer, ForeignKey("items.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, default=datetime.utcnow)

    user_a = relationship("User", foreign_keys=[user_a_id])
    user_b = relationship("User", foreign_keys=[user_b_id])
    item   = relationship("Item", back_populates="message_threads")

    # ✅ العلاقة الصحيحة لرسائل الدردشة
    messages = relationship(
        "Message",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("message_threads.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = col_or_literal("messages", "is_read", Boolean, default=False, nullable=False)
    read_at  = col_or_literal("messages", "read_at",  DateTime, nullable=True)

    thread = relationship("MessageThread", back_populates="messages")
    sender  = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")


# =========================
# Ratings
# =========================
class Rating(Base):
    __tablename__ = "ratings"
    id = Column(Integer, primary_key=True, index=True)
    rater_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    rated_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stars   = Column(Integer, nullable=False, default=5)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    rater       = relationship("User", foreign_keys="[Rating.rater_id]", back_populates="ratings_given")
    rated_user  = relationship("User", foreign_keys="[Rating.rated_user_id]", back_populates="ratings_received")


# =========================
# Freeze Deposit / Orders / Bookings
# =========================
class FreezeDeposit(Base):
    __tablename__ = "freeze_deposits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    amount  = Column(Integer, nullable=False, default=0)
    status  = Column(String(20), nullable=False, default="planned")
    note    = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", lazy="joined")
    item = relationship("Item", lazy="joined")


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    item_id  = Column(Integer, ForeignKey("items.id"), nullable=False)
    renter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    days          = Column(Integer, nullable=False, default=1)
    price_per_day = Column(Integer, nullable=False, default=0)
    total_amount  = Column(Integer, nullable=False, default=0)
    status    = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


# =========================
# Notifications
# =========================
class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kind    = Column(String(40), nullable=False, default="info")
    title   = Column(String(200), nullable=False)
    body    = Column(Text, nullable=True)
    link_url = Column(String(400), nullable=True)
    is_read  = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    user = relationship(
        "User",
        back_populates="notifications",
        lazy="joined",
        overlaps="notifications,user"
    )

# علاقة عكسيّة اختيارية
try:
    User.notifications
except Exception:
    User.notifications = relationship(
        "Notification",
        primaryjoin="User.id==Notification.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Notification.created_at.desc()",
        lazy="selectin",
        overlaps="notifications,user"
    )


# =========================
# Bookings
# =========================
class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    item_id  = Column(Integer, ForeignKey("items.id"), nullable=False)
    renter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    days                    = Column(Integer, nullable=False, default=1)
    price_per_day_snapshot  = Column(Integer, nullable=False, default=0)
    total_amount            = Column(Integer, nullable=False, default=0)
    status      = Column(String(20), nullable=False, default="requested")
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payment_method           = col_or_literal("bookings", "payment_method", String(20), nullable=True)
    platform_fee             = col_or_literal("bookings", "platform_fee", Integer, nullable=False, default=0)
    rent_amount              = col_or_literal("bookings", "rent_amount", Integer, nullable=False, default=0)
    hold_deposit_amount      = col_or_literal("bookings", "hold_deposit_amount", Integer, nullable=False, default=0)
    online_status            = col_or_literal("bookings", "online_status", String(30), default="created")
    online_checkout_id       = col_or_literal("bookings", "online_checkout_id", String(120), nullable=True)
    online_payment_intent_id = col_or_literal("bookings", "online_payment_intent_id", String(120), nullable=True)
    owner_payout_amount      = col_or_literal("bookings", "owner_payout_amount", Integer, nullable=False, default=0)
    rent_released_at         = col_or_literal("bookings", "rent_released_at", DateTime, nullable=True)

    deposit_status        = col_or_literal("bookings", "deposit_status", String(30), default="none")
    deposit_hold_intent_id = col_or_literal("bookings", "deposit_hold_intent_id", String(120), nullable=True)
    deposit_refund_id      = col_or_literal("bookings", "deposit_refund_id", String(120), nullable=True)
    deposit_capture_id     = col_or_literal("bookings", "deposit_capture_id", String(120), nullable=True)

    owner_decision  = col_or_literal("bookings", "owner_decision", String(20), nullable=True)
    payment_status  = col_or_literal("bookings", "payment_status", String(20), nullable=True)
    deposit_amount  = col_or_literal("bookings", "deposit_amount", Integer, nullable=False, default=0)
    deposit_hold_id = col_or_literal("bookings", "deposit_hold_id", String(120), nullable=True)
    deposit_charged_amount = col_or_literal("bookings", "deposit_charged_amount", Integer, nullable=False, default=0)

    # لائحة DM
    returned_at        = col_or_literal("bookings", "returned_at", DateTime, nullable=True)
    owner_return_note  = col_or_literal("bookings", "owner_return_note", Text, nullable=True)

    # حقول التايملاين
    accepted_at                     = col_or_literal("bookings", "accepted_at", DateTime, nullable=True)
    rejected_at                     = col_or_literal("bookings", "rejected_at", DateTime, nullable=True)
    picked_up_at                    = col_or_literal("bookings", "picked_up_at", DateTime, nullable=True)
    return_confirmed_by_owner_at    = col_or_literal("bookings", "return_confirmed_by_owner_at", DateTime, nullable=True)
    timeline_created_at             = col_or_literal("bookings", "timeline_created_at", DateTime, nullable=True)
    timeline_owner_decided_at       = col_or_literal("bookings", "timeline_owner_decided_at", DateTime, nullable=True)
    timeline_payment_method_chosen_at = col_or_literal("bookings", "timeline_payment_method_chosen_at", DateTime, nullable=True)
    timeline_paid_at                = col_or_literal("bookings", "timeline_paid_at", DateTime, nullable=True)
    timeline_renter_received_at     = col_or_literal("bookings", "timeline_renter_received_at", DateTime, nullable=True)

    # فحص الإرجاع ومهلة الإفراج التلقائي
    return_check_no_problem  = col_or_literal("bookings", "return_check_no_problem", Boolean, default=False)
    return_check_submitted_at = col_or_literal("bookings", "return_check_submitted_at", DateTime, nullable=True)
    deposit_auto_release_at   = col_or_literal("bookings", "deposit_auto_release_at", DateTime, nullable=True)

    # مسار النزاع
    dispute_opened_at  = col_or_literal("bookings", "dispute_opened_at", DateTime, nullable=True)
    renter_response_at = col_or_literal("bookings", "renter_response_at", DateTime, nullable=True)
    dm_decision_at     = col_or_literal("bookings", "dm_decision_at", DateTime, nullable=True)

    renter_response_deadline_at = col_or_literal("bookings", "renter_response_deadline_at", DateTime, nullable=True)
    dm_decision_deadline_at     = col_or_literal("bookings", "dm_decision_deadline_at", DateTime, nullable=True)

    owner_report_type   = col_or_literal("bookings", "owner_report_type", String(20), nullable=True)  # delay/damage/loss/theft
    owner_report_reason = col_or_literal("bookings", "owner_report_reason", Text, nullable=True)
    renter_response_text = col_or_literal("bookings", "renter_response_text", Text, nullable=True)

    dm_decision        = col_or_literal("bookings", "dm_decision", String(30), nullable=True)  # release/withhold/partial
    dm_decision_amount = col_or_literal("bookings", "dm_decision_amount", Integer, nullable=False, default=0)
    dm_decision_note   = col_or_literal("bookings", "dm_decision_note", Text, nullable=True)

    if _has_column("bookings", "dm_claimed_by_id"):
        dm_claimed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    else:
        dm_claimed_by_id = column_property(literal(None))
    dm_claimed_at = col_or_literal("bookings", "dm_claimed_at", DateTime, nullable=True)

    if _has_column("bookings", "dm_closed_by_id"):
        dm_closed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    else:
        dm_closed_by_id = column_property(literal(None))

    # علاقات
    item   = relationship("Item", backref="bookings")
    renter = relationship("User", foreign_keys=[renter_id], back_populates="bookings_rented")
    owner  = relationship("User", foreign_keys=[owner_id], back_populates="bookings_owned")

    # سجلات وأدلة الوديعة
    deposit_audits = relationship(
        "DepositAuditLog",
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="DepositAuditLog.created_at.desc()"
    )
    deposit_evidences = relationship(
        "DepositEvidence",
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="DepositEvidence.created_at.desc()"
    )


# =========================
# Deposit Audit Log
# =========================
class DepositAuditLog(Base):
    __tablename__ = "deposit_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    actor_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    actor_role = Column(String(20), nullable=False)  # admin / manager / owner / renter
    action     = Column(String(40), nullable=False)  # open_dispute / renter_reply / dm_release / dm_withhold / auto_release ...
    amount     = Column(Integer, nullable=False, default=0)
    reason     = Column(Text, nullable=True)
    details    = Column(Text, nullable=True)         # JSON نصّي/تفاصيل إضافية
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    booking = relationship("Booking", back_populates="deposit_audits")
    actor   = relationship("User", lazy="joined")


# =========================
# Deposit Evidence
# =========================
class DepositEvidence(Base):
    __tablename__ = "deposit_evidences"

    id = Column(Integer, primary_key=True, index=True)
    booking_id  = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable لتوافق قواعد قديمة
    side        = Column(String(20), nullable=False)        # owner / renter / manager
    kind        = Column(String(20), nullable=False, default="image")  # image / video / doc / note
    file_path   = Column(String(600), nullable=True)   # مسار الملف إن وجد
    description = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow, index=True)

    booking = relationship("Booking", back_populates="deposit_evidences")
    uploader = relationship("User", lazy="joined")


# =========================
# Reports (بلاغات)
# =========================
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="open")
    tag    = col_or_literal("reports", "tag", String(24), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = col_or_literal("reports", "updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    item     = relationship("Item", lazy="joined")
    reporter = relationship("User", foreign_keys=[reporter_id], back_populates="reports_filed")

    action_logs = relationship(
        "ReportActionLog",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportActionLog.created_at.desc()"
    )


# =========================
# Report Action Log (قرارات المراجعين)
# =========================
class ReportActionLog(Base):
    __tablename__ = "report_action_logs"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False)
    actor_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    action    = Column(String(40), nullable=False)  # remove_item / reject_report / warn_owner / note / close
    note      = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    report = relationship("Report", back_populates="action_logs")
    actor  = relationship("User", back_populates="report_actions", lazy="joined")


# === SQLAlchemy events: فعّل الأدمن دائمًا ===
@event.listens_for(User, "load")
def _on_user_load(u, ctx):
    _force_admin_flags(u)

@event.listens_for(User, "before_insert")
def _on_user_before_insert(mapper, conn, u):
    _force_admin_flags(u)

@event.listens_for(User, "before_update")
def _on_user_before_update(mapper, conn, u):
    _force_admin_flags(u)


# =========================
# ✅ دعم التذاكر (Support)
# =========================
class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject  = Column(String(200), nullable=False)

    # ✅ أعمدة PostgreSQL التي أنشأتها
    status        = Column(String(20), nullable=False, default="new", index=True)  # new | open | resolved
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_msg_at   = Column(DateTime, nullable=True)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at   = Column(DateTime, nullable=True)

    # شارات/معلومات إضافية
    last_from = Column(String(10), nullable=False, default="user")  # user / agent
    unread_for_user  = Column(Boolean, nullable=False, default=False)
    unread_for_agent = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # علاقات
    user     = relationship("User", foreign_keys=[user_id], lazy="joined")
    assignee = relationship("User", foreign_keys=[assigned_to_id], lazy="joined")

    messages = relationship(
        "SupportMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportMessage.created_at"
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sender_role = Column(String(10), nullable=False, default="user")  # user / agent
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    is_read   = Column(Boolean, nullable=False, default=False)

    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User", lazy="joined")
