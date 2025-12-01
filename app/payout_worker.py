# app/payout_worker.py
from __future__ import annotations
from datetime import datetime

from sqlalchemy.orm import Session

from .database import SessionLocal
from .pay_api import send_owner_payouts


def main():
    db: Session = SessionLocal()
    try:
        print("======================================")
        print(f"[Sevor] Owner payouts worker started at {datetime.utcnow().isoformat()}")

        send_owner_payouts(db)

        print(f"[Sevor] Owner payouts worker finished at {datetime.utcnow().isoformat()}")
        print("======================================")
    finally:
        db.close()


if __name__ == "__main__":
    main()
