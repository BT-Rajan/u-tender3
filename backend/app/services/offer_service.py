"""Offer submission, revision and withdrawal. The single implementation behind the web offers routes and the WhatsApp contractor Flow.

Behaviour is the same as the original web routes: every edit and every withdrawal first snapshots the
current state into offer_revisions, so the offers row is always the latest state and revisions are an
append-only trail. The tender type locks on the first bid. Owners are notified, and a sealed tender's
notice never names the bidder.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.contractor import ContractorProfile
from app.models.enums import NotificationType, OfferStatus, ProjectStatus, TenderType
from app.models.offer import Offer, OfferRevision
from app.models.project import Project
from app.models.user import User
from app.services.email import notify_owner_new_offer
from app.services.notify import notify
from app.services.tender_service import TenderError
from app.services.whatsapp_notifications import amount_label


def snapshot_revision(db: Session, offer: Offer) -> None:
    """Freeze the current, pre-edit state of an offer into offer_revisions, then bump the counter."""
    db.add(
        OfferRevision(
            offer_id=offer.id,
            revision_number=offer.revision,
            amount=offer.amount,
            timeline_estimate=offer.timeline_estimate,
            message=offer.message,
            status=offer.status,
        )
    )
    offer.revision += 1


def submit_offer(
    db: Session,
    contractor: User,
    project_id: str,
    *,
    amount: Decimal,
    timeline_estimate: str | None,
    message: str | None,
    now: datetime,
) -> Offer:
    """Place a new offer, or revise the contractor's existing one. Callers check the payment gate first."""
    profile = db.get(ContractorProfile, contractor.id)
    project = db.get(Project, project_id)
    if not project or project.status != ProjectStatus.open or project.bid_deadline is None or project.bid_deadline < now:
        raise TenderError("closed", "Bidding on this project is closed.")
    if project.is_suspended:
        raise TenderError("suspended", "This project has been suspended and is not accepting offers.")
    if amount <= 0:
        raise TenderError("invalid", "Enter a valid bid amount.")

    # Lock the row for this transaction, so a double tap or retried request can't read the same revision number twice.
    offer = (
        db.query(Offer)
        .filter(Offer.project_id == project_id, Offer.contractor_id == contractor.id)
        .with_for_update()
        .first()
    )
    was_revision = offer is not None
    if offer:
        snapshot_revision(db, offer)
        offer.amount = amount
        offer.timeline_estimate = timeline_estimate
        offer.message = message
        offer.status = OfferStatus.submitted
        offer.updated_at = now
    else:
        offer = Offer(
            project_id=project_id,
            contractor_id=contractor.id,
            amount=amount,
            timeline_estimate=timeline_estimate,
            message=message,
            status=OfferStatus.submitted,
        )
        db.add(offer)

    # Once there is a bid, the tender type is locked (spec D-001). Idempotent, so it stays locked on revisions.
    if not project.tender_type_locked:
        project.tender_type_locked = True
    db.commit()
    db.refresh(offer)

    sealed = project.tender_type == TenderType.sealed and project.status == ProjectStatus.open
    owner = db.get(User, project.owner_id)
    if owner:
        notify_owner_new_offer(owner.email, project.title, project_id, profile.company_name, float(amount), sealed=sealed)
        # A revision is its own event, so the owner can tell it from a first bid. Sealed tenders never name the bidder or show the amount.
        # One in-app type for both, so repeat bids dedupe on the same unread notice. The WhatsApp wording
        # is chosen from is_revision.
        notify(
            db,
            owner,
            NotificationType.bid_submitted,
            link=f"/owner/projects/{project_id}",
            project_title=project.title,
            contractor_name="A contractor" if sealed else profile.company_name,
            amount_label=amount_label(float(amount), sealed),
            is_revision=was_revision,
        )
    return offer


def withdraw_offer(db: Session, contractor: User, project_id: str, *, now: datetime) -> Offer:
    offer = (
        db.query(Offer)
        .filter(Offer.project_id == project_id, Offer.contractor_id == contractor.id)
        .with_for_update()
        .first()
    )
    if not offer:
        raise TenderError("not_found", "No offer to withdraw.")
    if offer.status == OfferStatus.withdrawn:
        raise TenderError("already_withdrawn", "This offer has already been withdrawn.")
    snapshot_revision(db, offer)
    offer.status = OfferStatus.withdrawn
    offer.updated_at = now
    db.commit()
    db.refresh(offer)
    return offer
