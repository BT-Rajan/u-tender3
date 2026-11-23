import hmac
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.flow_crypto import (
    FlowCryptoError,
    decrypt_request,
    encrypt_response,
    load_private_key,
)
from app.services.whatsapp_events import record_events
from app.services.whatsapp_signature import verify_signature

router = APIRouter(tags=["whatsapp"])
logger = logging.getLogger("utender.whatsapp")

# Status codes WhatsApp acts on for the Flow data endpoint. 432: the signature
# does not verify. 421: the request can't be decrypted with this key, and
# WhatsApp then refetches the key and retries.
FLOW_BAD_SIGNATURE_STATUS = 432
FLOW_CANNOT_DECRYPT_STATUS = 421

# Flow handlers answer the actions that carry real screen logic (INIT, BACK,
# data_exchange). Phase 2 registers the registration and dashboard handlers
# here. A handler returns a reply dict, or None to pass to the next one.
FlowHandler = Callable[[dict[str, Any]], dict[str, Any] | None]
_flow_handlers: list[FlowHandler] = []


def register_flow_handler(handler: FlowHandler) -> None:
    _flow_handlers.append(handler)


def clear_flow_handlers() -> None:
    """Test hook: drop every registered Flow handler."""
    _flow_handlers.clear()


def _whatsapp_enabled_or_404() -> None:
    if not get_settings().whatsapp_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/whatsapp/webhook")
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    """Meta's subscription handshake. Echoes hub.challenge only when the verify token matches."""
    _whatsapp_enabled_or_404()
    expected = get_settings().whatsapp_verify_token
    if (
        hub_mode == "subscribe"
        and expected
        and hub_verify_token is not None
        and hmac.compare_digest(hub_verify_token, expected)
        and hub_challenge is not None
    ):
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    """Receive messages and status updates. The signature is checked over the raw bytes before parsing."""
    _whatsapp_enabled_or_404()
    raw_body = await request.body()

    if not verify_signature(raw_body, request.headers.get("X-Hub-Signature-256"), get_settings().whatsapp_app_secret):
        logger.warning("WhatsApp webhook rejected: signature did not verify")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        body = json.loads(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Malformed payload")

    record_events(db, body, now=datetime.utcnow())
    return {"received": True}


def _flow_reply(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")

    if action == "ping":
        return {"data": {"status": "active"}}
    if action == "error_notification":
        return {"data": {"acknowledged": True}}

    for handler in list(_flow_handlers):
        handled = handler(payload)
        if handled is not None:
            return handled

    screen = payload.get("screen")
    fallback: dict[str, Any] = {"data": {"error_message": "This form is not available. Please try again later."}}
    if isinstance(screen, str) and screen:
        fallback["screen"] = screen
    return fallback


@router.post("/whatsapp/flows")
async def flow_data_endpoint(request: Request) -> Response:
    """The data endpoint every Flow calls. Requests are signed, then encrypted for U-Tender's Flow key."""
    _whatsapp_enabled_or_404()
    settings = get_settings()
    raw_body = await request.body()

    if not verify_signature(raw_body, request.headers.get("X-Hub-Signature-256"), settings.whatsapp_app_secret):
        return PlainTextResponse("Invalid signature", status_code=FLOW_BAD_SIGNATURE_STATUS)

    if not settings.whatsapp_flow_private_key:
        logger.error("WhatsApp Flow request received but no Flow private key is configured")
        return PlainTextResponse("Encryption key not set up", status_code=FLOW_CANNOT_DECRYPT_STATUS)

    try:
        private_key = load_private_key(settings.whatsapp_flow_private_key)
        body = json.loads(raw_body)
        if not isinstance(body, dict):
            raise FlowCryptoError("Not an object.")
        decrypted = decrypt_request(body, private_key)
    except (FlowCryptoError, ValueError):
        return PlainTextResponse("Cannot decrypt", status_code=FLOW_CANNOT_DECRYPT_STATUS)

    reply = _flow_reply(decrypted.payload)
    encrypted = encrypt_response(reply, decrypted.aes_key, decrypted.iv)
    return Response(content=encrypted, media_type="text/plain")
