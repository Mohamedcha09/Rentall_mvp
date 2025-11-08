# app/models_deposit.py
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship

from .database import Base
# We use Users/Bookings only for foreign key relationships
# (We do not import Base from models.py to avoid circular imports)
# These tables are entirely new — no need for col_or_literal here.

# =========================
# Deposit Case
# =========================
class DepositCase(Base):
    """
    Represents a “deposit case” opened by the owner after the return,
    and reviewed by the Deposit Manager. It links to a specific booking.
    """
    __tablename__ = "deposit_cases"

    id = Column(Integer, primary_key=True, index=True)

    # Link to the booking and the parties
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    owner_id   = Column(Integer, ForeignKey("users.id"),    nullable=False)
    renter_id  = Column(Integer, ForeignKey("users.id"),    nullable=False)

    # Case workflow status
    # pending / in_review / need_info / resolved
    status = Column(String(20), nullable=False, default="pending")

    # Issue type (optional for organization): delay / damage / loss / other
    issue_type = Column(String(20), nullable=True)

    # Owner’s initial claim (in the platform’s base currency)
    claim_amount = Column(Integer, nullable=False, default=0)

    # Final decision:
    # decision: refund_all / withhold_partial / withhold_all / none
    decision       = Column(String(30), nullable=True)
    decided_amount = Column(Integer, nullable=False, default=0)  # Amount actually withheld from the deposit (if any)
    decision_note  = Column(Text, nullable=True)
    decided_at     = Column(DateTime, nullable=True)

    # Assignment to a specific Deposit Manager (a user with is_deposit_manager=True or admin)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at    = Column(DateTime, nullable=True)

    # Operational deadlines (optional)
    deadline_owner_report_at  = Column(DateTime, nullable=True)  # Deadline to open a report (usually set on creation)
    deadline_renter_reply_at  = Column(DateTime, nullable=True)  # Renter’s reply deadline
    deadline_manager_decide_at = Column(DateTime, nullable=True) # Manager’s decision deadline

    # Generic timestamps
    opened_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships (lazy=selectin to avoid N+1)
    booking = relationship("Booking", backref="deposit_case", lazy="selectin")
    owner   = relationship("User", foreign_keys=[owner_id],  lazy="selectin")
    renter  = relationship("User", foreign_keys=[renter_id], lazy="selectin")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], lazy="selectin")

    # Attached evidences for this case
    evidences = relationship("DepositEvidence", back_populates="case", cascade="all, delete-orphan", lazy="selectin")

    # Audit log
    logs = relationship("DepositLog", back_populates="case", cascade="all, delete-orphan", lazy="selectin")


# =========================
# Evidence (case evidences)
# =========================
class DepositEvidence(Base):
    """
    Evidence attached by the owner, renter, or manager:
    photos/videos/descriptive files and links. We store the path or URL with a short description.
    """
    __tablename__ = "deposit_evidences"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("deposit_cases.id"), nullable=False, index=True)

    # Who attached the evidence?
    by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # role: owner / renter / manager
    role = Column(String(20), nullable=False)

    # Evidence type (optional descriptive): photo / video / doc / note / link
    kind = Column(String(20), nullable=True)

    # Path to an uploaded file inside the system or an external link
    media_path = Column(String(600), nullable=True)
    external_url = Column(String(600), nullable=True)

    # Short description
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("DepositCase", back_populates="evidences", lazy="selectin")
    by_user = relationship("User", foreign_keys=[by_user_id], lazy="selectin")


# =========================
# Audit Log
# =========================
class DepositLog(Base):
    """
    Records every important event in the case: opened, assigned, need_info, decision, etc.
    """
    __tablename__ = "deposit_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("deposit_cases.id"), nullable=False, index=True)

    # Who performed the action (may be null if automated)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # action: opened / assigned / need_info / note / decision / auto_release / comment
    action = Column(String(30), nullable=False)

    # Explanatory text
    message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("DepositCase", back_populates="logs", lazy="selectin")
    actor = relationship("User", foreign_keys=[actor_user_id], lazy="selectin")
