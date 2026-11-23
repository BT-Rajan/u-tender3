import logging
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.whatsapp import (
    OUTBOX_DEAD,
    OUTBOX_FAILED,
    OUTBOX_PENDING,
    OUTBOX_SENT,
    WhatsAppOutbox,
)
from app.services.whatsapp_client import WhatsAppSendError, mask_recipient

logger = logging.getLogger("utender.whatsapp")

KIND_TEMPLATE = "template"
KIND_TEXT = "text"

BASE_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 60 * 60
DEFAULT_BATCH_SIZE = 50


class MessageSender(Protocol):
    def send_text(self, to_wa_id: str, body: str) -> str: ...

    def send_template(
        self,
        to_wa_id: str,
        template_name: str,
        language_code: str,
        components: list[dict[str, Any]] | None = None,
    ) -> str: ...


def backoff_seconds(attempts: int) -> int:
    """Exponential backoff: 30s, 60s, 120s, ... capped at one hour."""
    return min(MAX_BACKOFF_SECONDS, BASE_BACKOFF_SECONDS * (2 ** max(0, attempts - 1)))


def enqueue(
    db: Session,
    *,
    dedupe_key: str,
    recipient_wa_id: str,
    kind: str,
    now: datetime,
    template_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> WhatsAppOutbox:
    """Queue a message in the caller's transaction. Returns the existing row for a repeated dedupe_key.

    The caller commits. Nothing is sent until the dispatcher runs after that
    commit, so a rolled-back business change never produces a message.
    """
    if kind not in (KIND_TEMPLATE, KIND_TEXT):
        raise ValueError(f"Unknown outbox kind: {kind}")
    if kind == KIND_TEMPLATE and not template_name:
        raise ValueError("A template message needs a template_name.")

    existing = db.scalar(select(WhatsAppOutbox).where(WhatsAppOutbox.dedupe_key == dedupe_key))
    if existing is not None:
        return existing

    row = WhatsAppOutbox(
        dedupe_key=dedupe_key,
        recipient_wa_id=recipient_wa_id,
        kind=kind,
        template_name=template_name,
        params_json=params or None,
        status=OUTBOX_PENDING,
        attempts=0,
        next_attempt_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _send_row(sender: MessageSender, row: WhatsAppOutbox) -> str:
    params = row.params_json or {}
    if row.kind == KIND_TEMPLATE:
        return sender.send_template(
            row.recipient_wa_id,
            row.template_name or "",
            params.get("language", "en"),
            params.get("components"),
        )
    return sender.send_text(row.recipient_wa_id, str(params.get("body", "")))


def dispatch_due(
    db: Session,
    sender: MessageSender,
    *,
    now: datetime,
    max_attempts: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """Send every pending row whose next_attempt_at has passed.

    Each row is committed on its own, so one failure never blocks the rest and a
    crash mid-batch only repeats the row that was in flight. A transient error
    schedules a retry, and once max_attempts is spent the row becomes dead. A
    permanent error (for example Meta rejecting the template) marks it failed
    straight away, with no retry.
    """
    due = db.scalars(
        select(WhatsAppOutbox)
        .where(WhatsAppOutbox.status == OUTBOX_PENDING, WhatsAppOutbox.next_attempt_at <= now)
        .order_by(WhatsAppOutbox.next_attempt_at)
        .limit(batch_size)
    ).all()

    stats = {"sent": 0, "retry": 0, "failed": 0, "dead": 0}
    for row in due:
        row.attempts += 1
        try:
            message_id = _send_row(sender, row)
        except WhatsAppSendError as error:
            row.last_error_code = error.error_code or ("transport" if error.status_code is None else str(error.status_code))
            if error.transient and row.attempts < max_attempts:
                row.next_attempt_at = now + timedelta(seconds=backoff_seconds(row.attempts))
                stats["retry"] += 1
            elif error.transient:
                row.status = OUTBOX_DEAD
                stats["dead"] += 1
                logger.error("WhatsApp outbox row %s is dead after %s attempts", row.id, row.attempts)
            else:
                row.status = OUTBOX_FAILED
                stats["failed"] += 1
                logger.warning("WhatsApp outbox row %s failed permanently (%s)", row.id, row.last_error_code)
            db.commit()
            continue

        row.status = OUTBOX_SENT
        row.provider_message_id = message_id
        row.sent_at = now
        row.last_error_code = None
        db.commit()
        stats["sent"] += 1
        logger.info("WhatsApp outbox row %s sent to %s", row.id, mask_recipient(row.recipient_wa_id))

    return stats
