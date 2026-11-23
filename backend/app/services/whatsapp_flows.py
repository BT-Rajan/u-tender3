from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.contractor import ContractorProfile
from app.models.owner import OwnerProfile
from app.models.enums import UserRole
from app.models.user import User
from app.models.whatsapp import WhatsAppFlowSession, WhatsAppIdentity
from app.services.registration import (
    TRADE_OPTIONS,
    RegistrationError,
    register_contractor,
    register_owner,
)
from app.services.whatsapp_identity import find_active_flow_session

FLOW_REGISTRATION = "registration"
FLOW_OWNER_DASHBOARD = "owner_dashboard"
FLOW_CONTRACTOR_DASHBOARD = "contractor_dashboard"

# Fields each registration screen may carry in its `data`. The Flow JSON
# declares the same names, and a test keeps the two in step.
REGISTRATION_SCREEN_FIELDS: dict[str, tuple[str, ...]] = {
    "ROLE": (),
    "OWNER_DETAILS": ("full_name",),
    "CONTRACTOR_DETAILS": ("contact_name", "company_name", "primary_trade"),
}

OWNER_MENU_CHOICES = ("create_tender", "my_tenders", "received_offers", "my_documents")
CONTRACTOR_MENU_CHOICES = ("browse_projects", "my_offers", "my_documents", "my_awards")

# Phase 2 ships the menus as navigation shells. The journeys behind each choice
# arrive in Phases 4 and 5, so each choice currently lands on a "coming soon"
# screen.
STATUS_TEXT: dict[str, str] = {
    "documents_incomplete": "Documents are incomplete. Upload them to submit for review.",
    "submitted_for_review": "Your documents are with the review team.",
    "changes_requested": "The review team asked for changes to your documents.",
    "verified_active": "Your account is verified and active.",
    "suspended": "Your account is suspended. Contact support.",
    "payment_required": "Activate a subscription to bid on projects.",
    "payment_restricted": "Your subscription needs attention.",
}


def _expired_reply() -> dict[str, Any]:
    return {"screen": "EXPIRED", "data": {}}


