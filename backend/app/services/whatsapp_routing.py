from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import UserRole
from app.models.user import User
from app.models.whatsapp import WhatsAppFlowSession, WhatsAppIdentity, WhatsAppMessageEvent
from app.routers.whatsapp import register_flow_handler
from app.services import whatsapp_outbox
from app.services.whatsapp_events import register_inbound_handler
from app.services.whatsapp_identity import complete_flow_session, create_flow_session, get_or_create_identity
from app.services.whatsapp_flows import (
    FLOW_CONTRACTOR_DASHBOARD,
    FLOW_OWNER_DASHBOARD,
    FLOW_REGISTRATION,
    handle_flow_request,
)

REGISTRATION_BODY = "Welcome to U-Tender. Tap below to create your account. It takes under a minute."
DASHBOARD_BODY = "Open your U-Tender dashboard."
ADMIN_TEXT = "Admin accounts are managed on the U-Tender web dashboard."
SETUP_TEXT = "U-Tender WhatsApp is being set up. Please try again shortly."

# Only this word (any capitalisation, surrounding spaces ignored) opens the
# flows. Any other text gets HINT_TEXT, so the number does nothing until a
# user deliberately asks for it.
TRIGGER_KEYWORD = "utender"
HINT_TEXT = 'Send the word "utender" to open U-Tender.'


def _is_nfm_reply(message: dict[str, Any]) -> bool:
    """A completed Flow. The Flow data endpoint has already acted on it, so the router must not reply to it."""
    interactive = message.get("interactive")
    return message.get("type") == "interactive" and isinstance(interactive, dict) and interactive.get("type") == "nfm_reply"


def _find_resumable_registration(db: Session, identity: WhatsAppIdentity, *, now: datetime) -> WhatsAppFlowSession | None:
    """The newest registration session that is unfinished and still in date."""
    return db.scalar(
        select(WhatsAppFlowSession)
        .where(
            WhatsAppFlowSession.identity_id == identity.id,
            WhatsAppFlowSession.flow_name == FLOW_REGISTRATION,
            WhatsAppFlowSession.completed_at.is_(None),
            WhatsAppFlowSession.expires_at > now,
        )
        .order_by(WhatsAppFlowSession.created_at.desc(), WhatsAppFlowSession.expires_at.desc())
    )


def _queue_flow(
    db: Session,
    event: WhatsAppMessageEvent,
    identity: WhatsAppIdentity,
    session: WhatsAppFlowSession,
    raw_token: str,
    *,
    flow_setting: str,
    screen: str,
    body: str,
    cta: str,
    now: datetime,
) -> None:
    flow_id = getattr(get_settings(), flow_setting)
    if not flow_id:
        whatsapp_outbox.enqueue(
            db,
            dedupe_key=f"text:{event.id}",
            recipient_wa_id=identity.wa_id,
            kind=whatsapp_outbox.KIND_TEXT,
            now=now,
            params={"body": SETUP_TEXT},
        )
        return
    whatsapp_outbox.enqueue(
        db,
        dedupe_key=f"flow:{session.id}",
        recipient_wa_id=identity.wa_id,
        kind=whatsapp_outbox.KIND_FLOW,
        now=now,
        params={
            "flow_id": flow_id,
            "flow_token": raw_token,
            "screen": screen,
            "body": body,
            "cta": cta,
        },
    )


def _start_registration(db: Session, identity: WhatsAppIdentity, event: WhatsAppMessageEvent, *, now: datetime) -> None:
    """Open the registration Flow, resuming an unfinished one with its saved place and answers."""
    previous = _find_resumable_registration(db, identity, now=now)
    screen = "SPLASH"
    state: dict[str, Any] | None = None
    if previous is not None:
        screen = previous.screen or "SPLASH"
        state = previous.state_json
        complete_flow_session(db, previous, now=now)

    session, raw_token = create_flow_session(
        db,
        identity,
        flow_name=FLOW_REGISTRATION,
        now=now,
        screen=screen,
        state=state,
        ttl=timedelta(hours=24),
    )
    _queue_flow(
        db,
        event,
        identity,
        session,
        raw_token,
        flow_setting="whatsapp_flow_id_registration",
        screen="SPLASH",
        body=REGISTRATION_BODY,
        cta="Start",
        now=now,
    )


def _open_dashboard(
    db: Session, identity: WhatsAppIdentity, event: WhatsAppMessageEvent, user: User, *, now: datetime
) -> None:
    is_owner = user.role == UserRole.owner
    flow_name = FLOW_OWNER_DASHBOARD if is_owner else FLOW_CONTRACTOR_DASHBOARD
    session, raw_token = create_flow_session(db, identity, flow_name=flow_name, now=now)
    _queue_flow(
        db,
        event,
        identity,
        session,
        raw_token,
        flow_setting="whatsapp_flow_id_owner_dashboard" if is_owner else "whatsapp_flow_id_contractor_dashboard",
        screen="MENU",
        body=DASHBOARD_BODY,
        cta="Open",
        now=now,
    )


def _send_text(db: Session, identity: WhatsAppIdentity, event: WhatsAppMessageEvent, body: str, *, now: datetime) -> None:
    whatsapp_outbox.enqueue(
        db,
        dedupe_key=f"text:{event.id}",
        recipient_wa_id=identity.wa_id,
        kind=whatsapp_outbox.KIND_TEXT,
        now=now,
        params={"body": body},
    )


def _is_trigger(message: dict[str, Any]) -> bool:
    if message.get("type") != "text":
        return False
    body = (message.get("text") or {}).get("body")
    return isinstance(body, str) and body.strip().lower() == TRIGGER_KEYWORD


def handle_inbound_message(db: Session, event: WhatsAppMessageEvent, message: dict[str, Any]) -> None:
    """Route a message to the right flow, as an inbound handler.

    Only a message whose text is the trigger word ("utender") starts anything.
    Any other text gets a one-line hint and no identity is created for it.

    On the trigger:
    1. Resolve the number to an identity, creating it if new.
    2. Owner -> Owner Dashboard Flow. Contractor -> Contractor Dashboard Flow.
    3. Admin -> a text pointing to the web dashboard.
    4. No account -> registration, resuming an unfinished one if there is one.
    """
    if _is_nfm_reply(message):
        return
    raw_wa_id = message.get("from")
    if not raw_wa_id:
        return

    now = datetime.utcnow()
    if not _is_trigger(message):
        whatsapp_outbox.enqueue(
            db,
            dedupe_key=f"text:{event.id}",
            recipient_wa_id=str(raw_wa_id),
            kind=whatsapp_outbox.KIND_TEXT,
            now=now,
            params={"body": HINT_TEXT},
        )
        return
    identity = get_or_create_identity(db, str(raw_wa_id), now=now)

    user = db.get(User, identity.user_id) if identity.user_id else None
    if user is None:
        _start_registration(db, identity, event, now=now)
        return
    if user.role == UserRole.admin:
        _send_text(db, identity, event, ADMIN_TEXT, now=now)
        return
    _open_dashboard(db, identity, event, user, now=now)


def _flow_data_handler(db: Session, payload: dict[str, Any]) -> dict[str, Any] | None:
    return handle_flow_request(db, payload, now=datetime.utcnow())


def install_whatsapp_handlers() -> None:
    """Register the inbound router and the Flow data-endpoint handler. Called once at startup."""
    register_inbound_handler(handle_inbound_message)
    register_flow_handler(_flow_data_handler)
