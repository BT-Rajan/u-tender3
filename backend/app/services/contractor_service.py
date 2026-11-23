"""Contractor-side rules shared by the web routes and the WhatsApp contractor Flow.

Three gates, applied in the same places as before:
- verification: approved, not suspended. Needed to browse the feed and to withdraw.
- marketplace (payment): is_verified_active. Needed to see drawings and to submit or revise an offer.
- visibility: a tender is visible to a contractor when it isn't a draft, isn't admin-suspended, and the
  contractor passes the marketplace gate.

Contractors only ever see their own offers. Offer counts are shown, never bidder details.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.award_record import AwardRecord
from app.models.contractor import ContractorProfile
from app.models.enums import OfferStatus, ProjectStatus, UserRole, VerificationStatus
from app.models.offer import Offer, OfferRevision
from app.models.project import Project, ProjectDrawing
from app.models.user import User
from app.services.storage import drawing_url_expiry_seconds, get_storage
from app.services.tender_service import TenderError

FEED_LIMIT = 20
DRAWING_BUCKET = "project-drawings"


def _profile(db: Session, user: User) -> ContractorProfile | None:
    return db.get(ContractorProfile, user.id)


def require_approved(db: Session, user: User) -> None:
    """Verification gate: approved and not suspended. Needed to browse the feed and to withdraw."""
    profile = _profile(db, user)
    if profile is None or profile.verification_status != VerificationStatus.approved or profile.is_suspended:
        raise TenderError("not_approved", "Your account must be verified to do this.")


def require_marketplace(db: Session, user: User) -> None:
    """Payment gate: verified and paid (subscription or admin override). Needed for drawings and for bidding."""
    profile = _profile(db, user)
    if profile is None or not profile.is_verified_active:
        raise TenderError("payment_required", "Activate a subscription to bid on projects and see drawings.")


def can_view_project(db: Session, user: User, project: Project) -> bool:
    """Who may see a tender. Owners and admins always. Contractors need the marketplace gate, and drafts and admin-suspended tenders are hidden from them."""
    if user.role == UserRole.admin or project.owner_id == user.id:
        return True
    if user.role != UserRole.contractor:
        return False
    if project.status == ProjectStatus.draft or project.is_suspended:
        return False
    profile = _profile(db, user)
    return bool(profile and profile.is_verified_active)


def _offer_count(db: Session, project_id: str) -> int:
    return db.query(Offer).filter(Offer.project_id == project_id).count()


def _my_offer(db: Session, user: User, project_id: str) -> Offer | None:
    return db.query(Offer).filter(Offer.project_id == project_id, Offer.contractor_id == user.id).first()


def feed(
    db: Session,
    user: User,
    *,
    search: str | None = None,
    trade: str | None = None,
    sort: str = "deadline",
    now: datetime,
) -> list[dict[str, Any]]:
    """Open tenders, filtered and sorted as the web feed does. Verification is enough to browse."""
    require_approved(db, user)
    query = db.query(Project).filter(Project.status == ProjectStatus.open, Project.is_suspended.is_(False))
    if trade and trade.strip():
        query = query.filter(Project.trade.ilike(f"%{trade.strip()}%"))
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(Project.title.ilike(term), Project.address.ilike(term), Project.description.ilike(term)))
    query = query.order_by(Project.created_at.desc()) if sort == "newest" else query.order_by(Project.bid_deadline.asc())

    my_status = {o.project_id: o.status for o in db.query(Offer).filter(Offer.contractor_id == user.id).all()}
    rows = []
    for project in query.limit(FEED_LIMIT).all():
        rows.append(
            {
                "project": project,
                "offer_count": _offer_count(db, project.id),
                "my_offer_status": my_status.get(project.id),
            }
        )
    return rows


def project_view(db: Session, user: User, project_id: str, *, now: datetime) -> dict[str, Any]:
    """One tender as this contractor may see it, with what they are allowed to do.

    Any tender they may not view is reported as not found, so tender ids can't be probed.
    """
    project = db.get(Project, project_id)
    if project is None or not can_view_project(db, user, project):
        raise TenderError("not_found", "Project not found.")
    open_for_bids = project.status == ProjectStatus.open and project.bid_deadline is not None and project.bid_deadline > now
    mine = _my_offer(db, user, project_id)
    marketplace = bool(_profile(db, user) and _profile(db, user).is_verified_active)
    drawings = [d for d in project.drawings if d.is_current]
    return {
        "project": project,
        "offer_count": _offer_count(db, project_id),
        "my_offer": mine,
        "open_for_bids": open_for_bids and not project.is_suspended,
        "can_bid": marketplace and open_for_bids and not project.is_suspended,
        "drawing_count": len(drawings) if marketplace else 0,
        "can_get_drawings": marketplace and bool(drawings),
    }


def my_offers(db: Session, user: User) -> list[tuple[Offer, Project]]:
    """Every offer this contractor has placed. Own offers only. Role only, so a lapsed subscription doesn't hide what was bid."""
    return (
        db.query(Offer, Project)
        .join(Project, Offer.project_id == Project.id)
        .filter(Offer.contractor_id == user.id)
        .order_by(Offer.updated_at.desc())
        .all()
    )


def my_offer_detail(db: Session, user: User, project_id: str) -> tuple[Offer, Project, int]:
    """This contractor's own offer on a tender, and how many revisions it has had."""
    offer = _my_offer(db, user, project_id)
    if offer is None:
        raise TenderError("not_found", "No offer found for this project.")
    project = db.get(Project, project_id)
    revisions = db.query(OfferRevision).filter(OfferRevision.offer_id == offer.id).count()
    return offer, project, revisions


def my_offer_history(db: Session, user: User, project_id: str) -> list[OfferRevision]:
    offer = _my_offer(db, user, project_id)
    if offer is None:
        return []
    return (
        db.query(OfferRevision)
        .filter(OfferRevision.offer_id == offer.id)
        .order_by(OfferRevision.revision_number.asc())
        .all()
    )


def my_awards(db: Session, user: User) -> list[tuple[AwardRecord, Project]]:
    """Tenders this contractor has won. Own awards only."""
    return (
        db.query(AwardRecord, Project)
        .join(Project, AwardRecord.project_id == Project.id)
        .filter(AwardRecord.contractor_id == user.id)
        .order_by(AwardRecord.created_at.desc())
        .all()
    )


def drawing_links(db: Session, user: User, project_id: str, *, now: datetime) -> list[tuple[str, str]]:
    """Signed, expiring links to the current drawings. Same gate as viewing: marketplace-active and the tender visible.

    Expiry follows the bid deadline, as on the web. The links are only ever sent to the requesting
    contractor's own chat.
    """
    require_marketplace(db, user)
    project = db.get(Project, project_id)
    if project is None or not can_view_project(db, user, project):
        raise TenderError("not_found", "Project not found.")
    drawings: list[ProjectDrawing] = [d for d in project.drawings if d.is_current]
    if not drawings:
        raise TenderError("no_drawings", "There are no drawings on this project.")
    expiry = drawing_url_expiry_seconds(project.bid_deadline)
    storage = get_storage()
    return [(d.file_name, storage.signed_url(DRAWING_BUCKET, d.file_path, expiry)) for d in drawings]
