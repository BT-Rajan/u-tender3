import hmac
import json
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import get_db
from app.services.flow_crypto import (
    FlowCryptoError,
    decrypt_request,
    encrypt_response,
    load_private_key,
)
from app.services.whatsapp_client import WhatsAppCloudClient, WhatsAppSendError
from app.services.whatsapp_events import record_events
from app.services.whatsapp_outbox import KIND_BUTTONS, TENDER_NUMBER_PREFIX, dispatch_due
from app.services.whatsapp_signature import verify_signature

router = APIRouter(tags=["whatsapp"])
logger = logging.getLogger("utender.whatsapp")
# Flow requests are logged at INFO so a failure can be traced. stdout is kept by pm2.
logger.setLevel(logging.INFO)
if not logger.handlers:
    _console = logging.StreamHandler(sys.stdout)
    _console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_console)

# Status codes WhatsApp acts on for the Flow data endpoint. 432: the signature
# does not verify. 421: the request can't be decrypted with this key, and
# WhatsApp then refetches the key and retries.
FLOW_BAD_SIGNATURE_STATUS = 432
FLOW_CANNOT_DECRYPT_STATUS = 421

# Flow handlers answer the actions that carry real screen logic (INIT, BACK,
# data_exchange). A handler gets the DB session and the decrypted payload, and
# returns a reply dict, or None to pass to the next one.
FlowHandler = Callable[[Session, dict[str, Any]], dict[str, Any] | None]
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
    # Send what the inbound handlers just queued now, not on the next cron tick.
    # The send is blocking I/O, so it runs in a threadpool. A failure is logged
    # and left in the outbox, where the cron retries it.
    await run_in_threadpool(dispatch_outbox_now, db)
    return {"received": True}


def dispatch_outbox_now(db: Session, kinds: tuple[str, ...] | None = None, dedupe_prefixes: tuple[str, ...] | None = None) -> None:
    settings = get_settings()
    if not settings.whatsapp_enabled:
        return
    try:
        sender = build_whatsapp_sender()
    except WhatsAppSendError:
        logger.error("WhatsApp outbox not dispatched: the sender is not configured")
        return
    try:
        dispatch_due(db, sender, now=datetime.utcnow(), max_attempts=settings.whatsapp_outbox_max_attempts, kinds=kinds, dedupe_prefixes=dedupe_prefixes)
    except Exception:  # noqa: BLE001 - the webhook must still acknowledge Meta
        logger.exception("WhatsApp outbox dispatch failed; the cron will retry")
    finally:
        sender.close()


def build_whatsapp_sender() -> WhatsAppCloudClient:
    """Indirection so tests can substitute a sender without touching the network."""
    return WhatsAppCloudClient.from_settings(get_settings())


def _flow_reply(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")

    if action == "ping":
        return {"data": {"status": "active"}}
    if action == "error_notification":
        # WhatsApp reports here when a Flow screen fails on the customer's phone. Log what it reports.
        logger.warning("Flow screen failed on the phone: screen=%s details=%s", payload.get("screen"), str(payload.get("data"))[:800])
        return {"data": {"acknowledged": True}}

    for handler in list(_flow_handlers):
        handled = handler(db, payload)
        if handled is not None:
            return handled

    # No handler knew this request. Close the Flow with a message. A screen sent back without the
    # fields it shows makes WhatsApp fail with "Something went wrong", so the fallback never names one.
    return {"screen": "DONE", "data": {"heading": "", "message": "This form is no longer available. Send any message to open your dashboard."}}


@router.post("/whatsapp/flows")
async def flow_data_endpoint(request: Request, db: Session = Depends(get_db)) -> Response:
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

    reply = _flow_reply(db, decrypted.payload)
    request_data = decrypted.payload.get("data") if isinstance(decrypted.payload.get("data"), dict) else {}
    logger.info(
        "Flow request action=%s screen=%s fields=%s -> reply screen=%s",
        decrypted.payload.get("action"),
        decrypted.payload.get("screen"),
        sorted(request_data),
        reply.get("screen") if isinstance(reply, dict) else None,
    )
    # A sign-up may have just queued its "account created" buttons. Send those now; other queued messages wait for their usual dispatch.
    await run_in_threadpool(dispatch_outbox_now, db, (KIND_BUTTONS,), (TENDER_NUMBER_PREFIX,))
    encrypted = encrypt_response(reply, decrypted.aes_key, decrypted.iv)
    return Response(content=encrypted, media_type="text/plain")
