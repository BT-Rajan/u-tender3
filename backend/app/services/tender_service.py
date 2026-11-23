"""Tender (project) lifecycle rules, shared by the web routes and the WhatsApp owner flows.

Every owner action on a tender goes through this module, so the rules live in one place:
ownership, verification, which states allow which action, deadline rules, amendment
records, and who gets notified. The web routes and the WhatsApp Flows both call it.
Web behaviour and error messages are unchanged except where noted in the module.
"""

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
from app.services.tender_lifecycle import is_sealed_and_open, sync_expired_projects

TITLE_MAX = 255
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


@dataclass
class TenderFields:
    title: str | None = None
    address: str | None = None
    description: str | None = None
    trade: str | None = None
    bid_deadline: datetime | None = None  # naive UTC, as the database stores it
    tender_type: TenderType | None = None


def parse_local_deadline(text: str) -> datetime:
    """Read 'YYYY-MM-DD HH:MM' in the tender timezone and return naive UTC.

    Owners think in local time, and the database stores UTC.
    """
    try:
        local = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(get_settings().tender_timezone))
    except (ValueError, KeyError) as exc:
        raise TenderError("invalid", "Enter the deadline as YYYY-MM-DD HH:MM.") from exc
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def format_local_deadline(deadline: datetime | None) -> str:
    if deadline is None:
        return "not set"
    utc = deadline.replace(tzinfo=ZoneInfo("UTC"))
    return utc.astimezone(ZoneInfo(get_settings().tender_timezone)).strftime("%Y-%m-%d %H:%M")


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


def create_draft(db: Session, owner: User, fields: TenderFields) -> Project:
    """Save a tender as a draft. Only the title is required, so an incomplete tender can be saved and finished later."""
    require_verified_owner(db, owner)
    title = (fields.title or "").strip()
    if not title:
        raise TenderError("invalid", "Give the tender a title.")
    if len(title) > TITLE_MAX:
        raise TenderError("invalid", f"The title must be {TITLE_MAX} characters or fewer.")
    project = Project(
        owner_id=owner.id,
        title=title,
        address=(fields.address or "").strip() or "Not set",
        description=(fields.description or "").strip() or None,
        trade=(fields.trade or "").strip() or None,
        bid_deadline=fields.bid_deadline,
        tender_type=fields.tender_type or TenderType.owner_visible,
        status=ProjectStatus.draft,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_draft(db: Session, owner: User, project: Project, fields: TenderFields) -> Project:
    """Change a draft freely. Drafts are not published, so no amendment record is made."""
    require_verified_owner(db, owner)
    if project.status != ProjectStatus.draft:
        raise TenderError("not_draft", "Only a draft can be edited this way. Use amend for a published tender.")
    if fields.title is not None:
        title = fields.title.strip()
        if not title:
            raise TenderError("invalid", "Give the tender a title.")
        project.title = title[:TITLE_MAX]
    if fields.address is not None:
        project.address = fields.address.strip() or "Not set"
    if fields.description is not None:
        project.description = fields.description.strip() or None
    if fields.trade is not None:
        project.trade = fields.trade.strip() or None
    if fields.bid_deadline is not None:
        project.bid_deadline = fields.bid_deadline
    if fields.tender_type is not None:
        project.tender_type = fields.tender_type
    db.commit()
    db.refresh(project)
    return project


def publish(db: Session, owner: User, project: Project, now: datetime) -> Project:
    """Draft -> open. The gate is the same as the web: draft only, deadline in the future."""
    require_verified_owner(db, owner)
    if project.status != ProjectStatus.draft:
        raise TenderError("not_draft", "Only a draft project can be published.")
    if not project.title or not project.address or project.address == "Not set":
        raise TenderError("incomplete", "Add the address before publishing.")
    if project.bid_deadline is None or project.bid_deadline <= now:
        raise TenderError("deadline_past", "Set a bid deadline in the future before publishing.")
    project.status = ProjectStatus.open
    db.commit()
    db.refresh(project)
    return project


def amend(db: Session, owner: User, project: Project, fields: TenderFields, *, reason: str | None, now: datetime) -> Project:
    """Change a tender's content.

    A draft is edited directly. A published tender gets a numbered amendment record,
    its revision goes up, and every bidder with a live offer is told. A deadline can't
    move earlier once bids have locked the tender type.
    """
    require_verified_owner(db, owner)
    if project.status not in AMENDABLE:
        raise TenderError("not_amendable", "This project can no longer be amended.")
    if project.status == ProjectStatus.draft:
        return update_draft(db, owner, project, fields)

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
    actions.append("offers")
    return actions
