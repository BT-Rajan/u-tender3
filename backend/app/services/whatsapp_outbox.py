import logging
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.whatsapp import (
    OUTBOX_DEAD,
    OUTBOX_FAILED,
    OUTBOX_PENDING,
    OUTBOX_SENT,
    TEMPLATE_APPROVED,
    WhatsAppOutbox,
    WhatsAppTemplateStatus,
)
from app.services.whatsapp_client import WhatsAppSendError, mask_recipient

logger = logging.getLogger("utender.whatsapp")

KIND_TEMPLATE = "template"
KIND_TEXT = "text"
KIND_FLOW = "flow"
KIND_CTA_URL = "cta_url"
KINDS = (KIND_TEMPLATE, KIND_TEXT, KIND_FLOW, KIND_CTA_URL)

# Params that are bearer credentials (a Flow session token or an upload link). They're removed once the row is finished.
_SECRET_PARAMS = ("flow_token", "url")

HOLD_SECONDS = 15 * 60  # how long a template waiting on Meta's review is parked before the next check
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

    def send_flow(
        self,
        to_wa_id: str,
        *,
        flow_id: str,
        flow_token: str,
        screen: str,
        body: str,
        cta: str,
        header: str | None = None,
    ) -> str: ...

    def send_cta_url(self, to_wa_id: str, *, body: str, display_text: str, url: str) -> str: ...


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
    if kind not in KINDS:
        raise ValueError(f"Unknown outbox kind: {kind}")
    if kind == KIND_TEMPLATE and not template_name:
        raise ValueError("A template message needs a template_name.")
    if kind == KIND_FLOW and not (params and params.get("flow_id") and params.get("flow_token")):
        raise ValueError("A flow message needs a flow_id and flow_token.")
    if kind == KIND_CTA_URL and not (params and params.get("url") and params.get("display_text")):
        raise ValueError("A cta_url message needs a url and display_text.")

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


def template_is_approved(db: Session, name: str, language: str) -> bool:
    status = db.scalar(
        select(WhatsAppTemplateStatus.status).where(
            WhatsAppTemplateStatus.name == name, WhatsAppTemplateStatus.language == language
        )
    )
    return status == TEMPLATE_APPROVED


def _send_row(sender: MessageSender, row: WhatsAppOutbox) -> str:
    params = row.params_json or {}
    if row.kind == KIND_TEMPLATE:
        return sender.send_template(
            row.recipient_wa_id,
            row.template_name or "",
            params.get("language", "en"),
            params.get("components"),
        )
    if row.kind == KIND_FLOW:
        return sender.send_flow(
            row.recipient_wa_id,
            flow_id=str(params.get("flow_id", "")),
            flow_token=str(params.get("flow_token", "")),
            screen=str(params.get("screen", "")),
            body=str(params.get("body", "")),
            cta=str(params.get("cta", "Open")),
            header=params.get("header"),
        )
    if row.kind == KIND_CTA_URL:
        return sender.send_cta_url(
            row.recipient_wa_id,
            body=str(params.get("body", "")),
            display_text=str(params.get("display_text", "Open")),
            url=str(params.get("url", "")),
        )
    return sender.send_text(row.recipient_wa_id, str(params.get("body", "")))


def _clear_secrets(row: WhatsAppOutbox) -> None:
    """Drop bearer credentials once the row is finished.

    Flow tokens and upload URLs are removed. A row marked sensitive (a one-time
    code) also has its body redacted, so the code isn't kept after it has been
    sent.
    """
    params = row.params_json
    if not params:
        return
    needs_clearing = any(key in params for key in _SECRET_PARAMS) or params.get("sensitive")
    if not needs_clearing:
        return
    cleaned = {key: value for key, value in params.items() if key not in _SECRET_PARAMS}
    if cleaned.get("sensitive"):
        cleaned["body"] = "[redacted]"
    row.params_json = cleaned


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

    stats = {"sent": 0, "retry": 0, "failed": 0, "dead": 0, "held": 0}
    require_approval = get_settings().whatsapp_require_approved_templates
    for row in due:
        if row.kind == KIND_TEMPLATE and require_approval:
            language = str((row.params_json or {}).get("language", "en"))
            if not template_is_approved(db, row.template_name or "", language):
                # Not counted as an attempt: Meta hasn't rejected anything, the template just isn't approved yet.
                row.next_attempt_at = now + timedelta(seconds=HOLD_SECONDS)
                db.commit()
                stats["held"] += 1
                continue
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
            if row.status != OUTBOX_PENDING:
                _clear_secrets(row)
            db.commit()
            continue

        row.status = OUTBOX_SENT
        row.provider_message_id = message_id
        row.sent_at = now
        row.last_error_code = None
        _clear_secrets(row)
        db.commit()
        stats["sent"] += 1
        logger.info("WhatsApp outbox row %s sent to %s", row.id, mask_recipient(row.recipient_wa_id))

    return stats
