import logging
"""Tender (project) lifecycle rules, shared by the web routes and the WhatsApp owner flows.

Every owner action on a tender goes through this module, so the rules live in one place:
ownership, verification, which states allow which action, deadline rules, amendment
records, and who gets notified. The web routes and the WhatsApp Flows both call it.
Web behaviour and error messages are unchanged except where noted in the module.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import NotificationType, OfferStatus, ProjectStatus, TenderType
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.project_amendment import ProjectAmendment
from app.models.user import User
from app.services.audit import log_action
from app.services.email import notify_contractor_tender_amended
from app.services.notify import notify
from app.services.whatsapp_notifications import fan_out_new_tender
from app.services.tender_lifecycle import is_sealed_and_open, sync_expired_projects

_log = logging.getLogger(__name__)

TITLE_MAX = 255
DESCRIPTION_MAX = 1000
ADDRESS_MAX = 500
LIST_LIMIT = 20

# Statuses in which a tender's content can still be amended. Mirrors the web PATCH.
AMENDABLE = (ProjectStatus.draft, ProjectStatus.open, ProjectStatus.closed, ProjectStatus.under_evaluation)
CANCELABLE = (ProjectStatus.draft, ProjectStatus.open, ProjectStatus.closed, ProjectStatus.under_evaluation)


class TenderError(Exception):
    """A rule was broken. `code` is stable for callers that map it to HTTP or a Flow message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

def earliest_bid_date_ms(now: datetime) -> int:
    """The start of today in the tender timezone, in epoch milliseconds: the earliest day the calendar may pick."""
    zone = ZoneInfo(get_settings().tender_timezone)
    local = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
    start = datetime(local.year, local.month, local.day, tzinfo=zone)
    return int(start.timestamp() * 1000)


def check_tender_values(
    *,
    title: str | None,
    address: str | None,
    trade: str | None,
    description: str | None,
    bid_deadline: datetime | None,
    tender_type: Any,
    now: datetime,
    require_future_deadline: bool = True,
) -> dict[str, Any]:
    """The standard every tender meets before it is saved, drafts included, on every channel.

    Title, address, trade, bid end date and tender type are required. The description is optional.
    The bid end date must be in the future. Raises TenderError for the first problem found.
    """
    from app.services.registration import TRADE_OPTIONS  # local: registration imports the same package

    title = (title or "").strip()
    if not title:
        raise TenderError("invalid", "Give the tender a title.")
    if len(title) > TITLE_MAX:
        raise TenderError("invalid", f"The title must be {TITLE_MAX} characters or fewer.")
    address = (address or "").strip()
    if not address or address == "Not set":
        raise TenderError("invalid", "Add the address.")
    if len(address) > ADDRESS_MAX:
        raise TenderError("invalid", f"The address must be {ADDRESS_MAX} characters or fewer.")
    description = (description or "").strip() or None
    if description is not None and len(description) > DESCRIPTION_MAX:
        raise TenderError("invalid", f"The description must be {DESCRIPTION_MAX} characters or fewer.")
    trade = (trade or "").strip()
    if not trade:
        raise TenderError("invalid", "Choose the trade.")
    if trade not in TRADE_OPTIONS:
        raise TenderError("invalid", "Choose a trade from the list.")
    if bid_deadline is None:
        raise TenderError("invalid", "Set the bid end date.")
    if require_future_deadline and bid_deadline <= now:
        raise TenderError("deadline_past", "Set a bid end date in the future.")
    kind = tender_type.value if isinstance(tender_type, TenderType) else (tender_type or TenderType.owner_visible.value)
    if kind not in (TenderType.sealed.value, TenderType.owner_visible.value):
        raise TenderError("invalid", "Choose sealed or owner visible.")
    return {
        "title": title,
        "address": address,
        "description": description,
        "trade": trade,
        "bid_deadline": bid_deadline,
        "tender_type": TenderType(kind),
    }


@dataclass
class TenderFields:
    title: str | None = None
    address: str | None = None
    description: str | None = None
    trade: str | None = None
    bid_deadline: datetime | None = None  # naive UTC, as the database stores it
    tender_type: TenderType | None = None


# A bid end date is typed as DD-MM-YYYY. A date with no time ends at the close of that day.
DEADLINE_DATE_FORMAT = "%d-%m-%Y"
DEADLINE_DATE_TIME_FORMAT = "%d-%m-%Y %H:%M"
END_OF_DAY = (23, 59)


