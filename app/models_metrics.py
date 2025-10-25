# app/models_metrics.py
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, DateTime, Date, Index
from .database import Base

class Visit(Base):
    __tablename__ = "visits"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)
    user_id = Column(Integer, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    visited_at = Column(DateTime, default=datetime.utcnow, index=True)
    day = Column(Date, default=lambda: date.today(), index=True)
    year = Column(Integer, default=lambda: date.today().year, index=True)
    month = Column(Integer, default=lambda: date.today().month, index=True)

Index('ix_visits_day_session', Visit.day, Visit.session_id, unique=False)


class OnlineSession(Base):
    __tablename__ = "online_sessions"
    session_id = Column(String(64), primary_key=True)  # فريد لكل متصفح/جهاز
    user_id = Column(Integer, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
