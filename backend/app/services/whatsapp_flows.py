from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.contractor import ContractorProfile
from app.models.enums import DocumentStatus, UserRole
from app.models.owner import OwnerProfile
from app.models.user import User
from app.models.whatsapp import WhatsAppFlowSession, WhatsAppIdentity
from app.services import whatsapp_outbox
from app.services.document_service import checklist_for
from app.services.registration import (
    TRADE_OPTIONS,
    RegistrationError,
    register_contractor,
    register_owner,
)
from app.services.upload_links import issue_upload_link
from app.services.whatsapp_contractor_flows import contractor_menu_choice, handle_contractor_screen
from app.services.whatsapp_owner_flows import handle_owner_screen, owner_menu_choice
from app.services.whatsapp_identity import find_active_flow_session

# One request sends at most this many links, so a single tap can't flood a chat.
MAX_LINKS_PER_REQUEST = 6

FLOW_REGISTRATION = "registration"
FLOW_OWNER_DASHBOARD = "owner_dashboard"
FLOW_CONTRACTOR_DASHBOARD = "contractor_dashboard"

# Fields each registration screen may carry in its `data`. The Flow JSON
# declares the same names, and a test keeps the two in step.
REGISTRATION_SCREEN_FIELDS: dict[str, tuple[str, ...]] = {
    "SPLASH": (),
    "REGISTER": ("full_name", "address"),
}

# Contractors give one name on the form. The company name is set to it, and
# the trade is "Other" until the contractor completes their profile.
CONTRACTOR_DEFAULT_TRADE = "Other"

# What each role can do, shown on the summary screen after registration.
ROLE_CAPABILITIES: dict[str, str] = {
    "owner": (
        "- Post a tender for your project with drawings\n"
        "- Receive sealed or open offers from contractors\n"
        "- Review offers and award the work\n"
        "- Keep your documents up to date"
    ),
    "contractor": (
        "- Browse open projects and send offers\n"
        "- Track your offers and awards\n"
        "- Keep your documents up to date"
    ),
}

OWNER_MENU_CHOICES = ("create_tender", "my_tenders", "received_offers", "my_documents")
CONTRACTOR_MENU_CHOICES = ("browse_projects", "search_projects", "my_offers", "my_documents", "my_awards")

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
        return _dashboard_reply(db, session, payload, now=now)
    return None


def _saved_fields(session: WhatsAppFlowSession, screen: str) -> dict[str, Any]:
    state = session.state_json or {}
    return {key: state[key] for key in REGISTRATION_SCREEN_FIELDS.get(screen, ()) if key in state}


def _registration_reply(
    db: Session, session: WhatsAppFlowSession, payload: dict[str, Any], *, now: datetime
) -> dict[str, Any] | None:
    action = payload.get("action")
    if action == "INIT":
        screen = session.screen or "SPLASH"
        return {"screen": screen, "data": _saved_fields(session, screen)}
    if action == "BACK":
        return {"screen": "SPLASH", "data": {}}
    if action != "data_exchange":
        return None

    screen = payload.get("screen")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    identity = db.get(WhatsAppIdentity, session.identity_id)
    if identity is None:
        return _expired_reply()

    if screen == "REGISTER":
        return _complete_registration(db, session, identity, data, now=now)
    return None


def _complete_registration(
    db: Session, session: WhatsAppFlowSession, identity: WhatsAppIdentity, data: dict[str, Any], *, now: datetime
) -> dict[str, Any]:
    role = data.get("role")
    full_name = data.get("full_name")
    address = data.get("address")
    if role not in ("owner", "contractor"):
        return {"screen": "REGISTER", "data": {"error_message": "Choose whether you are an owner or a contractor."}}

    session.state_json = {**(session.state_json or {}), "full_name": full_name, "address": address, "role": role}
    session.screen = "REGISTER"
    db.commit()

    try:
        if role == "owner":
            user = register_owner(
                db, identity, session, full_name=full_name, address=address, language="en", now=now
            )
        else:
            user = register_contractor(
                db,
                identity,
                session,
                contact_name=full_name,
                company_name=full_name,
                primary_trade=CONTRACTOR_DEFAULT_TRADE,
                address=address,
                language="en",
                now=now,
            )
    except RegistrationError as error:
        return _registration_failure(error)
    return {
        "screen": "RESULT_OK",
        "data": {"reference": user.id, "capabilities": ROLE_CAPABILITIES[role]},
    }


def _registration_failure(error: RegistrationError) -> dict[str, Any]:
    if error.code == "invalid":
        # Stay on the form so the user can correct the field.
        return {"screen": "REGISTER", "data": {"error_message": error.message}}
    # The number is already taken, so the form can't succeed. Show why on the result screen.
    return {"screen": "RESULT_ERROR", "data": {"error_message": error.message}}


