"""Owner WhatsApp journeys, driven through the encrypted Flow endpoint from the dashboard the owner opens.

Every request carries the tender id it acts on, and each one is checked for ownership. A tender
that belongs to someone else is never reachable through these screens.
"""

import json
from datetime import datetime, timedelta
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
from flow_contract import check_reply
from whatsapp_helpers import RecordingSender, enable_whatsapp, flow_request, message_envelope, sign, text_message

FUTURE_LOCAL = (datetime.utcnow() + timedelta(days=20)).strftime("%d-%m-%Y %H:%M")
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
    raw = json.dumps(message_envelope(text_message(f"wamid.DASH{tag}", wa_id, "menu"))).encode()
    client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})
    return sender.flows()[-1]["flow_token"]


def _send(client, public_pem, token, screen, data, action="data_exchange"):
    reply = flow_request(client, public_pem, token=token, action=action, screen=screen, data=data)[0]
    if reply is not None:
        check_reply("owner_dashboard", reply)
    return reply


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


def test_an_unverified_owner_can_create_a_tender_from_whatsapp(client, monkeypatch, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    _owner(db, "96511110003", verified=False)
    token = _open_dashboard(client, monkeypatch, sender, "96511110003", "U")

    reply = _send(client, public_pem, token, "MENU", {"choice": "create_tender"})

    assert reply["screen"] == "CREATE_TENDER"
    assert db.query(Project).count() == 0


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

    done = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "action": "publish"})

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

    again = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "action": "publish"})

    assert again["screen"] == "REVIEW"
    assert "deadline" in again["data"]["error_message"].lower()
    assert _fresh(db, tender_id).status == ProjectStatus.draft


def test_a_deadline_typed_wrongly_is_refused_on_the_form(setup):
    db = setup["db"]
    reply = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "bid_deadline": "next Friday"})

    assert reply["screen"] == "CREATE_TENDER"
    assert "DD-MM-YYYY" in reply["data"]["error_message"]
    assert db.query(Project).count() == 0


def test_a_blank_title_is_refused_on_the_form(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "  "})
    assert reply["screen"] == "CREATE_TENDER"
    assert reply["data"]["error_message"]


def test_a_trade_outside_the_list_is_refused(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "trade": "Astrology"})
    assert reply["screen"] == "CREATE_TENDER"
    assert "trade" in reply["data"]["error_message"].lower()


def test_save_as_draft_keeps_the_tender_and_says_so(setup):
    db = setup["db"]
    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa"})["data"]["tender_id"]

    done = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "action": "save_draft"})

    assert done["screen"] == "DONE"
    assert "Draft saved" in done["data"]["message"]
    assert _fresh(db, tender_id).status == ProjectStatus.draft


def test_edit_from_review_reopens_the_form_with_the_saved_values(setup):
    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "address": "Block 3"})["data"]["tender_id"]

    form = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "action": "edit"})

    assert form["screen"] == "CREATE_TENDER"
    assert form["data"]["tender_id"] == tender_id
    assert form["data"]["title"] == "Villa"
    assert form["data"]["address"] == "Block 3"


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

    assert reply["screen"] == "MY_TENDERS"
    assert "no longer available" in reply["data"]["heading"]
    assert theirs.title not in json.dumps(reply)


def test_a_tender_id_that_does_not_exist_gets_the_same_answer(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "MY_TENDERS", {"tender_id": "made-up-id"})
    assert reply["screen"] == "MY_TENDERS"
    assert "no longer available" in reply["data"]["heading"]


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
    earlier = (NOW + timedelta(days=2)).strftime("%d-%m-%Y %H:%M")

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

    assert reply["screen"] == "MY_TENDERS"
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
    assert reply["screen"] == "DONE"
    assert "no longer available" in reply["data"]["message"]
    assert db.query(Project).count() == 0

def test_the_calendar_date_becomes_the_end_of_that_day(setup):
    from zoneinfo import ZoneInfo

    from app.config import get_settings

    zone = ZoneInfo(get_settings().tender_timezone)
    day = datetime.now(zone) + timedelta(days=20)
    midnight = datetime(day.year, day.month, day.day, tzinfo=zone)
    millis = int(midnight.timestamp() * 1000)

    _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "address": "Block 3", "bid_deadline": millis})

    project = setup["db"].query(Project).one()
    local = project.bid_deadline.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
    assert (local.year, local.month, local.day) == (day.year, day.month, day.day)
    assert (local.hour, local.minute) == (23, 59)

def test_the_calendar_may_send_an_iso_date_or_decimal_milliseconds(setup):
    from zoneinfo import ZoneInfo

    from app.config import get_settings

    zone = ZoneInfo(get_settings().tender_timezone)
    day = datetime.now(zone) + timedelta(days=25)
    midnight = datetime(day.year, day.month, day.day, tzinfo=zone)
    iso = f"{day.year:04d}-{day.month:02d}-{day.day:02d}"

    _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Iso", "address": "Block 3", "bid_deadline": iso})
    project = setup["db"].query(Project).one()
    local = project.bid_deadline.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
    assert (local.year, local.month, local.day, local.hour, local.minute) == (day.year, day.month, day.day, 23, 59)

    setup["db"].query(Project).delete()
    setup["db"].commit()
    millis = f"{int(midnight.timestamp() * 1000)}.0"
    _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Decimal", "address": "Block 3", "bid_deadline": millis})
    project = setup["db"].query(Project).one()
    local = project.bid_deadline.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
    assert (local.year, local.month, local.day) == (day.year, day.month, day.day)

