"""Owner WhatsApp journeys, driven through the encrypted Flow endpoint from the dashboard the owner opens.

Every request carries the tender id it acts on, and each one is checked for ownership. A tender
that belongs to someone else is never reachable through these screens.
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.contractor import ContractorProfile
from app.models.enums import OfferStatus, ProjectStatus, TenderType, UserRole, VerificationStatus
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.project_amendment import ProjectAmendment
from app.models.user import User
from app.models.whatsapp import WhatsAppIdentity
from app.routers import whatsapp as whatsapp_router
from app.services.whatsapp_identity import get_or_create_identity
from app.services.whatsapp_routing import install_whatsapp_handlers
from whatsapp_helpers import RecordingSender, enable_whatsapp, flow_request, message_envelope, sign, text_message

FUTURE_LOCAL = (datetime.utcnow() + timedelta(days=20)).strftime("%Y-%m-%d %H:%M")
NOW = datetime.utcnow()


@pytest.fixture(autouse=True)
def _handlers():
    install_whatsapp_handlers()
    yield


def _owner(db, wa_id, *, verified=True, email=None):
    user = User(email=email, password_hash=None, role=UserRole.owner, full_name="Layla Al-Sabah", phone=f"+{wa_id}")
    db.add(user)
    db.flush()
    db.add(OwnerProfile(user_id=user.id, verification_status=VerificationStatus.approved if verified else VerificationStatus.incomplete))
    identity = get_or_create_identity(db, wa_id, now=NOW)
    identity.user_id = user.id
    identity.role = "owner"
    db.commit()
    return user


def _open_dashboard(client, monkeypatch, sender, wa_id, tag) -> str:
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    raw = json.dumps(message_envelope(text_message(f"wamid.DASH{tag}", wa_id, "utender"))).encode()
    client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})
    return sender.flows()[-1]["flow_token"]


def _send(client, public_pem, token, screen, data, action="data_exchange"):
    return flow_request(client, public_pem, token=token, action=action, screen=screen, data=data)[0]


def _fresh(db, project_id):
    """The endpoint commits in its own session, so drop this session's cached copy before reading."""
    db.expire_all()
    return db.get(Project, project_id)


def _project(db, owner, *, status=ProjectStatus.open, title="Villa renovation", tender_type=TenderType.owner_visible, deadline=None):
    if deadline is None and status != ProjectStatus.draft:
        deadline = NOW + timedelta(days=10)
    project = Project(owner_id=owner.id, title=title, address="Block 3, Salmiya", trade="Civil works", bid_deadline=deadline, status=status, tender_type=tender_type)
    db.add(project)
    db.commit()
    return project


@pytest.fixture
def setup(client, monkeypatch, db):
    """An approved owner with an open dashboard, plus a second owner who must stay invisible."""
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    owner = _owner(db, "96511110001")
    stranger = _owner(db, "96511110002")
    token = _open_dashboard(client, monkeypatch, sender, "96511110001", "A")
    return {"client": client, "pem": public_pem, "owner": owner, "stranger": stranger, "token": token, "db": db}


# --- entering the journeys -----------------------------------------------------


def test_an_unverified_owner_can_open_the_form_and_reach_review_on_whatsapp(client, monkeypatch, db):
    """Verification is a web rule. A WhatsApp-registered owner is not checked again."""
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    _owner(db, "96511110003", verified=False)
    token = _open_dashboard(client, monkeypatch, sender, "96511110003", "U")

    form = _send(client, public_pem, token, "MENU", {"choice": "create_tender"})
    assert form["screen"] == "CREATE_TENDER"

    review = _send(client, public_pem, token, "CREATE_TENDER", {"title": "Villa", "address": "Block 3"})
    assert review["screen"] == "REVIEW"
    assert db.query(Project).count() == 1


def test_the_web_service_still_requires_a_verified_owner(db):
    from app.services.tender_service import TenderError, TenderFields, create_draft

    owner = _owner(db, "96511110004", verified=False)

    with pytest.raises(TenderError) as refused:
        create_draft(db, owner, TenderFields(title="Villa"))
    assert refused.value.code == "not_verified"


def test_create_tender_opens_a_blank_form(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "MENU", {"choice": "create_tender"})
    assert reply["screen"] == "CREATE_TENDER"
    assert reply["data"]["tender_id"] == ""


# --- create and review ---------------------------------------------------------


def test_a_title_alone_is_saved_as_a_draft_and_reaches_review(setup):
    db = setup["db"]
    reply = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa renovation", "tender_type": "owner_visible"})

    assert reply["screen"] == "REVIEW"
    project = db.scalar(select(Project).where(Project.owner_id == setup["owner"].id))
    assert project.status == ProjectStatus.draft
    assert project.bid_deadline is None
    assert reply["data"]["tender_id"] == project.id