def parse_local_deadline(text: str) -> datetime:
    """Read 'DD-MM-YYYY' (or 'DD-MM-YYYY HH:MM') in the tender timezone and return naive UTC.

    Owners think in local time, and the database stores UTC.
    """
    raw = text.strip()
    local: datetime | None = None
    try:
        local = datetime.strptime(raw, DEADLINE_DATE_TIME_FORMAT)
    except ValueError:
        try:
            local = datetime.strptime(raw, DEADLINE_DATE_FORMAT).replace(hour=END_OF_DAY[0], minute=END_OF_DAY[1])
        except ValueError as exc:
            raise TenderError("invalid", "Enter the bid end date as DD-MM-YYYY.") from exc
    local = local.replace(tzinfo=ZoneInfo(get_settings().tender_timezone))
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def format_local_deadline(deadline: datetime | None) -> str:
    if deadline is None:
        return "not set"
    utc = deadline.replace(tzinfo=ZoneInfo("UTC"))
    local = utc.astimezone(ZoneInfo(get_settings().tender_timezone))
    if (local.hour, local.minute) == END_OF_DAY:
        return local.strftime(DEADLINE_DATE_FORMAT)
    return local.strftime(DEADLINE_DATE_TIME_FORMAT)


def to_utc_naive(value: datetime | str) -> datetime:
    """A deadline sent from the web, stored as naive UTC. A value with no zone is Kuwait wall time
    (the form has no zone); a value with a zone is converted. Kuwait has no daylight saving."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(get_settings().tender_timezone))
    return value.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _local(deadline: datetime) -> datetime:
    """A stored (UTC, naive) deadline in the tender timezone."""
    return deadline.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(get_settings().tender_timezone))


def same_local_day(first: datetime, second: datetime) -> bool:
    a, b = _local(first), _local(second)
    return (a.year, a.month, a.day) == (b.year, b.month, b.day)


def deadline_from_calendar(value: Any) -> datetime:
    """The end of the day the calendar picked. The calendar sends epoch milliseconds."""
    zone = ZoneInfo(get_settings().tender_timezone)
    try:
        picked = datetime.fromtimestamp(int(float(value)) / 1000, zone)
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise TenderError("invalid", "Choose the bid end date from the calendar.") from exc
    end = datetime(picked.year, picked.month, picked.day, END_OF_DAY[0], END_OF_DAY[1], tzinfo=zone)
    return end.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def calendar_value(deadline: datetime) -> str:
    """The deadline's day as YYYY-MM-DD in the tender timezone. Meta's DatePicker takes its start value as text."""
    return _local(deadline).strftime("%Y-%m-%d")


def owner_project(db: Session, owner: User, project_id: str) -> Project:
    """The tender, if this owner owns it. Anything else looks identical to a missing tender, so ids can't be probed."""
    project = db.get(Project, project_id)
    if not project or project.owner_id != owner.id:
        raise TenderError("not_found", "Project not found.")
    return project


def require_verified_owner(db: Session, owner: User) -> None:
    """Posting or changing a tender needs a verified, unsuspended owner. Same rule as the web create route."""
    profile = db.get(OwnerProfile, owner.id)
    if profile is None or not profile.is_verified_active:
        raise TenderError("not_verified", "Your account must be verified before you can post tenders.")


def create_draft(db: Session, owner: User, fields: TenderFields, *, verified_required: bool = True) -> Project:
    """Save a tender as a draft. A draft meets the same standard as a published tender, so nothing incomplete is saved."""
    if verified_required:
        require_verified_owner(db, owner)
    values = check_tender_values(
        title=fields.title, address=fields.address, trade=fields.trade, description=fields.description,
        bid_deadline=fields.bid_deadline, tender_type=fields.tender_type, now=datetime.utcnow(),
    )
    project = Project(owner_id=owner.id, status=ProjectStatus.draft, **values)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_draft(
    db: Session, owner: User, project: Project, fields: TenderFields, *, verified_required: bool = True
) -> Project:
    """Change a draft freely. Drafts are not published, so no amendment record is made."""
    if verified_required:
        require_verified_owner(db, owner)
    if project.status != ProjectStatus.draft:
        raise TenderError("not_draft", "Only a draft can be edited this way. Use amend for a published tender.")
    current = {
        "title": project.title,
        "address": project.address,
        "description": project.description,
        "trade": project.trade,
        "bid_deadline": project.bid_deadline,
        "tender_type": project.tender_type,
    }
    for key in current:
        value = getattr(fields, key)
        if value is not None:
            current[key] = value
    values = check_tender_values(**current, now=datetime.utcnow())
    for key, value in values.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


def _new_reference_code(db: Session) -> str:
    """A six-digit tender number that no other tender has."""
    for _ in range(50):
        code = str(secrets.randbelow(900000) + 100000)
        if db.scalar(select(Project.id).where(Project.reference_code == code)) is None:
            return code
    raise TenderError("busy", "Could not give this tender a number. Try publishing again.")


