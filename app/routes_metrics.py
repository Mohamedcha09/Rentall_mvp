# app/routes_metrics.py
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, Request, Body, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from .database import get_db
from .models_metrics import Visit, OnlineSession

router = APIRouter()

ONLINE_WINDOW_SECONDS = 120  # Consider "online now" if there was activity in the last two minutes

def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"

@router.post("/api/metrics/track")
async def track_visit(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    session_id = (payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(400, "session_id required")
    user_id = payload.get("user_id")
    ip = _client_ip(request)
    ua = (request.headers.get("user-agent") or "")[:255]

    db.add(Visit(session_id=session_id, user_id=user_id, ip=ip, user_agent=ua))

    now = datetime.utcnow()
    osess = db.get(OnlineSession, session_id)
    if osess:
        osess.last_seen = now
        osess.ip = ip
        osess.user_agent = ua
        if user_id:
            osess.user_id = user_id
    else:
        db.add(OnlineSession(session_id=session_id, user_id=user_id, ip=ip, user_agent=ua,
                             first_seen=now, last_seen=now))
    db.commit()
    return {"ok": True}

@router.post("/api/metrics/heartbeat")
async def heartbeat(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    session_id = (payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(400, "session_id required")
    user_id = payload.get("user_id")
    ip = _client_ip(request)
    ua = (request.headers.get("user-agent") or "")[:255]
    now = datetime.utcnow()

    osess = db.get(OnlineSession, session_id)
    if osess:
        osess.last_seen = now
        osess.ip = ip
        osess.user_agent = ua
        if user_id:
            osess.user_id = user_id
    else:
        db.add(OnlineSession(session_id=session_id, user_id=user_id, ip=ip, user_agent=ua,
                             first_seen=now, last_seen=now))
    db.commit()

    online_now = db.query(OnlineSession).filter(OnlineSession.last_seen >= now - timedelta(seconds=ONLINE_WINDOW_SECONDS)).count()
    return {"ok": True, "online_now": online_now}

@router.get("/api/admin/metrics/summary")
def metrics_summary(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    today = date.today()

    today_count = db.query(func.count(distinct(Visit.session_id))).filter(Visit.day == today).scalar() or 0
    month_count = db.query(func.count(distinct(Visit.session_id))).filter(Visit.year == today.year, Visit.month == today.month).scalar() or 0
    year_count  = db.query(func.count(distinct(Visit.session_id))).filter(Visit.year == today.year).scalar() or 0

    online_now = db.query(OnlineSession).filter(OnlineSession.last_seen >= now - timedelta(seconds=ONLINE_WINDOW_SECONDS)).count()

    return {
        "today": today_count,
        "month": month_count,
        "year": year_count,
        "online_now": online_now,
        "online_window_seconds": ONLINE_WINDOW_SECONDS,
    }

@router.get("/api/admin/metrics/daily_chart")
def daily_chart(db: Session = Depends(get_db)):
    start_day = date.today() - timedelta(days=29)
    rows = (
        db.query(Visit.day.label("d"), func.count(distinct(Visit.session_id)).label("u"))
        .filter(Visit.day >= start_day)
        .group_by(Visit.day)
        .order_by(Visit.day)
        .all()
    )
    return {"labels": [r.d.isoformat() for r in rows], "values": [int(r.u) for r in rows]}
