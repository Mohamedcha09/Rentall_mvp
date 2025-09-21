# app/routes_users.py
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

# --- get_db import souple (selon ton projet) ---
try:
    # si ton projet expose get_db à app.db
    from app.db import get_db
except Exception:  # pragma: no cover
    # fallback local si l'import ci-dessus échoue
    from .db import get_db  # type: ignore

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")


# ---------- Helpers ----------
def has_column(db: Session, table: str, column: str) -> bool:
    """
    Retourne True si la colonne existe (SQLite/Postgres), sinon False.
    """
    try:
        insp = inspect(db.bind)
        cols = insp.get_columns(table)
        return any(c.get("name") == column for c in cols)
    except Exception:
        # si l’inspection échoue, on reste prudent
        return False


def coalesce_or_blank(col: str, alias: str) -> str:
    """
    Construit un COALESCE standardisé: COALESCE(col,'') AS alias
    """
    return f"COALESCE({col},'') AS {alias}"


def compute_badges(
    status: str,
    created_at: Optional[datetime],
    items_count: int,
    completed_rentals: int,
    avg_rating: Optional[float],
) -> Dict[str, bool]:
    now = datetime.utcnow()
    is_new = False
    if isinstance(created_at, datetime):
        is_new = (now - created_at) <= timedelta(days=14)

    verified = (status or "").lower() in {"approved", "verified"}

    power_seller = items_count >= 5 or completed_rentals >= 10
    trusted = (avg_rating or 0) >= 4.0 and completed_rentals >= 3
    top_rated = (avg_rating or 0) >= 4.7 and completed_rentals >= 5

    return {
        "verified": verified,
        "new_user": is_new,
        "power_seller": power_seller,
        "trusted": trusted,
        "top_rated": top_rated,
    }


# ---------- Route: page profil utilisateur ----------
@router.get("/{user_id}", response_class=HTMLResponse)
def user_profile(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    # --- 1) Lire l'utilisateur (colonnes optionnelles sécurisées) ---
    user_fields = [
        "u.id",
        coalesce_or_blank("u.first_name", "first_name"),
        coalesce_or_blank("u.last_name", "last_name"),
        coalesce_or_blank("u.avatar_path", "avatar_path"),
        coalesce_or_blank("u.status", "status"),
        "u.created_at AS created_at",
        coalesce_or_blank("u.bio", "bio"),
    ]
    # city peut ne pas exister -> si absente, renvoyer '' AS city
    if has_column(db, "users", "city"):
        user_fields.append(coalesce_or_blank("u.city", "city"))
    else:
        user_fields.append("'' AS city")

    user_sql = text(
        f"""
        SELECT
            {", ".join(user_fields)}
        FROM users u
        WHERE u.id = :uid
        LIMIT 1
        """
    )

    user_row = db.execute(user_sql, {"uid": user_id}).mappings().first()
    if not user_row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user = dict(user_row)

    # --- 2) Récupérer les items appartenant à l’utilisateur ---
    # colonnes minimales avec tolérance
    item_fields = [
        "i.id",
        coalesce_or_blank("i.title", "title"),
        coalesce_or_blank("i.image_path", "image_path"),
        coalesce_or_blank("i.city", "city") if has_column(db, "items", "city") else "'' AS city",
        "i.price_per_day" if has_column(db, "items", "price_per_day") else "0 AS price_per_day",
        # label de catégorie: soit depuis items.category, soit via table categories si elle existe
        coalesce_or_blank("i.category", "category_label"),
    ]

    items_sql = text(
        f"""
        SELECT {", ".join(item_fields)}
        FROM items i
        WHERE i.owner_id = :uid
        ORDER BY COALESCE(i.created_at, CURRENT_TIMESTAMP) DESC
        LIMIT 60
        """
    )
    items = [dict(r) for r in db.execute(items_sql, {"uid": user_id}).mappings().all()]

    # --- 3) Statistiques: nombre d’items, locations complétées, note moyenne ---
    items_count = len(items)

    # table bookings optionnelle
    completed_rentals = 0
    avg_rating: Optional[float] = None

    if "bookings" in inspect(db.bind).get_table_names():
        # completed rentals (pour ses items en tant que propriétaire)
        comp_sql = text(
            """
            SELECT COUNT(*) AS c
            FROM bookings b
            JOIN items i ON i.id = b.item_id
            WHERE i.owner_id = :uid
              AND LOWER(COALESCE(b.status,'')) IN ('completed','done','finished')
            """
        )
        completed_rentals = int(db.execute(comp_sql, {"uid": user_id}).scalar() or 0)

    # table reviews optionnelle
    reviews: List[Dict[str, Any]] = []
    if "reviews" in inspect(db.bind).get_table_names():
        # reviews reçues par cet utilisateur en tant que propriétaire
        # (adapter si ta table utilise d'autres colonnes)
        rv_sql = text(
            """
            SELECT
              r.id,
              r.rating,
              r.comment,
              r.created_at,
              COALESCE(ru.first_name,'') AS reviewer_first,
              COALESCE(ru.last_name,'')  AS reviewer_last
            FROM reviews r
            LEFT JOIN users ru ON ru.id = r.reviewer_id
            WHERE r.user_id = :uid
            ORDER BY r.created_at DESC
            LIMIT 50
            """
        )
        reviews = [dict(r) for r in db.execute(rv_sql, {"uid": user_id}).mappings().all()]

        avg_sql = text("SELECT AVG(rating) FROM reviews WHERE user_id = :uid")
        avg_val = db.execute(avg_sql, {"uid": user_id}).scalar()
        if avg_val is not None:
            try:
                avg_rating = round(float(avg_val), 2)
            except Exception:
                avg_rating = None

    # --- 4) Badges dynamiques ---
    badges = compute_badges(
        status=user.get("status", ""),
        created_at=user.get("created_at"),
        items_count=items_count,
        completed_rentals=completed_rentals,
        avg_rating=avg_rating,
    )

    # --- 5) Rendre le template ---
    ctx = {
        "request": request,
        "title": f"{user.get('first_name','')} {user.get('last_name','')}".strip() or "Profil",
        "user": user,
        "items": items,
        "reviews": reviews,
        "items_count": items_count,
        "completed_rentals": completed_rentals,
        "avg_rating": avg_rating,
        "badges": badges,
    }
    return templates.TemplateResponse("user.html", ctx)


# ---------- Alias pratique /u/ID ----------

@router.get("/u/{user_id}", response_class=HTMLResponse)
def user_profile_shortcut(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    # redirige vers la même logique
    return user_profile(request, user_id, db)
