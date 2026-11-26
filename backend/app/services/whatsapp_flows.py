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
from app.services.onboarding import create_invite, queue_portal_message
from app.services.whatsapp_contractor_flows import contractor_menu_choice, handle_contractor_screen
from app.services.whatsapp_owner_flows import handle_owner_screen, owner_menu_choice
from app.services.whatsapp_identity import find_active_flow_session

# One request sends at most this many links, so a single tap can't flood a chat.
MAX_LINKS_PER_REQUEST = 6

FLOW_REGISTRATION = "registration"
FLOW_OWNER_DASHBOARD = "owner_dashboard"
FLOW_CONTRACTOR_DASHBOARD = "contractor_dashboard"

# After a sign-up the customer is asked whether to continue. The button ids come back in the reply.
BUTTON_CONTINUE_YES = "continue_yes"
BUTTON_CONTINUE_NO = "continue_no"
ACCOUNT_CREATED = {
    "en": ("Your account is created. Do you want to continue?", "Yes", "No"),
    "ar": ("تم إنشاء حسابك. هل تريد المتابعة؟", "نعم", "لا"),
}

# Fields each registration screen may carry in its `data`. The Flow JSON
# declares the same names, and a test keeps the two in step.
REGISTRATION_SCREEN_FIELDS: dict[str, tuple[str, ...]] = {
    "ROLE": (),
    "OWNER_DETAILS": ("full_name",),
    "CONTRACTOR_DETAILS": ("contact_name", "company_name", "primary_trade"),
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


def _queue_account_created(db: Session, identity: WhatsAppIdentity, language: str, *, now: datetime) -> None:
    """Queue the "account created, continue?" message with Yes and No buttons. The dispatcher sends it."""
    body, yes, no = ACCOUNT_CREATED.get(language, ACCOUNT_CREATED["en"])
    whatsapp_outbox.enqueue(
        db,
        dedupe_key=f"account-created:{identity.id}",
        recipient_wa_id=identity.wa_id,
        kind=whatsapp_outbox.KIND_BUTTONS,
        now=now,
        params={
            "body": body,
            "buttons": [{"id": BUTTON_CONTINUE_YES, "title": yes}, {"id": BUTTON_CONTINUE_NO, "title": no}],
        },
    )
    db.commit()


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
    _queue_account_created(db, identity, _language_of(session), now=now)
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
    _queue_account_created(db, identity, _language_of(session), now=now)
    # The web portal finishes the rest of the sign-up: business details, then a subscription.
    invite_link = create_invite(db, identity.user_id, now=now)
    queue_portal_message(db, identity.wa_id, invite_link, now=now, dedupe_suffix=identity.user_id)
    db.commit()
    return {"screen": "SUCCESS", "data": {"message": "Your account is ready. Send any message to open your dashboard."}}


def _registration_failure(screen: str, error: RegistrationError) -> dict[str, Any]:
    if error.code == "invalid":
        # Stay on the same screen so the user can correct the field.
        return {"screen": screen, "data": {"error_message": error.message}}
    # The number is already taken, so the form can't succeed. End it on a terminal screen.
    return {"screen": "NOT_COMPLETED", "data": {"message": error.message}}


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
        # The menu shows this field, so it is always sent; an empty string shows nothing.
        "error_message": "",
    }


__all__ = [
    "FLOW_CONTRACTOR_DASHBOARD",
    "FLOW_OWNER_DASHBOARD",
    "FLOW_REGISTRATION",
    "REGISTRATION_SCREEN_FIELDS",
    "TRADE_OPTIONS",
    "handle_flow_request",
]
