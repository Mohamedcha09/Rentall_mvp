# app/paypal_client.py
import os
import base64
import httpx

PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")

if PAYPAL_MODE == "live":
    BASE_URL = "https://api-m.paypal.com"
else:
    BASE_URL = "https://api-m.sandbox.paypal.com"

CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
SECRET = os.getenv("PAYPAL_SECRET")


class PayPalError(Exception):
    pass


async def _get_access_token():
    auth = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            headers=headers,
        )

    if r.status_code != 200:
        raise PayPalError(r.text)

    return r.json()["access_token"]


async def create_paypal_order(amount, currency, return_url, cancel_url, reference_id, description, custom_id):
    token = await _get_access_token()

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": reference_id,
            "description": description,
            "custom_id": custom_id,
            "amount": {
                "currency_code": currency.upper(),
                "value": f"{amount:.2f}"
            }
        }],
        "application_context": {
            "return_url": return_url,
            "cancel_url": cancel_url
        }
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/v2/checkout/orders",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )

    if r.status_code not in (200, 201):
        raise PayPalError(r.text)

    data = r.json()
    approve_url = next(l["href"] for l in data["links"] if l["rel"] == "approve")

    return {
        "order_id": data["id"],
        "approval_url": approve_url
    }


async def capture_paypal_order(order_id):
    token = await _get_access_token()

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/v2/checkout/orders/{order_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )

    if r.status_code not in (200, 201):
        raise PayPalError(r.text)

    data = r.json()
    capture_id = data["purchase_units"][0]["payments"]["captures"][0]["id"]

    return {"capture_id": capture_id}
