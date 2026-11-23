import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.whatsapp import WhatsAppFlowSession, WhatsAppIdentity

DEFAULT_FLOW_SESSION_TTL = timedelta(hours=24)


def normalise_wa_id(raw: str) -> str:
    """WhatsApp ids are digits only, with the country code and no leading '+'. Anything else is refused."""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits or len(digits) < 7 or len(digits) > 15:
        raise ValueError("Not a valid WhatsApp number.")
    return digits


def get_or_create_identity(db: Session, raw_wa_id: str, *, now: datetime) -> WhatsAppIdentity:
    """Return the identity for a WhatsApp number, creating it if needed.

    Two webhooks from one new number can race. The unique wa_id constraint
    settles it: the loser's insert fails, it rolls back to a savepoint and reads
    the winner's row.
    """
    wa_id = normalise_wa_id(raw_wa_id)
    existing = db.scalar(select(WhatsAppIdentity).where(WhatsAppIdentity.wa_id == wa_id))
    if existing is not None:
        existing.last_seen_at = now
        db.commit()
        return existing

    identity = WhatsAppIdentity(wa_id=wa_id, phone_e164=f"+{wa_id}", last_seen_at=now)
    try:
        with db.begin_nested():
            db.add(identity)
    except IntegrityError:
        db.rollback()
        return db.scalars(select(WhatsAppIdentity).where(WhatsAppIdentity.wa_id == wa_id)).one()

    db.commit()
    return identity


def hash_flow_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_flow_session(
    db: Session,
    identity: WhatsAppIdentity,
    *,
    flow_name: str,
    now: datetime,
    screen: str | None = None,
    state: dict[str, Any] | None = None,
    ttl: timedelta = DEFAULT_FLOW_SESSION_TTL,
) -> tuple[WhatsAppFlowSession, str]:
    """Create a session and return it with the raw token, which is never stored and is shown once."""
    raw_token = secrets.token_urlsafe(32)
    session = WhatsAppFlowSession(
        identity_id=identity.id,
        flow_name=flow_name,
        flow_token_hash=hash_flow_token(raw_token),
        screen=screen,
        state_json=state,
        expires_at=now + ttl,
    )
    db.add(session)
    db.commit()
    return session, raw_token


def find_active_flow_session(db: Session, raw_token: str, *, now: datetime) -> WhatsAppFlowSession | None:
    """Look up a live session by token. Expired or completed sessions are not returned."""
    if not raw_token:
        return None
    session = db.scalar(
        select(WhatsAppFlowSession).where(WhatsAppFlowSession.flow_token_hash == hash_flow_token(raw_token))
    )
    if session is None or session.completed_at is not None or session.expires_at <= now:
        return None
    return session


def complete_flow_session(db: Session, session: WhatsAppFlowSession, *, now: datetime) -> None:
    """Mark a flow finished and clear its state, so no answers linger after completion."""
    session.completed_at = now
    session.state_json = None
    db.commit()
