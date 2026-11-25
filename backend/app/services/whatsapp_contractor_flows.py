"""Contractor Flow screens: browse, search, project details, submit, review, my offers, revisions, withdrawal, awards, drawings.

Each request names the tender it acts on, and every one is checked again in the contractor service
against what this contractor may see. A tender they can't see is reported as missing, so ids can't be
probed. Offers are always the contractor's own.
"""

import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.models.contractor import ContractorProfile
from app.models.enums import OfferStatus, ProjectStatus, TenderType
from app.models.offer import Offer
from app.models.project import Project
from app.models.user import User
from app.models.whatsapp import WhatsAppIdentity
from app.services import contractor_service, offer_service, whatsapp_outbox
from app.services.contractor_service import require_approved, require_marketplace
from app.services.tender_service import TenderError

STATUS_LABEL: dict[ProjectStatus, str] = {
    ProjectStatus.open: "Open",
    ProjectStatus.closed: "Closed",
    ProjectStatus.under_evaluation: "Under evaluation",
    ProjectStatus.awarded: "Awarded",
    ProjectStatus.no_award: "No award",
    ProjectStatus.canceled: "Canceled",
    ProjectStatus.expired: "Expired",
}

OFFER_LABEL: dict[OfferStatus, str] = {
    OfferStatus.submitted: "Submitted",
    OfferStatus.approved: "Awarded to you",
    OfferStatus.rejected: "Not selected",
    OfferStatus.withdrawn: "Withdrawn",
}

MAX_AMOUNT = Decimal("1000000000000")  # matches the Numeric(12, 2) column


# WhatsApp shows at most 20 rows in a list. Anything beyond would make the screen fail.
MAX_OPTIONS = 20


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _option(title: str, project_id: str) -> dict[str, str]:
    return {"id": project_id, "title": title[:30]}


def _menu_error(db: Session, user: User, message: str) -> dict[str, Any]:
    from app.services.whatsapp_flows import _menu_data

    return {"screen": "MENU", "data": {**_menu_data(db, user, False), "error_message": message}}


def _money(value: Decimal | float | None) -> str:
    return f"{float(value):,.2f}" if value is not None else "not set"


def _project_line(project: Project, offer_count: int) -> str:
    deadline = project.bid_deadline.strftime("%d %b %H:%M UTC") if project.bid_deadline else "no deadline"
    return f"{project.title} | {STATUS_LABEL.get(project.status, project.status.value)} | closes {deadline} | {offer_count} offer(s)"


def _not_suspended(db: Session, user: User) -> None:
    """Browsing and search are open to every registered contractor. Only a suspended account is kept out."""
    profile = db.get(ContractorProfile, user.id)
    if profile is not None and profile.is_suspended:
        raise TenderError("not_approved", "Your account is suspended. Contact support.")


def open_browse(db: Session, user: User, *, now: datetime) -> dict[str, Any]:
    try:
        _not_suspended(db, user)
    except TenderError as error:
        return _menu_error(db, user, error.message)
    return _feed_screen(db, user, heading="Open projects", now=now)


def open_search(db: Session, user: User) -> dict[str, Any]:
    try:
        _not_suspended(db, user)
    except TenderError as error:
        return _menu_error(db, user, error.message)
    return {"screen": "SEARCH", "data": {"search": "", "trade": "", "sort": "deadline", "error_message": ""}}


def _feed_screen(db: Session, user: User, *, heading: str, now: datetime, search: str | None = None, trade: str | None = None, sort: str = "deadline") -> dict[str, Any]:
    rows = contractor_service.feed(db, user, search=search, trade=trade, sort=sort, now=now, verified_required=False)
    options = []
    for row in rows:
        project = row["project"]
        status_tag = f"[{row['my_offer_status'].value}] " if row["my_offer_status"] else ""
        options.append(_option(f"{status_tag}{project.title}", project.id))
    empty = "" if options else "No open projects match. Try a different search."
    return {"screen": "PROJECT_LIST", "data": {"heading": heading, "projects": options[:MAX_OPTIONS], "empty_message": empty, "error_message": ""}}