def _dashboard_reply(db: Session, session: WhatsAppFlowSession, payload: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
    identity = db.get(WhatsAppIdentity, session.identity_id)
    user = db.get(User, identity.user_id) if identity and identity.user_id else None
    if user is None or identity is None:
        return _expired_reply()

    is_owner = session.flow_name == FLOW_OWNER_DASHBOARD
    expected_role = UserRole.owner if is_owner else UserRole.contractor
    if user.role != expected_role:
        return _expired_reply()

    action = payload.get("action")
    screen = payload.get("screen")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    if action in ("INIT", "BACK") and screen != "DOCUMENTS":
        return {"screen": "MENU", "data": _menu_data(db, user, is_owner)}
    if action != "data_exchange":
        return None

    if screen == "DOCUMENTS":
        return _documents_action(db, identity, user, data, now=now)
    if is_owner and screen != "MENU":
        owner_reply = handle_owner_screen(db, user, screen or "", data, now=now)
        if owner_reply is not None:
            return owner_reply
    if not is_owner and screen != "MENU":
        contractor_reply = handle_contractor_screen(db, identity, user, screen or "", data, now=now)
        if contractor_reply is not None:
            return contractor_reply
    if screen != "MENU":
        return None

    choices = OWNER_MENU_CHOICES if is_owner else CONTRACTOR_MENU_CHOICES
    choice = data.get("choice")
    if choice not in choices:
        return {"screen": "MENU", "data": {**_menu_data(db, user, is_owner), "error_message": "Choose one option."}}
    if choice == "my_documents":
        return {"screen": "DOCUMENTS", "data": {"checklist": _checklist_text(db, user)}}
    if is_owner:
        owner_reply = owner_menu_choice(db, user, str(choice), now=now)
        if owner_reply is not None:
            return owner_reply
    else:
        contractor_reply = contractor_menu_choice(db, identity, user, str(choice), now=now)
        if contractor_reply is not None:
            return contractor_reply
    return {"screen": "COMING_SOON", "data": {"message": "This section is coming soon."}}


# Plain markers rather than emoji, so the text reads the same on every phone.
_CHECKLIST_LABEL = {
    DocumentStatus.not_submitted: "Upload needed",
    DocumentStatus.pending: "Under review",
    DocumentStatus.approved: "Approved",
    DocumentStatus.rejected: "Rejected - please upload again",
}


def _checklist_text(db: Session, user: User) -> str:
    items = checklist_for(db, user)
    if not items:
        return "No documents are required for your account."
    lines = []
    for item in items:
        line = f"{item.name}: {_CHECKLIST_LABEL[item.status]}"
        if item.status == DocumentStatus.rejected and item.admin_note:
            line += f" ({item.admin_note[:160]})"
        lines.append(line)
    return "\n".join(lines)[:3500]


def _documents_action(
    db: Session, identity: WhatsAppIdentity, user: User, data: dict[str, Any], *, now: datetime
) -> dict[str, Any]:
    """Queue an upload link and a separate one-time code for every requirement that still needs a file."""
    if data.get("intent") != "send_links":
        return {"screen": "DOCUMENTS", "data": {"checklist": _checklist_text(db, user)}}

    needing = [item for item in checklist_for(db, user) if item.needs_upload][:MAX_LINKS_PER_REQUEST]
    if not needing:
        return {"screen": "LINKS_SENT", "data": {"message": "Nothing needs uploading right now. Your documents are approved or under review."}}

    settings = get_settings()
    for item in needing:
        issued = issue_upload_link(db, user_id=user.id, requirement_id=item.requirement_id, now=now)
        whatsapp_outbox.enqueue(
            db,
            dedupe_key=f"upload-link:{issued.link_id}",
            recipient_wa_id=identity.wa_id,
            kind=whatsapp_outbox.KIND_CTA_URL,
            now=now,
            params={
                "body": f"Upload your {item.name}. Open the link, then enter the code from our next message. The link works once and expires in {settings.upload_link_ttl_minutes} minutes.",
                "display_text": "Upload",
                "url": f"{settings.api_url.rstrip('/')}/upload/{issued.token}",
            },
        )
        whatsapp_outbox.enqueue(
            db,
            dedupe_key=f"upload-code:{issued.link_id}",
            recipient_wa_id=identity.wa_id,
            kind=whatsapp_outbox.KIND_TEXT,
            now=now,
            params={
                "body": f"Your code for {item.name} is {issued.code}. It works once and expires in {settings.upload_link_ttl_minutes} minutes. Do not share it.",
                "sensitive": True,
            },
        )
    db.commit()
    return {
        "screen": "LINKS_SENT",
        "data": {"message": f"We sent {len(needing)} upload link(s) to this chat. Each works once."},
    }


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