def publish(db: Session, owner: User, project: Project, now: datetime, *, verified_required: bool = True) -> Project:
    """Draft -> open. The gate is the same as the web: draft only, deadline in the future."""
    if verified_required:
        require_verified_owner(db, owner)
    if project.status != ProjectStatus.draft:
        raise TenderError("not_draft", "Only a draft project can be published.")
    check_tender_values(
        title=project.title, address=project.address, trade=project.trade, description=project.description,
        bid_deadline=project.bid_deadline, tender_type=project.tender_type, now=now,
    )
    if project.reference_code is None:
        project.reference_code = _new_reference_code(db)
    project.status = ProjectStatus.open
    db.commit()
    db.refresh(project)
    try:
        fan_out_new_tender(db, project, now=now, notify=notify)
    except Exception:
        # The tender is already published. A failed contractor notice must not turn that into an error
        # for the owner, who would otherwise see "Something went wrong" for a tender that is live.
        db.rollback()
        _log.exception('Could not notify contractors about tender %s', project.id)
        db.refresh(project)
    return project


def amend(
    db: Session,
    owner: User,
    project: Project,
    fields: TenderFields,
    *,
    reason: str | None,
    now: datetime,
    verified_required: bool = True,
) -> Project:
    """Change a tender's content.

    A draft is edited directly. A published tender gets a numbered amendment record,
    its revision goes up, and every bidder with a live offer is told. A deadline can't
    move earlier once bids have locked the tender type.
    """
    if verified_required:
        require_verified_owner(db, owner)
    if project.status not in AMENDABLE:
        raise TenderError("not_amendable", "This project can no longer be amended.")
    if project.status == ProjectStatus.draft:
        return update_draft(db, owner, project, fields)

    # The standard applies to the tender as it will read after the change. The deadline is only
    # re-checked when it is being changed.
    check_tender_values(
        title=fields.title if fields.title is not None else project.title,
        address=project.address,
        trade=fields.trade if fields.trade is not None else project.trade,
        description=fields.description if fields.description is not None else project.description,
        bid_deadline=fields.bid_deadline if fields.bid_deadline is not None else project.bid_deadline,
        tender_type=project.tender_type,
        now=now,
        require_future_deadline=fields.bid_deadline is not None,
    )

    changed: list[str] = []
    if fields.title is not None:
        title = fields.title.strip()
        if not title:
            raise TenderError("invalid", "Title cannot be empty.")
        if title != project.title:
            changed.append("title")
            project.title = title[:TITLE_MAX]
    if fields.description is not None and (fields.description or None) != project.description:
        changed.append("description")
        project.description = fields.description or None
    if fields.trade is not None and (fields.trade or None) != project.trade:
        changed.append("trade")
        project.trade = fields.trade or None

    deadline_extended = False
    if fields.bid_deadline is not None and fields.bid_deadline != project.bid_deadline:
        # A bid already locks the tender type (spec D-001). For the same reason the deadline
        # can't move earlier once bidders have priced against it.
        if project.bid_deadline and fields.bid_deadline < project.bid_deadline and project.tender_type_locked:
            raise TenderError("deadline_locked", "Cannot move the deadline earlier once bids have been submitted.")
        deadline_extended = bool(project.bid_deadline and fields.bid_deadline > project.bid_deadline)
        changed.append("bid_deadline")
        project.bid_deadline = fields.bid_deadline

    if not changed:
        raise TenderError("no_changes", "No changes were provided.")

    amendment_number = db.query(ProjectAmendment).filter(ProjectAmendment.project_id == project.id).count() + 1
    summary = f"Updated {', '.join(changed)}."
    db.add(
        ProjectAmendment(
            project_id=project.id,
            amendment_number=amendment_number,
            summary=summary,
            changed_fields=", ".join(changed),
            reason=(reason or "").strip() or None,
            deadline_extended=deadline_extended,
            created_by=owner.id,
        )
    )
    project.revision += 1
    db.commit()
    db.refresh(project)

    # Best-effort: a failed send never rolls the amendment back.
    for (contractor_id,) in (
        db.query(Offer.contractor_id)
        .filter(Offer.project_id == project.id, Offer.status != OfferStatus.withdrawn)
        .distinct()
        .all()
    ):
        contractor = db.get(User, contractor_id)
        if contractor:
            notify_contractor_tender_amended(contractor.email, project.title, project.id, summary)
            notify(
                db,
                contractor,
                NotificationType.tender_amendment,
                link=f"/contractor/projects/{project.id}/offer",
                project_title=project.title,
                summary=summary,
            )
    return project


def close(db: Session, owner: User, project: Project) -> Project:
    if project.status != ProjectStatus.open:
        raise TenderError("bad_state", "Only an open project can be closed.")
    project.status = ProjectStatus.closed
    db.commit()
    db.refresh(project)
    return project


