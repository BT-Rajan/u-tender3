"""MyFatoorah hosted payments (API v2): create an invoice, read an invoice's status, check webhook signatures.

The status we act on always comes from GetPaymentStatus, never from a webhook body alone.
Endpoints and fields follow MyFatoorah's documentation (SendPayment, GetPaymentStatus, webhook signature).
The API token, base address and webhook secret come from app_settings (set by the admin), see MyFatoorahConfig.
"""

import base64
import hashlib
import hmac
from decimal import Decimal
from typing import Any

import httpx

from app.services.app_settings import MyFatoorahConfig

TIMEOUT_SECONDS = 20
PAID = "Paid"
PENDING = "Pending"
CANCELED = "Canceled"


class MyFatoorahError(Exception):
    """MyFatoorah refused the call or could not be reached."""


def _client(config: MyFatoorahConfig) -> httpx.Client:
    if not config.api_key:
        raise MyFatoorahError("Payments are not connected yet. The MyFatoorah API token is missing.")
    return httpx.Client(
        base_url=config.base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
        timeout=TIMEOUT_SECONDS,
    )


def _body(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise MyFatoorahError("MyFatoorah sent an unreadable reply.") from exc
    if response.status_code >= 400 or not data.get("IsSuccess"):
        message = data.get("Message") or f"HTTP {response.status_code}"
        raise MyFatoorahError(f"MyFatoorah refused the request: {message}")
    return data


def send_payment(
    *,
    config: MyFatoorahConfig,
    amount: Decimal,
    currency: str,
    customer_name: str,
    customer_email: str | None,
    reference: str,
    callback_url: str,
    error_url: str,
) -> tuple[int, str]:
    """Create a hosted invoice. Returns (InvoiceId, InvoiceURL) for the customer to pay."""
    payload: dict[str, Any] = {
        "InvoiceValue": float(amount),
        "CustomerName": customer_name[:100] or "U-Tender contractor",
        "NotificationOption": "LNK",
        "DisplayCurrencyIso": currency,
        "Language": "EN",
        "CustomerReference": reference,
        "CallBackUrl": callback_url,
        "ErrorUrl": error_url,
    }
    if customer_email:
        payload["CustomerEmail"] = customer_email
    with _client(config) as client:
        data = _body(client.post("/v2/SendPayment", json=payload))["Data"]
    return int(data["InvoiceId"]), str(data["InvoiceURL"])


def get_payment_status(invoice_id: int, *, config: MyFatoorahConfig) -> str:
    """The invoice status as MyFatoorah reports it: Paid, Pending or Canceled."""
    with _client(config) as client:
        data = _body(client.post("/v2/GetPaymentStatus", json={"Key": str(invoice_id), "KeyType": "InvoiceId"}))["Data"]
    return str(data.get("InvoiceStatus", ""))


def _signed_text(data: dict[str, Any]) -> str:
    """The text MyFatoorah signs for a payment event. Nulls become empty strings."""
    invoice = data.get("Invoice") or {}
    transaction = data.get("Transaction") or {}
    fields = [
        ("Invoice.Id", invoice.get("Id")),
        ("Invoice.Status", invoice.get("Status")),
        ("Transaction.Status", transaction.get("Status")),
        ("Transaction.PaymentId", transaction.get("PaymentId")),
        ("Invoice.ExternalIdentifier", invoice.get("ExternalIdentifier")),
    ]
    return ",".join(f"{name}={'' if value is None else value}" for name, value in fields)


def signature_matches(data: dict[str, Any], header_value: str | None, *, secret: str | None) -> bool:
    """True when the webhook signature is correct. With no secret set this returns False and the caller
    must rely on GetPaymentStatus alone."""
    if not secret or not header_value:
        return False
    digest = hmac.new(secret.encode(), _signed_text(data).encode(), hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), header_value.strip())
