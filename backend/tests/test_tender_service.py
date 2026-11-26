"""Tender lifecycle rules in the shared service. Both the web routes and the WhatsApp owner Flow depend on these."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.contractor import ContractorProfile
from app.models.enums import NotificationType, OfferStatus, ProjectStatus, TenderType, UserRole, VerificationStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.project_amendment import ProjectAmendment
from app.models.user import User
from app.services import tender_service
from app.services.tender_service import TenderError, TenderFields

NOW = datetime.utcnow()
FUTURE = NOW + timedelta(days=10)


def _owner(db, email="owner@example.com", verified=True, suspended=False):
    user = User(email=email, password_hash="x", role=UserRole.owner, full_name="Layla Al-Sabah", email_verified=True)
    db.add(user)
    db.flush()
    db.add(
        OwnerProfile(
            user_id=user.id,
            verification_status=VerificationStatus.approved if verified else VerificationStatus.incomplete,
            is_suspended=suspended,
        )
    )
    db.commit()
    return user


def _contractor(db, name="Haddad Builders", email="con@example.com"):
    user = User(email=email, password_hash="x", role=UserRole.contractor, full_name="Omar", email_verified=True)
    db.add(user)
    db.flush()
    db.add(ContractorProfile(user_id=user.id, company_name=name, verification_status=VerificationStatus.approved))
    db.commit()
    return user


def _project(db, owner, status=ProjectStatus.open, tender_type=TenderType.owner_visible, deadline=FUTURE, **extra):
    project = Project(
        owner_id=owner.id,
        title="Villa renovation",
        address="Block 3, Salmiya",
        description="Ground floor",
        trade="Civil works",
        bid_deadline=deadline,
        status=status,
        tender_type=tender_type,
        **extra,
    )
    db.add(project)
    db.commit()
    return project


def _offer(db, project, contractor, amount, status=OfferStatus.submitted, suspended=False, created=None):
    offer = Offer(
        project_id=project.id,
        contractor_id=contractor.id,
        amount=Decimal(str(amount)),
        timeline_estimate="6 months",
        status=status,
        is_suspended=suspended,
    )
    if created:
        offer.created_at = created
    db.add(offer)
    db.commit()
    return offer


# --- the standard: creating, editing and publishing ------------------------------


def _complete(**overrides):
    base = dict(
        title="Villa renovation",
        address="Block 3, Salmiya",
        description=None,
        trade="Electrical",
        bid_deadline=FUTURE,
        tender_type=TenderType.owner_visible,
    )
    base.update(overrides)
    return TenderFields(**base)


def test_a_draft_needs_the_full_standard_before_it_is_saved(db):
    owner = _owner(db)
    with pytest.raises(TenderError) as excinfo:
        tender_service.create_draft(db, owner, TenderFields(title="Villa renovation"))
    assert excinfo.value.code == "invalid"
    assert db.query(Project).count() == 0


def test_a_complete_draft_is_saved_with_its_trade_and_deadline(db):
    owner = _owner(db)
    project = tender_service.create_draft(db, owner, _complete())
    assert project.status == ProjectStatus.draft
    assert project.trade == "Electrical"
    assert project.bid_deadline == FUTURE


def test_a_draft_without_a_title_is_refused(db):
    owner = _owner(db)
    with pytest.raises(TenderError) as excinfo:
        tender_service.create_draft(db, owner, _complete(title="   "))
    assert excinfo.value.code == "invalid"


def test_an_overlong_title_is_refused(db):
    owner = _owner(db)
    with pytest.raises(TenderError):
        tender_service.create_draft(db, owner, _complete(title="x" * 256))


def test_a_trade_is_required_and_must_be_on_the_list(db):
    owner = _owner(db)
    with pytest.raises(TenderError) as missing:
        tender_service.create_draft(db, owner, _complete(trade=None))
    assert missing.value.message == "Choose the trade."
    with pytest.raises(TenderError) as unlisted:
        tender_service.create_draft(db, owner, _complete(trade="Roofing"))
    assert unlisted.value.message == "Choose a trade from the list."
    assert db.query(Project).count() == 0


def test_a_deadline_in_the_past_is_refused_when_saving(db):
    owner = _owner(db)
    with pytest.raises(TenderError) as excinfo:
        tender_service.create_draft(db, owner, _complete(bid_deadline=NOW - timedelta(hours=1)))
    assert excinfo.value.code == "deadline_past"


def test_an_unverified_owner_cannot_create_a_draft(db):
    owner = _owner(db, verified=False)
    with pytest.raises(TenderError) as excinfo:
        tender_service.create_draft(db, owner, _complete())
    assert excinfo.value.code == "not_verified"
    assert db.query(Project).count() == 0


def test_a_suspended_owner_cannot_create_a_draft(db):
    owner = _owner(db, suspended=True)
    with pytest.raises(TenderError) as excinfo:
        tender_service.create_draft(db, owner, _complete())
    assert excinfo.value.code == "not_verified"


def test_editing_a_draft_changes_it_in_place_without_an_amendment(db):
    owner = _owner(db)
    project = tender_service.create_draft(db, owner, _complete())
    tender_service.update_draft(db, owner, project, TenderFields(address="Block 4"))
    db.refresh(project)
    assert project.address == "Block 4"
    assert project.trade == "Electrical"
    assert db.query(ProjectAmendment).count() == 0


def test_an_edit_cannot_clear_a_required_field(db):
    owner = _owner(db)
    project = tender_service.create_draft(db, owner, _complete())
    with pytest.raises(TenderError) as excinfo:
        tender_service.update_draft(db, owner, project, TenderFields(trade=""))
    assert excinfo.value.message == "Choose the trade."
    db.refresh(project)
    assert project.trade == "Electrical"


def test_a_published_tender_cannot_be_edited_as_a_draft(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open)
    with pytest.raises(TenderError) as excinfo:
        tender_service.update_draft(db, owner, project, TenderFields(title="New"))
    assert excinfo.value.code == "not_draft"


# --- publishing ----------------------------------------------------------------


def test_publishing_a_complete_draft_with_a_future_deadline_opens_it(db):
    owner = _owner(db)
    project = tender_service.create_draft(db, owner, _complete())
    tender_service.publish(db, owner, project, NOW)
    assert project.status == ProjectStatus.open


def test_publishing_a_draft_whose_deadline_has_passed_is_refused(db):
    owner = _owner(db)
    project = tender_service.create_draft(db, owner, _complete())
    project.bid_deadline = NOW - timedelta(hours=1)
    db.commit()
    with pytest.raises(TenderError) as excinfo:
        tender_service.publish(db, owner, project, NOW)
    assert excinfo.value.code == "deadline_past"
    assert project.status == ProjectStatus.draft


def test_publishing_without_an_address_is_refused(db):
    owner = _owner(db)
    project = tender_service.create_draft(db, owner, _complete())
    project.address = "Not set"
    db.commit()
    with pytest.raises(TenderError) as excinfo:
        tender_service.publish(db, owner, project, NOW)
    assert excinfo.value.code == "invalid"
    assert project.status == ProjectStatus.draft


def test_only_a_draft_can_be_published(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open)
    with pytest.raises(TenderError) as excinfo:
        tender_service.publish(db, owner, project, NOW)
    assert excinfo.value.code == "not_draft"


def test_an_unverified_owner_cannot_publish(db):
    owner = _owner(db, verified=False)
    project = _project(db, owner, status=ProjectStatus.draft, deadline=FUTURE)
    with pytest.raises(TenderError) as excinfo:
        tender_service.publish(db, owner, project, NOW)
    assert excinfo.value.code == "not_verified"
    assert project.status == ProjectStatus.draft


# --- amending a published tender ----------------------------------------------


def test_amending_a_published_tender_records_a_numbered_amendment_and_bumps_the_revision(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open)
    tender_service.amend(db, owner, project, TenderFields(title="Villa renovation phase 2"), reason="Scope change", now=NOW)

    amendment = db.scalar(select(ProjectAmendment).where(ProjectAmendment.project_id == project.id))
    assert amendment.amendment_number == 1
    assert amendment.changed_fields == "title"
    assert amendment.reason == "Scope change"
    assert amendment.created_by == owner.id
    assert project.revision == 2


def test_amending_notifies_every_bidder_with_a_live_offer_but_not_withdrawn_ones(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open)
    live = _contractor(db, email="live@example.com")
    withdrawn = _contractor(db, name="Withdrawn Co", email="gone@example.com")
    _offer(db, project, live, 100)
    _offer(db, project, withdrawn, 90, status=OfferStatus.withdrawn)

    tender_service.amend(db, owner, project, TenderFields(description="New scope"), reason=None, now=NOW)

    told = {n.user_id for n in db.scalars(select(Notification).where(Notification.type == NotificationType.tender_amendment)).all()}
    assert live.id in told
    assert withdrawn.id not in told


def test_a_deadline_cannot_move_earlier_once_bids_have_locked_the_tender(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open, tender_type_locked=True)
    with pytest.raises(TenderError) as excinfo:
        tender_service.amend(db, owner, project, TenderFields(bid_deadline=FUTURE - timedelta(days=3)), reason=None, now=NOW)
    assert excinfo.value.code == "deadline_locked"


def test_a_deadline_can_be_extended_after_bids_and_is_flagged_as_an_extension(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open, tender_type_locked=True)
    tender_service.amend(db, owner, project, TenderFields(bid_deadline=FUTURE + timedelta(days=5)), reason=None, now=NOW)
    assert db.scalar(select(ProjectAmendment)).deadline_extended is True


def test_an_amendment_with_no_real_change_is_refused_and_records_nothing(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open)
    with pytest.raises(TenderError) as excinfo:
        tender_service.amend(db, owner, project, TenderFields(title="Villa renovation"), reason=None, now=NOW)
    assert excinfo.value.code == "no_changes"
    assert db.query(ProjectAmendment).count() == 0


def test_a_canceled_tender_cannot_be_amended(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.canceled)
    with pytest.raises(TenderError) as excinfo:
        tender_service.amend(db, owner, project, TenderFields(title="New"), reason=None, now=NOW)
    assert excinfo.value.code == "not_amendable"


def test_an_awarded_tender_cannot_be_amended(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.awarded)
    with pytest.raises(TenderError):
        tender_service.amend(db, owner, project, TenderFields(title="New"), reason=None, now=NOW)


# --- ownership -------------------------------------------------------------------


def test_another_owners_tender_looks_like_a_missing_one(db):
    owner = _owner(db)
    stranger = _owner(db, email="other@example.com")
    project = _project(db, owner, status=ProjectStatus.open)
    with pytest.raises(TenderError) as excinfo:
        tender_service.owner_project(db, stranger, project.id)
    assert excinfo.value.code == "not_found"
    assert excinfo.value.message == "Project not found."


def test_a_missing_tender_is_not_found(db):
    owner = _owner(db)
    with pytest.raises(TenderError) as excinfo:
        tender_service.owner_project(db, owner, "no-such-id")
    assert excinfo.value.code == "not_found"


def test_my_tenders_lists_only_the_owners_own(db):
    owner = _owner(db)
    other = _owner(db, email="other@example.com")
    mine = _project(db, owner, status=ProjectStatus.open)
    _project(db, other, status=ProjectStatus.open)

    listed = tender_service.list_owner_tenders(db, owner, now=NOW)

    assert [p.id for p in listed] == [mine.id]


# --- lifecycle transitions -----------------------------------------------------


def test_open_then_closed_then_under_evaluation_is_the_normal_path(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open)
    tender_service.close(db, owner, project)
    assert project.status == ProjectStatus.closed
    tender_service.start_evaluation(db, owner, project)
    assert project.status == ProjectStatus.under_evaluation


def test_closing_a_tender_that_is_not_open_is_refused(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.draft)
    with pytest.raises(TenderError) as excinfo:
        tender_service.close(db, owner, project)
    assert excinfo.value.code == "bad_state"


def test_no_award_needs_a_closed_or_under_evaluation_tender(db):
    owner = _owner(db)
    open_project = _project(db, owner, status=ProjectStatus.open)
    with pytest.raises(TenderError):
        tender_service.mark_no_award(db, owner, open_project)

    evaluating = _project(db, owner, status=ProjectStatus.under_evaluation)
    tender_service.mark_no_award(db, owner, evaluating)
    assert evaluating.status == ProjectStatus.no_award


def test_cancel_is_refused_once_a_tender_is_awarded(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.awarded)
    with pytest.raises(TenderError):
        tender_service.cancel(db, owner, project)


def test_cancel_moves_a_draft_to_canceled(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.draft)
    tender_service.cancel(db, owner, project)
    assert project.status == ProjectStatus.canceled


# --- which actions each state offers ------------------------------------------


@pytest.mark.parametrize(
    "status, expected",
    [
        (ProjectStatus.draft, {"details", "edit", "publish", "cancel"}),
        (ProjectStatus.open, {"details", "edit", "close", "cancel", "offers", "quotations"}),
        (ProjectStatus.closed, {"details", "edit", "start_evaluation", "no_award", "cancel", "offers", "quotations"}),
        (ProjectStatus.under_evaluation, {"details", "edit", "no_award", "cancel", "offers", "quotations"}),
        (ProjectStatus.awarded, {"details", "offers", "quotations"}),
        (ProjectStatus.canceled, {"details", "offers", "quotations"}),
    ],
)
def test_allowed_actions_follow_the_state(db, status, expected):
    owner = _owner(db)
    project = _project(db, owner, status=status)
    assert set(tender_service.allowed_actions(project)) == expected


# --- sealed-bid confidentiality -------------------------------------------------


def test_a_sealed_open_tender_hides_names_and_amounts_and_orders_by_submission(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open, tender_type=TenderType.sealed)
    cheap = _contractor(db, name="Cheap Co", email="cheap@example.com")
    dear = _contractor(db, name="Dear Co", email="dear@example.com")
    _offer(db, project, dear, 900, created=NOW - timedelta(hours=2))
    _offer(db, project, cheap, 100, created=NOW - timedelta(hours=1))

    view = tender_service.received_offers(db, owner, project)

    assert view["sealed"] is True
    serialised = repr(view)
    assert "Cheap Co" not in serialised and "Dear Co" not in serialised
    assert "100" not in serialised and "900" not in serialised
    # The earlier bid is listed first, so order can't reveal the price ranking.
    assert view["rows"][0]["label"] == "Offer 1"
    assert view["rows"][0]["amount"] is None


def test_a_sealed_tender_reveals_amounts_once_it_is_closed(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.closed, tender_type=TenderType.sealed)
    cheap = _contractor(db, name="Cheap Co", email="cheap@example.com")
    dear = _contractor(db, name="Dear Co", email="dear@example.com")
    _offer(db, project, dear, 900)
    _offer(db, project, cheap, 100)

    view = tender_service.received_offers(db, owner, project)

    assert view["sealed"] is False
    assert [row["company"] for row in view["rows"]] == ["Cheap Co", "Dear Co"]


def test_an_owner_visible_tender_shows_companies_and_amounts_lowest_first(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.open, tender_type=TenderType.owner_visible)
    a = _contractor(db, name="A Co", email="a@example.com")
    b = _contractor(db, name="B Co", email="b@example.com")
    _offer(db, project, a, 500)
    _offer(db, project, b, 300)

    rows = tender_service.received_offers(db, owner, project)["rows"]

    assert [row["company"] for row in rows] == ["B Co", "A Co"]
    assert rows[0]["amount"] == 300.0


def test_admin_suspended_offers_are_never_shown_to_the_owner(db):
    owner = _owner(db)
    project = _project(db, owner, status=ProjectStatus.closed, tender_type=TenderType.owner_visible)
    visible = _contractor(db, name="Visible Co", email="v@example.com")
    hidden = _contractor(db, name="Hidden Co", email="h@example.com")
    _offer(db, project, visible, 300)
    _offer(db, project, hidden, 100, suspended=True)

    rows = tender_service.received_offers(db, owner, project)["rows"]

    assert [row["company"] for row in rows] == ["Visible Co"]


# --- deadlines and time zones ---------------------------------------------------


def test_a_local_kuwait_deadline_is_stored_as_utc():
    deadline = tender_service.parse_local_deadline("31-12-2026 14:00")
    assert deadline == datetime(2026, 12, 31, 11, 0)


def test_a_deadline_in_the_wrong_format_is_refused():
    with pytest.raises(TenderError) as excinfo:
        tender_service.parse_local_deadline("31/12/2026 2pm")
    assert excinfo.value.code == "invalid"


def test_a_deadline_round_trips_through_the_local_display():
    stored = datetime(2026, 12, 31, 11, 0)
    assert tender_service.format_local_deadline(stored) == "31-12-2026 14:00"


def test_an_unset_deadline_displays_as_not_set():
    assert tender_service.format_local_deadline(None) == "not set"