def start_evaluation(db: Session, owner: User, project: Project) -> Project:
    if project.status != ProjectStatus.closed:
        raise TenderError("bad_state", "Only a closed project can enter evaluation.")
    project.status = ProjectStatus.under_evaluation
    db.commit()
    db.refresh(project)
    return project


def _notify_bidders(db: Session, project: Project, notification_type: NotificationType) -> None:
    for (contractor_id,) in (
        db.query(Offer.contractor_id)
        .filter(Offer.project_id == project.id, Offer.status != OfferStatus.withdrawn)
        .distinct()
        .all()
    ):
        bidder = db.get(User, contractor_id)
        if bidder:
            notify(db, bidder, notification_type, link=f"/contractor/projects/{project.id}/offer", project_title=project.title)


def mark_no_award(db: Session, owner: User, project: Project) -> Project:
    if project.status not in (ProjectStatus.closed, ProjectStatus.under_evaluation):
        raise TenderError("bad_state", "Only a closed or under-evaluation project can be marked no-award.")
    previous = project.status.value
    project.status = ProjectStatus.no_award
    db.commit()
    log_action(db, actor_id=owner.id, action="project.no_award", target_type="project", target_id=project.id, previous_value=previous, new_value="no_award")
    _notify_bidders(db, project, NotificationType.tender_no_award)
    db.refresh(project)
    return project


def cancel(db: Session, owner: User, project: Project) -> Project:
    if project.status not in CANCELABLE:
        raise TenderError("bad_state", "This project can no longer be canceled.")
    previous = project.status.value
    project.status = ProjectStatus.canceled
    db.commit()
    log_action(db, actor_id=owner.id, action="project.cancel", target_type="project", target_id=project.id, previous_value=previous, new_value="canceled")
    _notify_bidders(db, project, NotificationType.tender_cancelled)
    db.refresh(project)
    return project


def list_owner_tenders(db: Session, owner: User, *, now: datetime) -> list[Project]:
    """The owner's tenders, newest first, with expired ones moved to their final state first."""
    sync_expired_projects(db)
    return list(
        db.scalars(
            select(Project).where(Project.owner_id == owner.id).order_by(Project.created_at.desc()).limit(LIST_LIMIT)
        ).all()
    )


def offer_count(db: Session, project: Project) -> int:
    return db.query(Offer).filter(Offer.project_id == project.id).count()


def received_offers(db: Session, owner: User, project: Project) -> dict[str, Any]:
    """Offers the owner may see, with the sealed-bid rule applied.

    While the tender is sealed and open, bidder identity and amount are withheld,
    and offers are listed in submission order so their order can't reveal price.
    Once the seal lifts, the list is sorted by amount, as on the web.
    Admin-suspended offers are never shown.
    """
    from app.models.contractor import ContractorProfile

    sealed = is_sealed_and_open(project)
    query = (
        db.query(Offer, ContractorProfile)
        .join(ContractorProfile, Offer.contractor_id == ContractorProfile.user_id)
        .filter(Offer.project_id == project.id, Offer.is_suspended.is_(False))
    )
    query = query.order_by(Offer.created_at.asc()) if sealed else query.order_by(Offer.amount.asc())
    rows = []
    for index, (offer, profile) in enumerate(query.all(), start=1):
        if sealed:
            rows.append(
                {
                    "offer_id": offer.id,
                    "label": f"Offer {index}",
                    "status": offer.status.value,
                    "submitted_at": offer.created_at,
                    "company": None,
                    "amount": None,
                    "timeline": None,
                }
            )
        else:
            rows.append(
                {
                    "offer_id": offer.id,
                    "label": profile.company_name,
                    "status": offer.status.value,
                    "submitted_at": offer.created_at,
                    "company": profile.company_name,
                    "amount": float(offer.amount),
                    "timeline": offer.timeline_estimate,
                }
            )
    return {"sealed": sealed, "rows": rows}


def allowed_actions(project: Project) -> list[str]:
    """The owner actions this tender's current state allows. The Flow only ever offers these."""
    actions: list[str] = ["details"]
    status = project.status
    if status in AMENDABLE:
        actions.append("edit")
    if status == ProjectStatus.draft:
        actions.append("publish")
    if status == ProjectStatus.open:
        actions.append("close")
    if status == ProjectStatus.closed:
        actions.append("start_evaluation")
    if status in (ProjectStatus.closed, ProjectStatus.under_evaluation):
        actions.append("no_award")
    if status in CANCELABLE:
        actions.append("cancel")
    if status != ProjectStatus.draft:
        actions.append("offers")
        actions.append("quotations")
    return actions