def _submit_search(db: Session, user: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    search = _text(data.get("search"), 100)
    trade = "" if data.get("trade") in (None, "", "Any") else _text(data.get("trade"), 60)
    sort = "newest" if data.get("sort") == "newest" else "deadline"
    heading = f"Results for “{search}”" if search else "Open projects"
    return _feed_screen(db, user, heading=heading, now=now, search=search or None, trade=trade or None, sort=sort)


def _project_details(db: Session, user: User, project_id: str, *, now: datetime, message: str = "") -> dict[str, Any]:
    view = contractor_service.project_view(db, user, project_id, now=now)
    project: Project = view["project"]
    mine: Offer | None = view["my_offer"]
    lines = [
        f"Status: {STATUS_LABEL.get(project.status, project.status.value)}",
        f"Address: {_text(project.address, 120)}",
        f"Trade: {project.trade or 'not set'}",
        f"Bid deadline: {project.bid_deadline:%d %b %Y %H:%M} UTC" if project.bid_deadline else "Bid deadline: not set",
        f"Offers received: {view['offer_count']}",
        f"Type: {'Sealed' if project.tender_type == TenderType.sealed else 'Owner visible'}",
    ]
    if project.description:
        lines.append(f"About: {_text(project.description, 400)}")
    if mine:
        lines.append(f"Your offer: {_money(mine.amount)}, {OFFER_LABEL[mine.status]}")
    if view["drawing_count"]:
        lines.append(f"Drawings: {view['drawing_count']} current. Tap Get drawings for secure links.")
    elif not view["can_get_drawings"]:
        lines.append("Drawings are available once your subscription is active.")

    actions: list[dict[str, str]] = []
    if view["can_bid"] and mine is None:
        actions.append({"id": "submit", "title": "Submit offer"})
    if view["can_bid"] and mine is not None and mine.status == OfferStatus.submitted:
        actions.append({"id": "revise", "title": "Revise my offer"})
    if view["can_bid"] and mine is not None and mine.status == OfferStatus.withdrawn:
        actions.append({"id": "submit", "title": "Submit again"})
    if view["can_get_drawings"]:
        actions.append({"id": "drawings", "title": "Get drawings"})
    if mine is not None:
        actions.append({"id": "history", "title": "My revision history"})
    actions.append({"id": "details", "title": "Refresh"})

    return {
        "screen": "PROJECT_DETAILS",
        "data": {
            "project_id": project.id,
            "title": _text(project.title, 80),
            "details": "\n".join(lines)[:3500],
            "actions": actions,
            "error_message": message,
        },
    }


def _offer_form(project_id: str, title: str, offer: Offer | None) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "title": _text(title, 80),
        "amount": f"{offer.amount:.2f}" if offer is not None else "",
        "timeline": (offer.timeline_estimate or "") if offer is not None else "",
        "message": (offer.message or "") if offer is not None else "",
        "error_message": "",
    }


def _parse_amount(text: str) -> Decimal:
    cleaned = text.replace(",", "").strip()
    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise TenderError("invalid", "Enter the amount as a number, for example 12500.") from exc
    if amount <= 0 or amount > MAX_AMOUNT:
        raise TenderError("invalid", "Enter a bid amount greater than zero.")
    return amount.quantize(Decimal("0.01"))


def _review_offer(project_id: str, title: str, amount: Decimal, timeline: str, message: str) -> dict[str, Any]:
    summary = "\n".join(
        [
            f"Project: {title}",
            f"Your amount: {amount:,.2f}",
            f"Timeline: {timeline or 'not stated'}",
            f"Message: {message or 'none'}",
            "Once submitted, the owner sees it. You can revise it until the deadline.",
        ]
    )
    return {
        "screen": "REVIEW_OFFER",
        "data": {
            "project_id": project_id,
            "amount": f"{amount:.2f}",
            "timeline": timeline,
            "message": message,
            "summary": summary,
            "error_message": "",
        },
    }


