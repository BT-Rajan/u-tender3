"""The relay from Cogzi: request checks, message conversion and the replies sent back through Cogzi.

Cogzi receives WhatsApp messages and posts the ones for U-Tender here, signed. U-Tender runs the
same routing as its own webhook, and returns the replies in the response. Cogzi sends them.
Cogzi never holds a file: a file is only a WhatsApp media ID, and U-Tender fetches it from Meta.
"""

import hashlib
import hmac
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.whatsapp import WhatsAppIdentity, WhatsAppOutbox
from app.services.whatsapp_outbox import KIND_FLOW, KIND_TEXT, OUTBOX_PENDING, OUTBOX_SENT

TIMESTAMP_HEADER = "X-Cogzi-Timestamp"
SIGNATURE_HEADER = "X-Cogzi-Signature"
RELAY_EVENT = "whatsapp.message"
TRIGGER = re.compile(r"\butender\b", re.IGNORECASE)
# How far back a reply may have been queued and still belong to this request.
REPLY_WINDOW = timedelta(minutes=2)


def verify_signature(
    raw_body: bytes,
    timestamp: str | None,
    signature: str | None,
    secret: str | None,
    *,
    now: int,
    max_skew_seconds: int,
) -> bool:
    """True when the request was signed with the shared secret and is recent enough to trust."""
    if not secret or not timestamp or not signature:
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(now - sent_at) > max_skew_seconds:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def wa_id_of(phone: str) -> str:
    """WhatsApp IDs are the digits of the number, without the leading plus."""
    return "".join(ch for ch in phone if ch.isdigit())


def should_answer(db: Session, message: dict[str, Any], *, phone_number_id: str, own_number_id: str | None) -> bool:
    """Every message on U-Tender's own number is answered. Elsewhere a new user must say the trigger word first.
    Someone already registered, or a completed Flow, is always answered."""
    if own_number_id and phone_number_id == own_number_id:
        return True
    if message.get("type") == "interactive":
        return True
    body = message.get("body")
    if isinstance(body, str) and TRIGGER.search(body):
        return True
    return db.scalar(select(WhatsAppIdentity.id).where(WhatsAppIdentity.wa_id == wa_id_of(message["from"]))) is not None


def to_meta_payload(payload: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """The relayed message in the shape of a Meta webhook, so the existing routing handles it unchanged."""
    message = payload["message"]
    wa_id = wa_id_of(message["from"])
    meta_message: dict[str, Any] = {
        "from": wa_id,
        "id": message["id"],
        "timestamp": str(message.get("timestamp") or int(now.timestamp())),
        "type": message["type"],
    }
    if message["type"] == "text":
        meta_message["text"] = {"body": message.get("body") or ""}
    elif isinstance(message.get("interactive"), dict):
        meta_message["interactive"] = message["interactive"]
    elif message.get("media"):
        media = message["media"]
        meta_message[message["type"]] = {"id": media["id"], "mime_type": media.get("mime_type"), "filename": media.get("filename")}

    contact: dict[str, Any] = {"wa_id": wa_id}
    if message.get("name"):
        contact["profile"] = {"name": message["name"]}

    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "cogzi-relay",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": payload["phone_number_id"]},
                    "contacts": [contact],
                    "messages": [meta_message],
                },
            }],
        }],
    }


def take_replies(db: Session, *, recipient_wa_id: str, now: datetime) -> list[dict[str, Any]]:
    """The messages this request queued for the sender, as replies for Cogzi to send. Each is marked sent,
    so the U-Tender dispatcher never sends it a second time."""
    rows = db.scalars(
        select(WhatsAppOutbox)
        .where(
            WhatsAppOutbox.recipient_wa_id == recipient_wa_id,
            WhatsAppOutbox.status == OUTBOX_PENDING,
            WhatsAppOutbox.created_at >= now - REPLY_WINDOW,
        )
        .order_by(WhatsAppOutbox.created_at, WhatsAppOutbox.id)
    ).all()

    replies: list[dict[str, Any]] = []
    for row in rows:
        params = dict(row.params_json or {})
        if row.kind == KIND_TEXT:
            reply: dict[str, Any] = {"type": "text", "body": params.get("body", "")}
        elif row.kind == KIND_FLOW:
            reply = {
                "type": "flow",
                "flow_id": params["flow_id"],
                "flow_token": params["flow_token"],
                "screen": params.get("screen"),
                "body": params.get("body"),
                "cta": params.get("cta"),
            }
        else:
            # Templates and link buttons still go out through U-Tender's own dispatcher; the relay does not carry them yet.
            continue
        replies.append(reply)
        row.status = OUTBOX_SENT
        row.provider_message_id = "relayed-to-cogzi"
        row.params_json = {key: value for key, value in params.items() if key not in ("flow_token", "url")}
    return replies
