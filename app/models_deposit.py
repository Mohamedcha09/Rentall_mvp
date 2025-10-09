# app/models_deposit.py
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship

from .database import Base
# نستخدم Users/Bookings للعلاقات الخارجية فقط
# (لا نستورد Base من models.py لتجنّب الدورات)
# هذه الجداول جديدة بالكامل — لا حاجة لـ col_or_literal هنا.

# =========================
# Deposit Case (قضية وديعة)
# =========================
class DepositCase(Base):
    """
    تمثّل "قضية الوديعة" التي يفتحها المالك بعد الإرجاع، وتُراجع من قِبل
    متحكّم الوديعة (Deposit Manager). تربط بحجز معيّن.
    """
    __tablename__ = "deposit_cases"

    id = Column(Integer, primary_key=True, index=True)

    # ربط بالحجز والأطراف
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    owner_id   = Column(Integer, ForeignKey("users.id"),    nullable=False)
    renter_id  = Column(Integer, ForeignKey("users.id"),    nullable=False)

    # حالة سير القضية
    # pending / in_review / need_info / resolved
    status = Column(String(20), nullable=False, default="pending")

    # نوع المشكلة (اختياري تنظيمي): delay / damage / loss / other
    issue_type = Column(String(20), nullable=True)

    # مطالبة المالك المبدئية (بالعملة الأساسية — نفس عملة المنصة)
    claim_amount = Column(Integer, nullable=False, default=0)

    # قرار نهائي:
    # decision: refund_all / withhold_partial / withhold_all / none
    decision       = Column(String(30), nullable=True)
    decided_amount = Column(Integer, nullable=False, default=0)  # المبلغ المقتطع فعليًا من الوديعة (إن وُجد)
    decision_note  = Column(Text, nullable=True)
    decided_at     = Column(DateTime, nullable=True)

    # إسناد لمتحكّم وديعة معيّن (أحد المستخدمين بصلاحية is_deposit_manager=True أو admin)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at    = Column(DateTime, nullable=True)

    # مهل زمنية تشغيلية (اختيارية)
    deadline_owner_report_at  = Column(DateTime, nullable=True)  # مهلة فتح البلاغ (عادة عند الإنشاء نملأها)
    deadline_renter_reply_at  = Column(DateTime, nullable=True)  # مهلة رد المستأجر
    deadline_manager_decide_at = Column(DateTime, nullable=True) # مهلة قرار المتحكّم

    # طوابع زمنية عامة
    opened_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # علاقات (lazy=selectin لتجنّب N+1)
    booking = relationship("Booking", backref="deposit_case", lazy="selectin")
    owner   = relationship("User", foreign_keys=[owner_id],  lazy="selectin")
    renter  = relationship("User", foreign_keys=[renter_id], lazy="selectin")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], lazy="selectin")

    # أدلة مرفقة لهذه القضية
    evidences = relationship("DepositEvidence", back_populates="case", cascade="all, delete-orphan", lazy="selectin")

    # سجل تدقيق
    logs = relationship("DepositLog", back_populates="case", cascade="all, delete-orphan", lazy="selectin")


# =========================
# Evidence (أدلة القضية)
# =========================
class DepositEvidence(Base):
    """
    أدلة مرفقة من المالك أو المستأجر أو المتحكّم:
    صور/فيديو/ملفات وصفية وروابط. نخزن المسار أو الرابط مع وصف مختصر.
    """
    __tablename__ = "deposit_evidences"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("deposit_cases.id"), nullable=False, index=True)

    # من الذي أرفق الدليل؟
    by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # role: owner / renter / manager
    role = Column(String(20), nullable=False)

    # نوع الدليل (اختياري وصفي): photo / video / doc / note / link
    kind = Column(String(20), nullable=True)

    # مسار ملف مرفوع داخل النظام أو رابط خارجي
    media_path = Column(String(600), nullable=True)
    external_url = Column(String(600), nullable=True)

    # وصف مختصر
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("DepositCase", back_populates="evidences", lazy="selectin")
    by_user = relationship("User", foreign_keys=[by_user_id], lazy="selectin")


# =========================
# Audit Log (سجل تدقيق)
# =========================
class DepositLog(Base):
    """
    يسجل كل حدث مهم في القضية: فتح، إسناد، طلب معلومات، قرار، إلخ…
    """
    __tablename__ = "deposit_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("deposit_cases.id"), nullable=False, index=True)

    # من قام بالفعل (قد يكون null لو كان إجراءً آليًا)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # action: opened / assigned / need_info / note / decision / auto_release / comment
    action = Column(String(30), nullable=False)

    # نص توضيحي
    message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("DepositCase", back_populates="logs", lazy="selectin")
    actor = relationship("User", foreign_keys=[actor_user_id], lazy="selectin")