def handle_flow_request(db: Session, payload: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
    """Answer one decrypted Flow data-endpoint request. Returns None if no session flow covers it."""
    token = payload.get("flow_token")
    if not isinstance(token, str) or not token:
        return None

    session = find_active_flow_session(db, token, now=now)
    if session is None:
        return _expired_reply()

    if session.flow_name == FLOW_REGISTRATION:
        return _registration_reply(db, session, payload, now=now)
    if session.flow_name in (FLOW_OWNER_DASHBOARD, FLOW_CONTRACTOR_DASHBOARD):
        return _dashboard_reply(db, session, payload)
    return None


def _saved_fields(session: WhatsAppFlowSession, screen: str) -> dict[str, Any]:
    state = session.state_json or {}
    return {key: state[key] for key in REGISTRATION_SCREEN_FIELDS.get(screen, ()) if key in state}


def _registration_reply(
    db: Session, session: WhatsAppFlowSession, payload: dict[str, Any], *, now: datetime
) -> dict[str, Any] | None:
    action = payload.get("action")
    if action == "INIT":
        screen = session.screen or "ROLE"
        return {"screen": screen, "data": _saved_fields(session, screen)}
    if action == "BACK":
        return {"screen": "ROLE", "data": {}}
    if action != "data_exchange":
        return None

    screen = payload.get("screen")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    identity = db.get(WhatsAppIdentity, session.identity_id)
    if identity is None:
        return _expired_reply()

    if screen == "ROLE":
        return _choose_role(db, session, data, now=now)
    if screen == "OWNER_DETAILS":
        return _complete_owner(db, session, identity, data, now=now)
    if screen == "CONTRACTOR_DETAILS":
        return _complete_contractor(db, session, identity, data, now=now)
    return None


def _choose_role(db: Session, session: WhatsAppFlowSession, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    role = data.get("role")
    language = data.get("language")
    if role not in ("owner", "contractor") or language not in ("en", "ar"):
        return {"screen": "ROLE", "data": {"error_message": "Choose a role and a language."}}

    session.state_json = {**(session.state_json or {}), "role": role, "language": language}
    next_screen = "OWNER_DETAILS" if role == "owner" else "CONTRACTOR_DETAILS"
    session.screen = next_screen
    db.commit()
    return {"screen": next_screen, "data": {}}


def _language_of(session: WhatsAppFlowSession) -> str:
    return str((session.state_json or {}).get("language", "en"))


def _complete_owner(
    db: Session, session: WhatsAppFlowSession, identity: WhatsAppIdentity, data: dict[str, Any], *, now: datetime
) -> dict[str, Any]:
    try:
        register_owner(
            db,
            identity,
            session,
            full_name=data.get("full_name"),
            language=_language_of(session),
            now=now,
        )
    except RegistrationError as error:
        return _registration_failure("OWNER_DETAILS", error)
    return {"screen": "SUCCESS", "data": {"message": "Your account is ready. Send any message to open your dashboard."}}


def _complete_contractor(
    db: Session, session: WhatsAppFlowSession, identity: WhatsAppIdentity, data: dict[str, Any], *, now: datetime
) -> dict[str, Any]:
    try:
        register_contractor(
            db,
            identity,
            session,
            contact_name=data.get("contact_name"),
            company_name=data.get("company_name"),
            primary_trade=data.get("primary_trade"),
            language=_language_of(session),
            now=now,
        )
    except RegistrationError as error:
        return _registration_failure("CONTRACTOR_DETAILS", error)
    return {"screen": "SUCCESS", "data": {"message": "Your account is ready. Send any message to open your dashboard."}}


def _registration_failure(screen: str, error: RegistrationError) -> dict[str, Any]:
    if error.code == "invalid":
        # Stay on the same screen so the user can correct the field.
        return {"screen": screen, "data": {"error_message": error.message}}
    # The number is already taken, so the form can't succeed. End it on a terminal screen.
    return {"screen": "NOT_COMPLETED", "data": {"message": error.message}}


def _dashboard_reply(db: Session, session: WhatsAppFlowSession, payload: dict[str, Any]) -> dict[str, Any] | None:
    identity = db.get(WhatsAppIdentity, session.identity_id)
    user = db.get(User, identity.user_id) if identity and identity.user_id else None
    if user is None:
        return _expired_reply()

    is_owner = session.flow_name == FLOW_OWNER_DASHBOARD
    expected_role = UserRole.owner if is_owner else UserRole.contractor
    if user.role != expected_role:
        return _expired_reply()

    action = payload.get("action")
    if action in ("INIT", "BACK"):
        return {"screen": "MENU", "data": _menu_data(db, user, is_owner)}
    if action != "data_exchange" or payload.get("screen") != "MENU":
        return None

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    choices = OWNER_MENU_CHOICES if is_owner else CONTRACTOR_MENU_CHOICES
    if data.get("choice") not in choices:
        return {"screen": "MENU", "data": {**_menu_data(db, user, is_owner), "error_message": "Choose one option."}}
    return {"screen": "COMING_SOON", "data": {"message": "This section is coming soon."}}


def _menu_data(db: Session, user: User, is_owner: bool) -> dict[str, str]:
    if is_owner:
        profile = db.get(OwnerProfile, user.id)
    else:
        profile = db.get(ContractorProfile, user.id)
    marketplace_status = profile.marketplace_status if profile else "documents_incomplete"
    first_name = (user.full_name or "").split(" ")[0] or "there"
    return {
        "greeting": f"Hello {first_name}",
        "status": STATUS_TEXT.get(marketplace_status, ""),
    }


__all__ = [
    "FLOW_CONTRACTOR_DASHBOARD",
    "FLOW_OWNER_DASHBOARD",
    "FLOW_REGISTRATION",
    "REGISTRATION_SCREEN_FIELDS",
    "TRADE_OPTIONS",
    "handle_flow_request",
]