def test_a_full_tender_can_be_published_from_review(setup):
    db = setup["db"]
    reply = _send(
        setup["client"], setup["pem"], setup["token"], "CREATE_TENDER",
        {"title": "Villa renovation", "address": "Block 3", "trade": "Civil works", "description": "Ground floor",
         "bid_deadline": FUTURE_LOCAL, "tender_type": "sealed"},
    )
    tender_id = reply["data"]["tender_id"]

    done = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "option": "publish"})

    assert done["screen"] == "DONE"
    assert "published" in done["data"]["message"]
    project = _fresh(db, tender_id)
    assert project.status == ProjectStatus.open
    assert project.tender_type == TenderType.sealed
    assert project.bid_deadline > NOW


def test_publishing_without_a_deadline_stays_on_review_with_a_message(setup):
    db = setup["db"]
    reply = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "address": "Block 3"})
    tender_id = reply["data"]["tender_id"]

    again = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "option": "publish"})

    assert again["screen"] == "REVIEW"
    assert "deadline" in again["data"]["error_message"].lower()
    assert _fresh(db, tender_id).status == ProjectStatus.draft


def test_a_deadline_typed_wrongly_is_refused_on_the_form(setup):
    db = setup["db"]
    reply = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "bid_deadline": "next Friday"})

    assert reply["screen"] == "CREATE_TENDER"
    assert "YYYY-MM-DD HH:MM" in reply["data"]["error_message"]
    assert db.query(Project).count() == 0


def test_a_blank_title_is_refused_on_the_form(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "  "})
    assert reply["screen"] == "CREATE_TENDER"
    assert reply["data"]["error_message"]


def test_a_trade_outside_the_list_is_refused(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "trade": "Astrology"})
    assert reply["screen"] == "CREATE_TENDER"
    assert "trade" in reply["data"]["error_message"].lower()


def test_a_tender_saved_at_the_form_stays_a_draft_until_published(setup):
    db = setup["db"]
    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa"})["data"]["tender_id"]

    assert _fresh(db, tender_id).status == ProjectStatus.draft


def test_review_offers_no_edit_because_the_back_arrow_returns_to_the_form(setup):
    """Meta only accepts forward routes, so REVIEW cannot send the user back to CREATE_TENDER."""
    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "address": "Block 3"})["data"]["tender_id"]

    review = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "option": "edit"})

    assert review["screen"] == "REVIEW"
    assert review["data"]["error_message"] == "Tap Publish now to publish this tender."
    assert "Title: Villa" in review["data"]["summary"]
    assert "edit" not in {option["id"] for option in _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "option": "publish"})["data"].get("actions", [])}


def test_editing_an_existing_draft_updates_it_rather_than_creating_another(setup):
    db = setup["db"]
    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa"})["data"]["tender_id"]

    _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"tender_id": tender_id, "title": "Villa v2"})

    assert db.query(Project).count() == 1
    assert _fresh(db, tender_id).title == "Villa v2"


# --- my tenders and details -------------------------------------------------------


def test_my_tenders_lists_only_the_owners_own_tenders(setup):
    db = setup["db"]
    mine = _project(db, setup["owner"], status=ProjectStatus.open)
    theirs = _project(db, setup["stranger"], status=ProjectStatus.open, title="Not yours")

    reply = _send(setup["client"], setup["pem"], setup["token"], "MENU", {"choice": "my_tenders"})

    ids = [row["id"] for row in reply["data"]["tenders"]]
    assert mine.id in ids
    assert theirs.id not in ids


def test_a_tender_of_another_owner_cannot_be_opened(setup):
    db = setup["db"]
    theirs = _project(db, setup["stranger"], status=ProjectStatus.open, title="Not yours")

    reply = _send(setup["client"], setup["pem"], setup["token"], "MY_TENDERS", {"tender_id": theirs.id})

    assert reply["screen"] == "DONE"
    assert "no longer available" in reply["data"]["message"]
    assert theirs.title not in json.dumps(reply)


def test_a_tender_id_that_does_not_exist_gets_the_same_answer(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "MY_TENDERS", {"tender_id": "made-up-id"})
    assert reply["screen"] == "DONE"
    assert "no longer available" in reply["data"]["message"]


def test_details_show_only_the_actions_the_state_allows(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open)

    reply = _send(setup["client"], setup["pem"], setup["token"], "MY_TENDERS", {"tender_id": project.id})

    action_ids = [a["id"] for a in reply["data"]["actions"]]
    assert "close" in action_ids and "edit" in action_ids and "cancel" in action_ids
    assert "publish" not in action_ids and "start_evaluation" not in action_ids


