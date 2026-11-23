from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid

# Status and direction values are plain strings rather than DB enums so a new
# state can be added without a migration on MySQL. The constants below are the
# only values the application writes.
EVENT_STATUS_RECEIVED = "received"
EVENT_STATUS_PROCESSED = "processed"
EVENT_STATUS_FAILED = "failed"

OUTBOX_PENDING = "pending"
OUTBOX_SENT = "sent"
OUTBOX_FAILED = "failed"  # permanent error, e.g. Meta rejected the template
OUTBOX_DEAD = "dead"  # transient errors exhausted every retry


class WhatsAppIdentity(Base):
    """Maps a WhatsApp number to a U-Tender user.

    Registration is WhatsApp-only, so a WhatsApp identity may exist before it is
    linked to a user (user_id stays NULL until registration completes). Both wa_id
    and phone_e164 are unique: one number, one identity.
    """

    __tablename__ = "whatsapp_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    wa_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    # Unique: one WhatsApp number maps to one user, and one user has one number.
    # This is the database-level guard behind "prevent duplicate accounts".
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True, index=True
    )
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "owner" | "contractor" once chosen
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WhatsAppMessageEvent(Base):
    """A delivery we have already handled, keyed for idempotency.

    Meta redelivers webhooks, so every inbound message (keyed by its wamid) and
    every status update (keyed by message id + status) is inserted once.
    The unique event_key is what makes a duplicate delivery a no-op.

    Message bodies are never stored here. Only a SHA-256 of the raw message
    object is kept, which is enough to tell a true redelivery from a
    different payload that reuses an id.
    """

    __tablename__ = "whatsapp_message_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    event_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # "inbound" | "status"
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    wa_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=EVENT_STATUS_RECEIVED, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WhatsAppFlowSession(Base):
    """Server-side state for one customer's place in a WhatsApp Flow.

    Meta gives the Flow a flow_token. Only its SHA-256 is stored, so a leaked
    table can't be replayed as live tokens. state_json holds just the screen
    and the fields the flow needs to resume. It is cleared once the flow
    completes.
    """

    __tablename__ = "whatsapp_flow_sessions"
    __table_args__ = (UniqueConstraint("flow_token_hash", name="uq_whatsapp_flow_token"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("whatsapp_identities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flow_name: Mapped[str] = mapped_column(String(64), nullable=False)
    flow_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    screen: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WhatsAppOutbox(Base):
    """Transactional outbox for every outgoing WhatsApp message.

    Business code enqueues a row inside its own transaction, so a message is
    never sent for a change that rolled back. A dispatcher sends due rows and
    retries transient failures with backoff. dedupe_key is unique, so the same
    event enqueued twice sends once.
    """

    __tablename__ = "whatsapp_outbox"
    __table_args__ = (Index("ix_whatsapp_outbox_status_next", "status", "next_attempt_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dedupe_key: Mapped[str] = mapped_column(String(191), unique=True, nullable=False)
    recipient_wa_id: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "template" | "text"
    template_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=OUTBOX_PENDING)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
