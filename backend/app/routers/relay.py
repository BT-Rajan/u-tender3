import json
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.utender_relay import (
    RELAY_EVENT,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    should_answer,
    take_replies,
    to_meta_payload,
    verify_signature,
    wa_id_of,
)
from app.services.whatsapp_events import record_events

router = APIRouter(tags=["relay"])
logger = logging.getLogger("utender.relay")


@router.post("/relay/whatsapp")
async def receive_relayed_message(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """A message Cogzi relays from WhatsApp. Returns the replies for Cogzi to send; sends nothing itself."""
    settings = get_settings()
    if not settings.relay_secret:
        raise HTTPException(status_code=503, detail="The U-Tender relay is not configured.")

    raw_body = await request.body()
    if not verify_signature(
        raw_body,
        request.headers.get(TIMESTAMP_HEADER),
        request.headers.get(SIGNATURE_HEADER),
        settings.relay_secret,
        now=int(time.time()),
        max_skew_seconds=settings.relay_max_skew_seconds,
    ):
        logger.warning("Relay request rejected: signature or timestamp did not verify")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON") from exc
    if not isinstance(payload, dict) or payload.get("event") != RELAY_EVENT or not isinstance(payload.get("message"), dict):
        raise HTTPException(status_code=400, detail="Unsupported event")

    now = datetime.utcnow()
    message = payload["message"]
    if not should_answer(db, message, phone_number_id=str(payload.get("phone_number_id", "")), own_number_id=settings.whatsapp_phone_number_id):
        # A new user who did not say the trigger word gets nothing, and nothing is stored for them.
        return {"replies": []}

    record_events(db, to_meta_payload(payload, now=now), now=now)
    replies = take_replies(db, recipient_wa_id=wa_id_of(message["from"]), now=now)
    db.commit()
    return {"replies": replies}
