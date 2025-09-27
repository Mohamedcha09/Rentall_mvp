# app/models.py
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Date, Boolean
)
from sqlalchemy.orm import relationship, column_property
from sqlalchemy.sql import literal
from .database import Base, engine  # لا تغيّر

# -------------------------
# Helpers مع SQLite
# -------------------------
def _has_column(table: str, col: str) -> bool:
    try:
        with engine.begin() as conn:
            rows = conn.exec_driver_sql(f"PRAGMA table_info('{table}')").all()
        return any(r[1] == col for r in rows)
    except Exception:
        return True

def col_or_literal(table: str, name: str, type_, **kwargs):
    if _has_column(table, name):
        return Column(type_, **kwargs)
    return column_property(literal(None))


# =========================
# Users & Documents
# =========================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name  = Column(String(100), nullable=False)
    email      = Column(String(200), unique=True, nullable=False, index=True)
    phone      = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)

    stripe_account_id = col_or_literal("users", "stripe_account_id", String, nullable=True)
    payouts_enabled   = col_or_literal("users", "payouts_enabled", Boolean, default=False)
    role              = col_or_literal("users", "role", String(20), default="user")
    status            = col_or_literal("users", "status", String(20), default="pending")

    is_verified    = col_or_literal("users", "is_verified", Boolean, default=False, nullable=False)
    verified_at    = col_or_literal("users", "verified_at", DateTime, nullable=True)
    if _has_column("users", "verified_by_id"):
        verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    else:
        verified_by_id = column_property(literal(None))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = col_or_literal("users", "updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    avatar_path = col_or_literal("users", "avatar_path", String(500), nullable=True)

    # شارات اختيارية
    badge_admin         = col_or_literal("users", "badge_admin",         Boolean, default=False)
    badge_new_yellow    = col_or_literal("users", "badge_new_yellow",    Boolean, default=False)
    badge_pro_green     = col_or_literal("users", "badge_pro_green",     Boolean, default=False)
    badge_pro_gold      = col_or_literal("users", "badge_pro_gold",      Boolean, default=False)
    badge_purple_trust  = col_or_literal("users", "badge_purple_trust",  Boolean, default=False)
    badge_renter_green  = col_or_literal("users", "badge_renter_green",  Boolean, default=False)
    badge_orange_stars  = col_or_literal("users", "badge_orange_stars",  Boolean, default=False)

    # علاقات
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    items = relationship("Item", back_populates="owner", cascade="all, delete-orphan")

    sent_messages    = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    ratings_given    = relationship("Rating", foreign_keys="Rating.rater_id", back_populates="rater")
    ratings_received = relationship("Rating", foreign_keys="Rating.rated_user_id", back_populates="rated_user")

    # علاقات التوثيق الذاتي
    if _has_column("users", "verified_by_id"):
        verified_by = relationship(
            "User",
            remote_side=[id],
            foreign_keys="[User.verified_by_id]",
            backref="verified_users",
            uselist=False
        )

    # مفضلات
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")

    # خصائص مساعدة
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def five_star_count(self) -> int:
        return sum(1 for r in (self.ratings_received or []) if r.stars == 5)

    @property
    def is_auto_verifiable(self) -> bool:
        return self.five_star_count >= 10

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

    @property
    def is_new_under_2m(self) -> bool:
        try:
            if not self.created_at:
                return False
            return (datetime.utcnow() - self.created_at).days < 60
        except Exception:
            return False


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    doc_type = Column(String(50))
    country  = Column(String(100))
    expiry_date = Column(Date, nullable=True)
    file_front_path = Column(String(500))
    file_back_path  = Column(String(500), nullable=True)
    review_status = Column(String(20), default="pending")
    review_note   = Column(Text, nullable=True)
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

    title       = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    city        = Column(String(120), nullable=True)

    price_per_day = Column(Integer, nullable=False, default=0)
    category     = Column(String(50), nullable=False, default="other")
    image_path   = Column(String(500), nullable=True)
    is_active    = Column(String(10), default="yes")

    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="items")
    message_threads = relationship("MessageThread", back_populates="item", cascade="all, delete-orphan")
    # علاقة المفضلة
    favorited_by = relationship("Favorite", back_populates="item", cascade="all, delete-orphan")


# =========================
# Favorites (NEW)
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
    item_id = Column(Integer, ForeignKey("items.id"), nullable=True)

    created_at      = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, default=datetime.utcnow)

    user_a = relationship("User", foreign_keys=[user_a_id])
    user_b = relationship("User", foreign_keys=[user_b_id])

    item = relationship("Item", back_populates="message_threads")

    messages = relationship(
        "Message",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Message.created_at.asc()",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("message_threads.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    is_read = col_or_literal("messages", "is_read", Boolean, default=False, nullable=False)
    read_at = col_or_literal("messages", "read_at", DateTime, nullable=True)

    thread = relationship("MessageThread", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")


# =========================
# Ratings
# =========================
class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True, index=True)

    rater_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    rated_user_id  = Column(Integer, ForeignKey("users.id"), nullable=False)

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
    amount = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="planned")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", lazy="joined")
    item = relationship("Item", lazy="joined")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    item_id    = Column(Integer, ForeignKey("items.id"), nullable=False)
    renter_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    days       = Column(Integer, nullable=False, default=1)
    price_per_day = Column(Integer, nullable=False, default=0)
    total_amount  = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    item_id   = Column(Integer, ForeignKey("items.id"), nullable=False)
    renter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner_id  = Column(Integer, ForeignKey("users.id"), nullable=False)

    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    days       = Column(Integer, nullable=False, default=1)

    price_per_day_snapshot = Column(Integer, nullable=False, default=0)
    total_amount           = Column(Integer, nullable=False, default=0)

    status = Column(String(20), nullable=False, default="requested")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payment_intent_id = col_or_literal("bookings", "payment_intent_id", String, nullable=True)
    payment_status    = col_or_literal("bookings", "payment_status", String, default="unpaid")

    item   = relationship("Item", backref="bookings")
    renter = relationship("User", foreign_keys="[Booking.renter_id]", backref="bookings_rented")
    owner  = relationship("User", foreign_keys="[Booking.owner_id]",  backref="bookings_owned")