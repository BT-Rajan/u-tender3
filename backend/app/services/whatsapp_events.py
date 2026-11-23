import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.models.whatsapp import (
    EVENT_STATUS_FAILED,
    EVENT_STATUS_PROCESSED,
    EVENT_STATUS_RECEIVED,
    OUTBOX_FAILED,
    OUTBOX_SENT,
    WhatsAppMessageEvent,
    WhatsAppOutbox,
    WhatsAppTemplateStatus,
)
from app.services.whatsapp_outbox import _clear_secrets
from app.services.whatsapp_client import mask_recipient

logger = logging.getLogger("utender.whatsapp")

DIRECTION_INBOUND = "inbound"
DIRECTION_STATUS = "status"


@dataclass
class ParsedEvent:
    event_key: str
    direction: str
    event_type: str
    payload_sha256: str
    provider_message_id: str | None
    wa_id: str | None
    error_code: str | None = None
    # Kept in memory only for the handlers of this request. Never persisted.
    message: dict[str, Any] | None = None


@dataclass
class IntakeResult:
    new: list[WhatsAppMessageEvent] = field(default_factory=list)
    duplicates: int = 0
    failed_handlers: int = 0


# A handler receives each new inbound message once. Phase 2 registers the
# registration and routing handler here. An exception is logged by class name
# only, the event is marked failed, and the webhook still returns 200, so Meta
# doesn't retry a delivery we already recorded.
InboundHandler = Callable[[Session, WhatsAppMessageEvent, dict[str, Any]], None]
_inbound_handlers: list[InboundHandler] = []


def register_inbound_handler(handler: InboundHandler) -> None:
    _inbound_handlers.append(handler)


def clear_inbound_handlers() -> None:
    """Test hook: drop every registered handler."""
    _inbound_handlers.clear()


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_webhook(body: dict[str, Any]) -> list[ParsedEvent]:
    """Flatten a webhook body into one ParsedEvent per message and per status update.

    Only identifiers and a digest are kept. The message text, media ids and
    captions remain in the in-memory message dict and are never stored.
    """
    events: list[ParsedEvent] = []
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for message in value.get("messages") or []:
                message_id = message.get("id")
                if not message_id:
                    continue
                events.append(
                    ParsedEvent(
                        event_key=f"inbound:{message_id}",
                        direction=DIRECTION_INBOUND,
                        event_type=str(message.get("type", "unknown")),
                        payload_sha256=_digest(message),
                        provider_message_id=str(message_id),
                        wa_id=str(message["from"]) if message.get("from") else None,
                        message=message,
                    )
                )
            for status in value.get("statuses") or []:
                status_id = status.get("id")
                status_name = status.get("status")
                if not status_id or not status_name:
                    continue
                errors = status.get("errors") or []
                error_code = str(errors[0].get("code")) if errors and isinstance(errors[0], dict) and errors[0].get("code") is not None else None
                events.append(
                    ParsedEvent(
                        event_key=f"status:{status_id}:{status_name}",
                        direction=DIRECTION_STATUS,
                        event_type=f"status_{status_name}",
                        payload_sha256=_digest(status),
                        provider_message_id=str(status_id),
                        wa_id=str(status["recipient_id"]) if status.get("recipient_id") else None,
                        error_code=error_code,
                    )
                )
    return events


def _insert_once(db: Session, parsed: ParsedEvent, now: datetime) -> WhatsAppMessageEvent | None:
    """Insert one event under a savepoint. Returns None if the key already exists."""
    row = WhatsAppMessageEvent(
        event_key=parsed.event_key,
        direction=parsed.direction,
        event_type=parsed.event_type,
        provider_message_id=parsed.provider_message_id,
        wa_id=parsed.wa_id,
        payload_sha256=parsed.payload_sha256,
        status=EVENT_STATUS_RECEIVED,
        attempts=0,
        last_error_code=parsed.error_code,
        received_at=now,
    )
    try:
        with db.begin_nested():
            db.add(row)
    except IntegrityError:
        return None
    return row


TEMPLATE_FIELD = "message_template_status_update"


def apply_template_updates(db: Session, body: dict[str, Any]) -> int:
    """Record Meta's review state for each template named in the webhook. Idempotent: the same update twice leaves one row.

    Returns how many template states were recorded.
    """
    count = 0
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") != TEMPLATE_FIELD:
                continue
            value = change.get("value") or {}
            name = str(value.get("message_template_name") or "")
            language = str(value.get("message_template_language") or "")
            event = str(value.get("event") or "")
            if not name or not language or not event:
                continue
            row = db.scalar(
                select(WhatsAppTemplateStatus).where(
                    WhatsAppTemplateStatus.name == name, WhatsAppTemplateStatus.language == language
                )
            )
            if row is None:
                db.add(WhatsAppTemplateStatus(name=name, language=language, status=event))
            else:
                row.status = event
            count += 1
    if count:
        db.commit()
    return count


def apply_delivery_failure(db: Session, parsed: ParsedEvent) -> bool:
    """A message we accepted was later reported failed. Mark its outbox row failed and drop its credentials.

    Only a row that was sent is changed. A row still pending is left for the dispatcher, and a row
    already in a final state is not touched.
    """
    if not parsed.provider_message_id:
        return False
    row = db.scalar(select(WhatsAppOutbox).where(WhatsAppOutbox.provider_message_id == parsed.provider_message_id))
    if row is None or row.status != OUTBOX_SENT:
        return False
    row.status = OUTBOX_FAILED
    row.last_error_code = parsed.error_code or "delivery_failed"
    _clear_secrets(row)
    return True


def record_events(db: Session, body: dict[str, Any], *, now: datetime) -> IntakeResult:
    """Store each event once and run inbound handlers for the new messages.

    Duplicate deliveries are detected by the unique event_key. Re-running the
    same webhook adds no rows and calls no handler a second time.
    """
    apply_template_updates(db, body)
    result = IntakeResult()
    for parsed in parse_webhook(body):
        row = _insert_once(db, parsed, now)
        if row is None:
            result.duplicates += 1
            continue

        if parsed.direction == DIRECTION_INBOUND and parsed.message is not None:
            row.attempts = 1
            try:
                for handler in list(_inbound_handlers):
                    handler(db, row, parsed.message)
                row.status = EVENT_STATUS_PROCESSED
                row.processed_at = now
            except Exception as exc:  # noqa: BLE001 - recorded, not re-raised, so Meta gets 200
                row.status = EVENT_STATUS_FAILED
                row.last_error_code = type(exc).__name__
                result.failed_handlers += 1
                # Class name only. The exception message and traceback can echo
                # message text, so they are never logged.
                logger.error("WhatsApp inbound handler failed for event %s (%s)", row.id, type(exc).__name__)
        else:
            row.status = EVENT_STATUS_PROCESSED
            row.processed_at = now
            if parsed.event_type == "status_failed":
                apply_delivery_failure(db, parsed)

        result.new.append(row)
        logger.info(
            "WhatsApp event recorded: direction=%s type=%s from=%s",
            parsed.direction,
            parsed.event_type,
            mask_recipient(parsed.wa_id) if parsed.wa_id else "-",
        )

    db.commit()
    return result