def test_an_action_the_state_does_not_allow_is_refused(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open)

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "publish"})

    assert reply["screen"] == "TENDER_DETAILS"
    assert "isn't available" in reply["data"]["error_message"]
    assert _fresh(db, project.id).status == ProjectStatus.open


def test_details_show_the_status_deadline_and_offer_count(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open)

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "details"})

    assert "Open for bids" in reply["data"]["details"]
    assert "Offers received: 0" in reply["data"]["details"]
    assert "Bid deadline:" in reply["data"]["details"]


def test_a_draft_offers_publish_and_edit_but_not_close(setup):
    db = setup["db"]
    draft = _project(db, setup["owner"], status=ProjectStatus.draft)

    reply = _send(setup["client"], setup["pem"], setup["token"], "MY_TENDERS", {"tender_id": draft.id})
    action_ids = [a["id"] for a in reply["data"]["actions"]]

    assert "publish" in action_ids and "edit" in action_ids
    assert "close" not in action_ids


def test_edit_on_a_draft_opens_the_create_form(setup):
    db = setup["db"]
    draft = _project(db, setup["owner"], status=ProjectStatus.draft, title="Half-written")

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": draft.id, "action": "edit"})

    assert reply["screen"] == "CREATE_TENDER"
    assert reply["data"]["title"] == "Half-written"


# --- amend -------------------------------------------------------------------------


def test_amend_on_an_open_tender_records_an_amendment(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open)

    form = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "edit"})
    assert form["screen"] == "AMEND"
    assert form["data"]["title"] == "Villa renovation"

    done = _send(
        setup["client"], setup["pem"], setup["token"], "AMEND",
        {"tender_id": project.id, "title": "Villa renovation phase 2", "description": "", "trade": "Civil works",
         "bid_deadline": form["data"]["bid_deadline"], "reason": "Scope change"},
    )

    assert done["screen"] == "DONE"
    amendment = db.scalar(select(ProjectAmendment).where(ProjectAmendment.project_id == project.id))
    assert amendment.changed_fields == "title"
    assert amendment.reason == "Scope change"


def test_amend_with_nothing_changed_says_so(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open)
    form = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "edit"})

    reply = _send(
        setup["client"], setup["pem"], setup["token"], "AMEND",
        {"tender_id": project.id, "title": "Villa renovation", "description": "", "trade": "Civil works",
         "bid_deadline": form["data"]["bid_deadline"], "reason": ""},
    )

    assert reply["screen"] == "AMEND"
    assert reply["data"]["error_message"] == "No changes were provided."
    assert db.query(ProjectAmendment).count() == 0


def test_amend_cannot_move_the_deadline_earlier_after_bids(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open)
    project.tender_type_locked = True
    db.commit()
    earlier = (NOW + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")

    reply = _send(
        setup["client"], setup["pem"], setup["token"], "AMEND",
        {"tender_id": project.id, "title": "Villa renovation", "bid_deadline": earlier},
    )

    assert reply["screen"] == "AMEND"
    assert "earlier" in reply["data"]["error_message"]


def test_amend_of_another_owners_tender_is_refused(setup):
    db = setup["db"]
    theirs = _project(db, setup["stranger"], status=ProjectStatus.open, title="Not yours")

    reply = _send(setup["client"], setup["pem"], setup["token"], "AMEND", {"tender_id": theirs.id, "title": "Hijacked"})

    assert reply["screen"] == "DONE"
    assert _fresh(db, theirs.id).title == "Not yours"


# --- lifecycle actions ------------------------------------------------------------


def test_close_from_the_details_screen(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open)

    done = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "close"})

    assert done["screen"] == "DONE"
    assert _fresh(db, project.id).status == ProjectStatus.closed


def test_cancel_needs_an_explicit_yes(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open)

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "cancel", "confirm": ""})

    assert reply["screen"] == "TENDER_DETAILS"
    assert "confirm" in reply["data"]["error_message"].lower()
    assert _fresh(db, project.id).status == ProjectStatus.open


def test_cancel_with_yes_cancels_the_tender(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open)

    done = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "cancel", "confirm": "yes"})

    assert done["screen"] == "DONE"
    assert _fresh(db, project.id).status == ProjectStatus.canceled


def test_no_award_needs_an_explicit_yes(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.closed)

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "no_award", "confirm": "no"})

    assert reply["screen"] == "TENDER_DETAILS"
    assert _fresh(db, project.id).status == ProjectStatus.closed


