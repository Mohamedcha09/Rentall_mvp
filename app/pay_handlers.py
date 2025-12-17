# app/pay_handlers.py
from datetime import datetime
import stripe
from sqlalchemy.orm import Session

from .models import Booking, User, Item
from .notifications_api import push_notification
from .pay_api import (
    _set_deposit_pi_id,
    _latest_charge_id,
    _fmt_money_cents,
    _compose_invoice_html,
    send_payment_email,
    _best_loc_qs,
)
from .settings import CURRENCY  # ou ton CURRENCY actuel

def handle_checkout_completed(session_obj: dict, db: Session) -> None:
    # 🔁 COPIE-COLLE ICI le contenu COMPLET de:
    # def _handle_checkout_completed(...)
    # SANS changer la logique
    pass