def _submit_offer_form(db: Session, user: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    project_id = _text(data.get("project_id"), 64)
    view = contractor_service.project_view(db, user, project_id, now=now)
    project: Project = view["project"]
    amount = _parse_amount(_text(data.get("amount"), 40))
    timeline = _text(data.get("timeline"), 200)
    message = _text(data.get("message"), 1000)
    return _review_offer(project.id, project.title, amount, timeline, message)


def _submit_review(db: Session, user: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    project_id = _text(data.get("project_id"), 64)
    decision = _text(data.get("decision"), 20)
    if decision == "edit":
        view = contractor_service.project_view(db, user, project_id, now=now)
        mine = view["my_offer"]
        form = _offer_form(project_id, view["project"].title, mine)
        form.update({"amount": _text(data.get("amount"), 40), "timeline": _text(data.get("timeline"), 200), "message": _text(data.get("message"), 1000)})
        return {"screen": "SUBMIT_OFFER", "data": form}
    if decision != "submit":
        raise TenderError("invalid", "Choose submit or edit.")

    require_marketplace(db, user)
    amount = _parse_amount(_text(data.get("amount"), 40))
    timeline = _text(data.get("timeline"), 200)
    message = _text(data.get("message"), 1000)
    view = contractor_service.project_view(db, user, project_id, now=now)
    if not view["can_bid"]:
        raise TenderError("closed", "Bidding on this project is closed.")
    was_revision = view["my_offer"] is not None
    offer_service.submit_offer(
        db,
        user,
        project_id,
        amount=amount,
        timeline_estimate=timeline or None,
        message=message or None,
        now=now,
    )
    if was_revision:
        return _done("Your offer is revised. Your earlier version is kept in your revision history.")
    return _done("Your offer is submitted. You can revise it until the deadline.")


def _done(message: str) -> dict[str, Any]:
    return {"screen": "DONE", "data": {"message": message}}


def _my_offers_screen(db: Session, user: User) -> dict[str, Any]:
    rows = contractor_service.my_offers(db, user)
    options = [_option(f"[{OFFER_LABEL[offer.status]}] {project.title}", project.id) for offer, project in rows]
    empty = "" if options else "You have not placed any offers yet. Browse projects to find one."
    return {"screen": "MY_OFFERS", "data": {"heading": "My offers", "offers": options[:MAX_OPTIONS], "empty_message": empty, "error_message": ""}}


def _offer_details(db: Session, user: User, project_id: str, *, now: datetime, message: str = "") -> dict[str, Any]:
    offer, project, revisions = contractor_service.my_offer_detail(db, user, project_id)
    lines = [
        f"Project status: {STATUS_LABEL.get(project.status, project.status.value)}",
        f"Your amount: {_money(offer.amount)}",
        f"Timeline: {offer.timeline_estimate or 'not stated'}",
        f"Message: {_text(offer.message, 300) or 'none'}",
        f"Status: {OFFER_LABEL[offer.status]}",
        f"Revisions so far: {revisions}",
    ]
    actions: list[dict[str, str]] = []
    marketplace_ok = True
    try:
        require_marketplace(db, user)
    except TenderError:
        marketplace_ok = False
    open_for_bids = project.status == ProjectStatus.open and project.bid_deadline is not None and project.bid_deadline > now and not project.is_suspended
    if marketplace_ok and open_for_bids and offer.status == OfferStatus.submitted:
        actions.append({"id": "revise", "title": "Revise my offer"})
    if offer.status == OfferStatus.submitted:
        try:
            require_approved(db, user)
            actions.append({"id": "withdraw", "title": "Withdraw my offer"})
        except TenderError:
            pass
    if revisions:
        actions.append({"id": "history", "title": "My revision history"})
    actions.append({"id": "details", "title": "Refresh"})
    return {
        "screen": "OFFER_DETAILS",
        "data": {
            "project_id": project.id,
            "title": _text(project.title, 80),
            "details": "\n".join(lines),
            "actions": actions,
            "confirm": "",
            "error_message": message,
        },
    }


def _offer_history(db: Session, user: User, project_id: str) -> dict[str, Any]:
    revisions = contractor_service.my_offer_history(db, user, project_id)
    lines = []
    for revision in revisions:
        lines.append(
            f"Revision {revision.revision_number}: {_money(revision.amount)}, "
            f"{revision.timeline_estimate or 'no timeline'}, {OFFER_LABEL.get(revision.status, revision.status.value)}"
        )
    body = "\n".join(lines) if lines else "No earlier revisions yet."
    return {"screen": "OFFER_HISTORY", "data": {"body": body[:3500]}}


def _awards_screen(db: Session, user: User) -> dict[str, Any]:
    rows = contractor_service.my_awards(db, user)
    if not rows:
        body = "You have not been awarded a tender yet."
    else:
        lines = [f"{project.title}: {_money(record.amount)}, awarded {record.created_at:%d %b %Y} UTC" for record, project in rows]
        body = "\n".join(lines)
    return {"screen": "AWARDS", "data": {"body": body[:3500]}}


def _withdraw(db: Session, user: User, project_id: str, *, now: datetime) -> dict[str, Any]:
    require_approved(db, user)
    offer_service.withdraw_offer(db, user, project_id, now=now)
    return _done("Your offer is withdrawn. It stays in your revision history.")


def _send_drawing_links(db: Session, identity: WhatsAppIdentity, user: User, project_id: str, *, now: datetime) -> dict[str, Any]:
    links = contractor_service.drawing_links(db, user, project_id, now=now)
    for file_name, url in links:
        whatsapp_outbox.enqueue(
            db,
            dedupe_key=f"drawing:{uuid.uuid4().hex}",
            recipient_wa_id=identity.wa_id,
            kind=whatsapp_outbox.KIND_CTA_URL,
            now=now,
            params={
                "body": f"{_text(file_name, 80)}. This secure link expires automatically. Open it on your phone.",
                "display_text": "Open drawing",
                "url": url,
            },
        )
    db.commit()
    return _done(f"We sent {len(links)} drawing link(s) to this chat.")


def _details_action(db: Session, identity: WhatsAppIdentity, user: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    project_id = _text(data.get("project_id"), 64)
    action = _text(data.get("next_step") or data.get("action"), 20)
    if action == "details":
        return _project_details(db, user, project_id, now=now)
    if action == "submit":
        require_marketplace(db, user)
        view = contractor_service.project_view(db, user, project_id, now=now)
        if not view["can_bid"]:
            raise TenderError("closed", "Bidding on this project is closed.")
        return {"screen": "SUBMIT_OFFER", "data": _offer_form(project_id, view["project"].title, view["my_offer"])}
    if action == "revise":
        require_marketplace(db, user)
        view = contractor_service.project_view(db, user, project_id, now=now)
        if not view["can_bid"] or view["my_offer"] is None:
            raise TenderError("closed", "This offer can't be revised now.")
        return {"screen": "SUBMIT_OFFER", "data": _offer_form(project_id, view["project"].title, view["my_offer"])}
    if action == "history":
        return _offer_history(db, user, project_id)
    if action == "drawings":
        return _send_drawing_links(db, identity, user, project_id, now=now)
    raise TenderError("invalid", "Choose an option.")


def _offer_details_action(db: Session, user: User, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    project_id = _text(data.get("project_id"), 64)
    action = _text(data.get("next_step") or data.get("action"), 20)
    if action == "details":
        return _offer_details(db, user, project_id, now=now)
    if action == "history":
        return _offer_history(db, user, project_id)
    if action == "revise":
        require_marketplace(db, user)
        view = contractor_service.project_view(db, user, project_id, now=now)
        if not view["can_bid"]:
            raise TenderError("closed", "This offer can't be revised now.")
        return {"screen": "SUBMIT_OFFER", "data": _offer_form(project_id, view["project"].title, view["my_offer"])}
    if action == "withdraw":
        if _text(data.get("confirm"), 5) != "yes":
            raise TenderError("confirm", "Choose Yes to confirm you want to withdraw.")
        return _withdraw(db, user, project_id, now=now)
    raise TenderError("invalid", "Choose an option.")


def handle_contractor_screen(
    db: Session, identity: WhatsAppIdentity, user: User, screen: str, data: dict[str, Any], *, now: datetime
) -> dict[str, Any] | None:
    """Answer a data_exchange from a contractor screen. Returns None for a screen this module doesn't own."""
    handlers = {
        "SEARCH": lambda: _submit_search(db, user, data, now=now),
        "PROJECT_LIST": lambda: _project_details(db, user, _text(data.get("project_id"), 64), now=now),
        "PROJECT_DETAILS": lambda: _details_action(db, identity, user, data, now=now),
        "SUBMIT_OFFER": lambda: _submit_offer_form(db, user, data, now=now),
        "REVIEW_OFFER": lambda: _submit_review(db, user, data, now=now),
        "MY_OFFERS": lambda: _offer_details(db, user, _text(data.get("project_id"), 64), now=now),
        "OFFER_DETAILS": lambda: _offer_details_action(db, user, data, now=now),
    }
    handler = handlers.get(screen)
    if handler is None:
        return None
    try:
        return handler()
    except TenderError as error:
        return _contractor_error(db, user, screen, data, error, now=now)


def _contractor_error(db: Session, user: User, screen: str, data: dict[str, Any], error: TenderError, *, now: datetime) -> dict[str, Any]:
    if error.code == "payment_required":
        return _menu_error(db, user, error.message)
    if error.code == "not_approved":
        return _menu_error(db, user, error.message)
    if error.code == "not_found":
        # Without the payment gate the web hides tender details, so a tender id from an unpaid
        # contractor's list gets the subscription message rather than revealing anything.
        profile = db.get(ContractorProfile, user.id)
        if profile is not None and not profile.is_verified_active:
            return _menu_error(db, user, "Activate a subscription to view project details, drawings and to bid.")
        return _feed_screen(db, user, heading="That project is no longer available", now=now)
    if screen == "SEARCH":
        return {"screen": "SEARCH", "data": {"search": "", "trade": "", "sort": "deadline", "error_message": error.message}}
    if screen == "SUBMIT_OFFER":
        form = {k: _text(v, 1000) for k, v in data.items() if k in ("project_id", "amount", "timeline", "message")}
        return {"screen": "SUBMIT_OFFER", "data": {**_offer_form(form.get("project_id", ""), "", None), **form, "error_message": error.message}}
    if screen == "REVIEW_OFFER":
        project_id = _text(data.get("project_id"), 64)
        return {"screen": "SUBMIT_OFFER", "data": {**_offer_form(project_id, "", None), "amount": _text(data.get("amount"), 40), "timeline": _text(data.get("timeline"), 200), "message": _text(data.get("message"), 1000), "error_message": error.message}}
    if screen == "OFFER_DETAILS":
        return _offer_details(db, user, _text(data.get("project_id"), 64), now=now, message=error.message)
    project_id = _text(data.get("project_id"), 64)
    if project_id:
        return _project_details(db, user, project_id, now=now, message=error.message)
    return _feed_screen(db, user, heading="Open projects", now=now)


def contractor_menu_choice(db: Session, identity: WhatsAppIdentity, user: User, choice: str, *, now: datetime) -> dict[str, Any] | None:
    if choice == "browse_projects":
        return open_browse(db, user, now=now)
    if choice == "search_projects":
        return open_search(db, user)
    if choice == "my_offers":
        return _my_offers_screen(db, user)
    if choice == "my_awards":
        return _awards_screen(db, user)
    return None
