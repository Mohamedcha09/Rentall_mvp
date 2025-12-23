# app/payout_worker.py
from __future__ import annotations
from datetime import datetime

def main():
    print("======================================")
    print(f"[Sevor] payout_worker DISABLED at {datetime.utcnow().isoformat()}")
    print("Reason: owner payouts not implemented yet")
    print("======================================")

if __name__ == "__main__":
    main()