def test_start_evaluation_from_the_details_screen(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.closed)

    done = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "start_evaluation"})

    assert done["screen"] == "DONE"
    assert _fresh(db, project.id).status == ProjectStatus.under_evaluation


# --- received offers and sealed bids -------------------------------------------


def _bidder(db, wa_name, email):
    user = User(email=email, password_hash="x", role=UserRole.contractor, full_name="Omar", email_verified=True)
    db.add(user)
    db.flush()
    db.add(ContractorProfile(user_id=user.id, company_name=wa_name, verification_status=VerificationStatus.approved))
    db.commit()
    return user


def _bid(db, project, bidder, amount):
    db.add(Offer(project_id=project.id, contractor_id=bidder.id, amount=Decimal(str(amount)), timeline_estimate="6 months", status=OfferStatus.submitted))
    db.commit()


def test_a_sealed_tender_shows_offer_times_but_no_names_or_amounts(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open, tender_type=TenderType.sealed)
    _bid(db, project, _bidder(db, "Secret Builders", "s1@example.com"), 123456)
    _bid(db, project, _bidder(db, "Quiet Co", "s2@example.com"), 98765)

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "offers"}, )

    assert reply["screen"] == "OFFERS"
    text = reply["data"]["offers"]
    assert "Offer 1" in text and "Offer 2" in text
    assert "Secret Builders" not in text and "Quiet Co" not in text
    assert "123456" not in text and "98,765" not in text and "98765" not in text


def test_an_owner_visible_tender_shows_companies_and_amounts(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.open, tender_type=TenderType.owner_visible)
    _bid(db, project, _bidder(db, "Open Books Ltd", "o1@example.com"), 250000)

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id, "action": "offers"})

    assert "Open Books Ltd" in reply["data"]["offers"]
    assert "250,000.00" in reply["data"]["offers"]


def test_the_offers_screen_never_shows_another_owners_bids(setup):
    db = setup["db"]
    theirs = _project(db, setup["stranger"], status=ProjectStatus.open, tender_type=TenderType.owner_visible)
    _bid(db, theirs, _bidder(db, "Private Bid Co", "p1@example.com"), 4242)

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": theirs.id, "action": "offers"})

    assert "Private Bid Co" not in json.dumps(reply)
    assert "4,242" not in json.dumps(reply)


def test_received_offers_from_the_menu_picks_a_tender_first(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "MENU", {"choice": "received_offers"})
    assert reply["screen"] == "MY_TENDERS"
    assert "Pick a tender" in reply["data"]["heading"]


# --- roles ---------------------------------------------------------------------------


def test_a_contractor_cannot_reach_the_owner_screens(client, monkeypatch, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    bidder = _bidder(db, "Haddad Builders", "con-flow@example.com")
    bidder.phone = "+96522224444"
    db.commit()
    identity = get_or_create_identity(db, "96522224444", now=NOW)
    identity.user_id = bidder.id
    identity.role = "contractor"
    db.commit()
    token = _open_dashboard(client, monkeypatch, sender, "96522224444", "C")

    reply = _send(client, public_pem, token, "CREATE_TENDER", {"title": "Sneaky"})

    # A contractor is answered with an error, not the owner screen, and nothing is created.
    assert "error_message" in reply["data"]
    assert db.query(Project).count() == 0


def _epoch_ms_for_utc_midnight(day: datetime) -> str:
    midnight = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return str(int(midnight.replace(tzinfo=timezone.utc).timestamp() * 1000))


def test_the_calendar_date_and_time_set_the_bid_deadline_in_utc(setup):
    """Kuwait 09:00 on 15 March 2030 is 06:00 UTC."""
    db = setup["db"]
    date_ms = _epoch_ms_for_utc_midnight(datetime(2030, 3, 15))

    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {
        "title": "Villa", "address": "Block 3", "bid_deadline_date": date_ms, "bid_deadline_time": "09:00",
    })["data"]["tender_id"]

    assert _fresh(db, tender_id).bid_deadline == datetime(2030, 3, 15, 6, 0)


def test_the_calendar_accepts_a_plain_date_too(setup):
    db = setup["db"]

    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {
        "title": "Villa", "address": "Block 3", "bid_deadline_date": "2030-03-15", "bid_deadline_time": "09:00",
    })["data"]["tender_id"]

    assert _fresh(db, tender_id).bid_deadline == datetime(2030, 3, 15, 6, 0)


def test_a_date_without_a_time_is_refused_with_a_message(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {
        "title": "Villa", "address": "Block 3", "bid_deadline_date": "2030-03-15",
    })

    assert reply["screen"] == "CREATE_TENDER"
    assert "both the date and the time" in reply["data"]["error_message"]