def test_publishing_also_sends_the_tender_number_in_chat(setup):
    from app.models.whatsapp import WhatsAppOutbox

    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "address": "Block 3", "bid_deadline": FUTURE_LOCAL})["data"]["tender_id"]

    reply = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "next_step": "publish"})

    db = setup["db"]
    project = db.get(Project, tender_id)
    assert reply["screen"] == "DONE"
    assert project.reference_code in reply["data"]["heading"]
    rows = db.query(WhatsAppOutbox).filter(WhatsAppOutbox.dedupe_key == f"tender-number:{project.id}").all()
    assert len(rows) == 1
    assert project.reference_code in rows[0].params_json["body"]

def test_a_draft_is_not_offered_close_or_view_offers(setup):
    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "address": "Block 3"})["data"]["tender_id"]

    reply = _send(setup["client"], setup["pem"], setup["token"], "MY_TENDERS", {"tender_id": tender_id})

    ids = [action["id"] for action in reply["data"]["actions"]]
    assert "close" not in ids
    assert "offers" not in ids


def test_the_details_choice_is_read_from_next_step(setup):
    tender_id = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "address": "Block 3", "bid_deadline": FUTURE_LOCAL})["data"]["tender_id"]
    _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "next_step": "publish"})

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": tender_id, "next_step": "edit"})

    assert reply["screen"] == "AMEND"

def test_repro_edit_a_draft(setup):
    tid = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": "Villa", "address": "Block 3", "bid_deadline": FUTURE_LOCAL})["data"]["tender_id"]
    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": tid, "next_step": "edit"})
    print("EDIT SCREEN", reply["screen"], sorted(reply["data"].keys()))
    reply2 = _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"tender_id": tid, "title": "Villa v2", "address": "Block 3", "bid_deadline": FUTURE_LOCAL})
    print("SAVE", reply2["screen"])


# --- scenario matrix: every owner menu choice, status and review path -----------------


def _draft_with_deadline(setup, title="Villa"):
    return _send(setup["client"], setup["pem"], setup["token"], "CREATE_TENDER", {"title": title, "address": "Block 3", "bid_deadline": FUTURE_LOCAL})["data"]["tender_id"]


def test_every_owner_menu_choice_opens_a_screen(setup):
    expected = {"create_tender": "CREATE_TENDER", "my_tenders": "MY_TENDERS", "received_offers": "MY_TENDERS", "my_documents": "DOCUMENTS"}
    for choice, screen in expected.items():
        reply = _send(setup["client"], setup["pem"], setup["token"], "MENU", {"choice": choice})
        assert reply["screen"] == screen, (choice, reply["screen"])


@pytest.mark.parametrize("status", [ProjectStatus.draft, ProjectStatus.open, ProjectStatus.closed, ProjectStatus.under_evaluation, ProjectStatus.awarded, ProjectStatus.canceled])
def test_the_details_screen_opens_for_every_status(setup, status):
    project = _project(setup["db"], setup["owner"], status=status)

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": project.id})

    assert reply["screen"] == "TENDER_DETAILS"
    assert "publish" not in [a["id"] for a in reply["data"]["actions"]] or status == ProjectStatus.draft


def test_publish_a_draft_from_its_details(setup):
    tender_id = _draft_with_deadline(setup)

    reply = _send(setup["client"], setup["pem"], setup["token"], "TENDER_DETAILS", {"tender_id": tender_id, "next_step": "publish"})

    assert reply["screen"] == "DONE"
    project = _fresh(setup["db"], tender_id)
    assert project.status == ProjectStatus.open
    assert project.reference_code in reply["data"]["heading"]


def test_review_without_a_choice_stays_on_review_with_a_message(setup):
    tender_id = _draft_with_deadline(setup)

    reply = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id})

    assert reply["screen"] == "REVIEW"
    assert "Choose" in reply["data"]["error_message"]


def test_a_document_that_is_not_accepted_is_named_on_review(setup):
    tender_id = _draft_with_deadline(setup)
    documents = [{"file_name": "plan.exe", "cdn_url": "https://example.invalid/x", "encryption_metadata": {}}]

    reply = _send(setup["client"], setup["pem"], setup["token"], "REVIEW", {"tender_id": tender_id, "documents": documents, "next_step": "save_draft"})

    assert reply["screen"] == "REVIEW"
    assert "plan.exe" in reply["data"]["error_message"]
    assert _fresh(setup["db"], tender_id).status == ProjectStatus.draft


def test_a_long_tender_list_is_capped_at_twenty_rows(setup):
    for number in range(25):
        _project(setup["db"], setup["owner"], status=ProjectStatus.draft, title=f"Tender number {number} with a long name")

    reply = _send(setup["client"], setup["pem"], setup["token"], "MY_TENDERS", {})

    assert reply["screen"] == "MY_TENDERS"
    assert len(reply["data"]["tenders"]) == 20
