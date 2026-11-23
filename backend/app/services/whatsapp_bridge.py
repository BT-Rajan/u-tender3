"""Option 1 bridge: messages for a number that Cogzi still owns, forwarded to U-Tender by Cogzi.

Cogzi sends a 'message.received' event for each inbound message on its outgoing webhook, signed with
HMAC-SHA256 of the raw body using the webhook secret. This module checks that signature, keeps only the
trigger word, and turns the event into the same envelope Meta would send. The existing intake then
handles it, so idempotency (by WhatsApp message id) and routing are unchanged.
"""

from typing import Any

from app.config import Settings
from app.services.whatsapp_signature import verify_signature

FORWARDED_EVENT = "message.received"


def verify_bridge_signature(raw_body: bytes, signature_header: str | None, settings: Settings) -> bool:
    return verify_signature(raw_body, signature_header, settings.whatsapp_bridge_secret)


def envelope_for_trigger(event: dict[str, Any], settings: Settings) -> dict[str, Any] | None:
    """The Meta-style envelope for a trigger message, or None when the event should be ignored."""
    if event.get("event") != FORWARDED_EVENT:
        return None
    data = event.get("data") or {}
    message = data.get("message") or {}
    sender = data.get("sender") or {}
    message_id = data.get("message_id")
    phone = sender.get("phone")
    body = message.get("body")

    if message.get("type") != "text" or not message_id or not phone or not isinstance(body, str):
        return None
    if body.strip().lower() != settings.whatsapp_bridge_trigger.strip().lower():
        return None

    meta_message = {
        "from": str(phone).lstrip("+"),
        "id": str(message_id),
        "timestamp": "0",
        "type": "text",
        "text": {"body": body},
    }
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "cogzi-bridge", "changes": [{"field": "messages", "value": {"messages": [meta_message]}}]}],
    }
