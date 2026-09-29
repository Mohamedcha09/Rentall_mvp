"""Small explicit maintenance command for Sevor Finder's derived catalog index.

Run only after the Finder migration is applied:

    python -m app.finder_index --rebuild

It does not modify Items, prices, listings, bookings, or support data.
"""
from __future__ import annotations

import argparse
import json

from .database import SessionLocal
from .finder_service import index_coverage, rebuild_listing_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain the derived Sevor Finder listing index.")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild every currently public listing document.")
    parser.add_argument("--coverage", action="store_true", help="Print current eligible/indexed coverage without changing data.")
    args = parser.parse_args()
    if not args.rebuild and not args.coverage:
        parser.error("choose --rebuild or --coverage")
    db = SessionLocal()
    try:
        if args.rebuild:
            result = rebuild_listing_index(db)
            db.commit()
            print(json.dumps({"rebuilt": result, "coverage": index_coverage(db)}, ensure_ascii=False))
        else:
            print(json.dumps(index_coverage(db), ensure_ascii=False))
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
