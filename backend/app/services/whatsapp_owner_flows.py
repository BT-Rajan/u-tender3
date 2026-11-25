"""Owner Flow screens: create, review and publish, my tenders, details, amend, received offers.

Each request carries the tender id it acts on. Every request re-checks ownership
in the tender service, so an id from a forwarded or edited Flow can't reach
another owner's tender. The Flow never shows an action the tender's state doesn't
allow (see tender_service.allowed_actions), and the service enforces the same rules
again on submit.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import ProjectStatus, TenderType
from app.models.project import Project
from app.models.user import User
from app.services import tender_service
from app.services.registration import TRADE_OPTIONS
from app.services.tender_service import TenderError, TenderFields

# Shown as "[Draft] ..." and so on, so the status is visible in a list item.
STATUS_LABEL: dict[ProjectStatus, str] = {
    ProjectStatus.draft: "Draft",
    ProjectStatus.open: "Open for bids",
    ProjectStatus.closed: "Closed",
    ProjectStatus.under_evaluation: "Under evaluation",
    ProjectStatus.awarded: "Awarded",
    ProjectStatus.no_award: "No award",
    ProjectStatus.canceled: "Canceled",
    ProjectStatus.expired: "Expired",
}

ACTION_TITLE: dict[str, str] = {
    "details": "View details",
    "edit": "Edit",
    "publish": "Publish",
    "close": "Close for bids",
    "start_evaluation": "Start evaluation",
    "no_award": "Mark as no award",
    "cancel": "Cancel tender",
    "offers": "View offers",
}

# Action ids on the details screen that change a tender irreversibly need a second confirmation.
CONFIRM_REQUIRED = {"no_award", "cancel"}

# How many recent amendments the details screen lists. Enough to see what changed without a long message.
RECENT_AMENDMENTS = 3


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _tender_option(project: Project) -> dict[str, str]:
    """One row of the My tenders list. Flow option titles are short, so the title is cut to fit."""
    label = f"[{STATUS_LABEL[project.status]}] {project.title}"
    return {"id": project.id, "title": label[:30]}


def _tender_list(db: Session, owner: User, *, now: datetime) -> list[dict[str, str]]:
    return [_tender_option(project) for project in tender_service.list_owner_tenders(db, owner, now=now)]


def _actions_for(project: Project) -> list[dict[str, str]]:
    return [{"id": action, "title": ACTION_TITLE[action]} for action in tender_service.allowed_actions(project)]


def _details_text(db: Session, project: Project) -> str:
    tender_type = "Sealed (bidder names and amounts hidden until the tender closes)" if project.tender_type == TenderType.sealed else "Owner visible"
    lines = [
        f"Status: {STATUS_LABEL[project.status]}",
        f"Type: {tender_type}",
        f"Address: {_text(project.address, 120)}",
        f"Trade: {project.trade or 'not set'}",
        f"Bid deadline: {tender_service.format_local_deadline(project.bid_deadline)}",
        f"Offers received: {tender_service.offer_count(db, project)}",
        f"Revision: {project.revision}",
    ]
    drawings = [drawing for drawing in project.drawings if drawing.is_current]
    if drawings:
        names = ", ".join(_text(drawing.file_name, 40) for drawing in drawings[:5])
        lines.append(f"Drawings: {names}. Upload and download drawings on the web app.")
    else:
        lines.append("Drawings: none yet. Upload them on the web app.")
    from app.models.project_amendment import ProjectAmendment

    amendments = (
        db.query(ProjectAmendment)
        .filter(ProjectAmendment.project_id == project.id)
        .order_by(ProjectAmendment.amendment_number.desc())
        .limit(RECENT_AMENDMENTS)
        .all()
    )
    if amendments:
        lines.append("Recent amendments:")
        lines.extend(f"#{a.amendment_number}: {_text(a.summary, 120)}" for a in reversed(amendments))
    return "\n".join(lines)[:3500]


def _fields_for_draft(project: Project) -> dict[str, Any]:
    """The values an edit screen starts with. The owner sees what is saved, not a blank form."""
    return {
        "tender_id": project.id,
        "title": project.title,
        "address": project.address if project.address != "Not set" else "",
        "description": project.description or "",
        "trade": project.trade or "",
        "bid_deadline": tender_service.format_local_deadline(project.bid_deadline) if project.bid_deadline else "",
        "tender_type": project.tender_type.value,
        "error_message": "",
    }


def _form(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _fields_from_form(data: dict[str, Any]) -> TenderFields:
    """Read the create/amend form. Blank means not given, except where a blank field clears the value, as the web does."""
    deadline_text = _form(data, "bid_deadline")
    deadline = tender_service.parse_local_deadline(deadline_text) if deadline_text else None
    tender_type_value = _form(data, "tender_type") or TenderType.owner_visible.value
    if tender_type_value not in (TenderType.sealed.value, TenderType.owner_visible.value):
        raise TenderError("invalid", "Choose sealed or owner visible.")
    return TenderFields(
        title=_form(data, "title") or None,
        address=_form(data, "address") or None,
        description=_form(data, "description"),
        trade=_form(data, "trade"),
        bid_deadline=deadline,
        tender_type=TenderType(tender_type_value),
    )


def _error(screen: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"screen": screen, "data": {**(data or {}), "error_message": message}}


def _menu_error(db: Session, owner: User, message: str) -> dict[str, Any]:
    from app.services.whatsapp_flows import _menu_data

    return {"screen": "MENU", "data": {**_menu_data(db, owner, True), "error_message": message}}


def _message(message: str) -> dict[str, Any]:
    return {"screen": "DONE", "data": {"message": message}}


def open_create(db: Session, owner: User) -> dict[str, Any]:
    return {"screen": "CREATE_TENDER", "data": _blank_create_form()}


def _blank_create_form() -> dict[str, Any]:
    return {"tender_id": "", "title": "", "address": "", "description": "", "trade": "", "bid_deadline": "", "tender_type": TenderType.owner_visible.value, "error_message": ""}


def open_my_tenders(db: Session, owner: User, *, now: datetime, heading: str = "Your tenders") -> dict[str, Any]:
    tenders = _tender_list(db, owner, now=now)
    empty = "" if tenders else "You have no tenders yet. Create one from the menu."
    return {"screen": "MY_TENDERS", "data": {"heading": heading, "tenders": tenders, "empty_message": empty, "error_message": ""}}


def _with_owned(db: Session, owner: User, tender_id: str) -> Project:
    if not tender_id:
        raise TenderError("not_found", "Project not found.")
    return tender_service.owner_project(db, owner, tender_id)


def _details_screen(db: Session, owner: User, project: Project, message: str = "") -> dict[str, Any]:
    return {
        "screen": "TENDER_DETAILS",
        "data": {
            "tender_id": project.id,
            "title": _text(project.title, 80),
            "details": _details_text(db, project),
            "actions": _actions_for(project),
            "error_message": message,
        },
    }


def handle_owner_screen(db: Session, owner: User, screen: str, data: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
    """Route a data_exchange from one of the owner screens. Returns None for a screen this module does not own."""
    handlers = {
        "CREATE_TENDER": _submit_create,
        "REVIEW": _submit_review,
        "MY_TENDERS": _pick_tender,
        "TENDER_DETAILS": _submit_details,
        "AMEND": _submit_amend,
    }
    handler = handlers.get(screen)
    if handler is None:
        return None
    try:
        return handler(db, owner, data, now=now)
    except TenderError as error:
        return _tender_error_reply(db, owner, screen, data, error, now=now)


def _tender_error_reply(db: Session, owner: User, screen: str, data: dict[str, Any], error: TenderError, *, now: datetime) -> dict[str, Any]:
    if error.code == "not_verified":
        return _menu_error(db, owner, error.message)
    if error.code == "not_found":
        return open_my_tenders(db, owner, now=now, heading="That tender is no longer available")
    if screen == "CREATE_TENDER":
        return _error("CREATE_TENDER", error.message, {**_blank_create_form(), **{k: v for k, v in data.items() if k in _blank_create_form()}})
    if screen == "REVIEW":
        return _error("REVIEW", error.message, {"tender_id": _form(data, "tender_id"), "summary": "", "actions": _review_actions()})
    if screen == "TENDER_DETAILS":
        project = db.get(Project, _form(data, "tender_id"))
        if project is not None and project.owner_id == owner.id:
            return _details_screen(db, owner, project, error.message)
        return open_my_tenders(db, owner, now=now)
    if screen == "AMEND":
        project = db.get(Project, _form(data, "tender_id"))
        if project is not None and project.owner_id == owner.id:
            return {"screen": "AMEND", "data": {**_amend_form(project), "error_message": error.message}}
        return open_my_tenders(db, owner, now=now)
    return open_my_tenders(db, owner, now=now)


def _review_actions() -> list[dict[str, str]]:
    return [
        {"id": "publish", "title": "Publish now"},
        {"id": "save_draft", "title": "Keep as draft"},
        {"id": "edit", "title": "Edit"},
    ]


def _review_screen(db: Session, project: Project) -> dict[str, Any]:
    summary_lines = [
        f"Title: {_text(project.title, 120)}",
        f"Address: {_text(project.address, 120)}",
        f"Trade: {project.trade or 'not set'}",
        f"Type: {'Sealed' if project.tender_type == TenderType.sealed else 'Owner visible'}",
        f"Bid deadline: {tender_service.format_local_deadline(project.bid_deadline)}",
    ]
    if project.description:
        summary_lines.append(f"Description: {_text(project.description, 300)}")
    return {
        "screen": "REVIEW",
        "data": {
            "tender_id": project.id,
            "summary": "\n".join(summary_lines),
            "actions": _review_actions(),
            "error_message": "",
        },
    }


def _submit_create(db: Session, owner: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    fields = _fields_from_form(data)
    if _form(data, "trade") and _form(data, "trade") not in TRADE_OPTIONS:
        raise TenderError("invalid", "Choose a trade from the list.")
    tender_id = _form(data, "tender_id")
    if tender_id:
        project = _with_owned(db, owner, tender_id)
        project = tender_service.update_draft(db, owner, project, fields, verified_required=False)
    else:
        project = tender_service.create_draft(db, owner, fields, verified_required=False)
    # Saving the form always keeps a draft. A tender that isn't finished yet is still saved.
    return _review_screen(db, project)


def _submit_review(db: Session, owner: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    project = _with_owned(db, owner, _form(data, "tender_id"))
    action = _form(data, "action")
    if action == "publish":
        project = tender_service.publish(db, owner, project, now, verified_required=False)
        return _message("Your tender is published. Bidders can now see it and submit offers.")
    if action == "save_draft":
        return _message("Draft saved. You can find it under My tenders.")
    if action == "edit":
        return {"screen": "CREATE_TENDER", "data": _fields_for_draft(project)}
    raise TenderError("invalid", "Choose an option.")


def _pick_tender(db: Session, owner: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    project = _with_owned(db, owner, _form(data, "tender_id"))
    return _details_screen(db, owner, project)


def _submit_details(db: Session, owner: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    project = _with_owned(db, owner, _form(data, "tender_id"))
    action = _form(data, "action")
    allowed = tender_service.allowed_actions(project)
    if action not in allowed:
        raise TenderError("not_allowed", "That action isn't available for this tender right now.")

    if action in CONFIRM_REQUIRED and _form(data, "confirm") != "yes":
        raise TenderError("confirm", f"Choose Yes to confirm: {ACTION_TITLE[action].lower()}.")

    if action == "details":
        return _details_screen(db, owner, project)
    if action == "offers":
        return _offers_screen(db, owner, project)
    if action == "edit":
        if project.status == ProjectStatus.draft:
            return {"screen": "CREATE_TENDER", "data": _fields_for_draft(project)}
        return {"screen": "AMEND", "data": _amend_form(project)}
    if action == "publish":
        tender_service.publish(db, owner, project, now, verified_required=False)
        return _message("Your tender is published. Bidders can now see it and submit offers.")
    if action == "close":
        tender_service.close(db, owner, project)
        return _message("The tender is closed to new bids.")
    if action == "start_evaluation":
        tender_service.start_evaluation(db, owner, project)
        return _message("Evaluation has started.")
    if action == "no_award":
        tender_service.mark_no_award(db, owner, project)
        return _message("The tender is marked as no award. Bidders have been told.")
    if action == "cancel":
        tender_service.cancel(db, owner, project)
        return _message("The tender is canceled. Bidders have been told.")
    raise TenderError("invalid", "Choose an option.")


def _amend_form(project: Project) -> dict[str, Any]:
    return {
        "tender_id": project.id,
        "title": project.title,
        "description": project.description or "",
        "trade": project.trade or "",
        "bid_deadline": tender_service.format_local_deadline(project.bid_deadline) if project.bid_deadline else "",
        "reason": "",
        "error_message": "",
    }


def _submit_amend(db: Session, owner: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    project = _with_owned(db, owner, _form(data, "tender_id"))
    deadline_text = _form(data, "bid_deadline")
    # The form shows the deadline to the minute. Resubmitting that same text must not count as a change.
    unchanged_deadline = deadline_text == tender_service.format_local_deadline(project.bid_deadline)
    fields = TenderFields(
        title=_form(data, "title") or None,
        description=_form(data, "description"),
        trade=_form(data, "trade"),
        bid_deadline=None if (not deadline_text or unchanged_deadline) else tender_service.parse_local_deadline(deadline_text),
    )
    if _form(data, "trade") and _form(data, "trade") not in TRADE_OPTIONS:
        raise TenderError("invalid", "Choose a trade from the list.")
    tender_service.amend(db, owner, project, fields, reason=_form(data, "reason") or None, now=now, verified_required=False)
    return _message("Changes saved. Bidders with offers have been told about the amendment.")


def _offers_screen(db: Session, owner: User, project: Project) -> dict[str, Any]:
    view = tender_service.received_offers(db, owner, project)
    rows = view["rows"]
    if not rows:
        body = "No offers have been received yet."
    elif view["sealed"]:
        lines = [
            "This tender is sealed. Bidder names and amounts stay hidden until it closes.",
            f"{len(rows)} offer(s) received.",
        ]
        lines.extend(f"{row['label']}: received {row['submitted_at']:%d %b %Y %H:%M} UTC, {row['status']}" for row in rows)
        body = "\n".join(lines)
    else:
        lines = [f"{len(rows)} offer(s), lowest amount first."]
        for row in rows:
            timeline = f", {row['timeline']}" if row["timeline"] else ""
            lines.append(f"{row['company']}: {row['amount']:,.2f}{timeline}, {row['status']}")
        body = "\n".join(lines)
    return {"screen": "OFFERS", "data": {"tender_title": _text(project.title, 80), "offers": body[:3500]}}


def owner_menu_choice(db: Session, owner: User, choice: str, *, now: datetime) -> dict[str, Any] | None:
    """Menu items that open owner screens. Returns None for a choice this module doesn't own."""
    if choice == "create_tender":
        return open_create(db, owner)
    if choice == "my_tenders":
        return open_my_tenders(db, owner, now=now)
    if choice == "received_offers":
        return open_my_tenders(db, owner, now=now, heading="Pick a tender to see its offers")
    return None
