"""Contractor WhatsApp journeys, driven through the encrypted Flow endpoint from the dashboard the contractor opens.

The three gates are checked here too: verification (browse, withdraw), payment (drawings, bidding), and
tender visibility (drafts and suspended tenders never appear). Contractors only ever see their own offers.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.award_record import AwardRecord
from app.models.contractor import ContractorProfile
from app.models.enums import OfferStatus, ProjectStatus, SubscriptionStatus, TenderType, UserRole, VerificationStatus
from app.models.offer import Offer, OfferRevision
from app.models.owner import OwnerProfile
from app.models.project import Project, ProjectDrawing
from app.models.user import User
from app.models.whatsapp import WhatsAppIdentity, WhatsAppOutbox
from app.routers import whatsapp as whatsapp_router
from app.services.storage import get_storage
from app.services.whatsapp_identity import get_or_create_identity
from app.services.whatsapp_outbox import dispatch_due
from app.services.whatsapp_routing import install_whatsapp_handlers
from whatsapp_helpers import RecordingSender, enable_whatsapp, flow_request, message_envelope, sign, text_message

NOW = datetime.utcnow()
FUTURE = NOW + timedelta(days=10)


@pytest.fixture(autouse=True)
def _handlers():
    install_whatsapp_handlers()
    yield


def _contractor(db, wa_id, *, name="Haddad Builders", verified=True, paid=True, suspended=False):
    user = User(email=None, password_hash=None, role=UserRole.contractor, full_name="Omar Haddad", phone=f"+{wa_id}")
    db.add(user)
    db.flush()
    db.add(
        ContractorProfile(
            user_id=user.id,
            company_name=name,
            primary_trade="Electrical",
            verification_status=VerificationStatus.approved if verified else VerificationStatus.incomplete,
            is_suspended=suspended,
            subscription_status=SubscriptionStatus.active if paid else SubscriptionStatus.not_started,
        )
    )
    identity = get_or_create_identity(db, wa_id, now=NOW)
    identity.user_id = user.id
    identity.role = "contractor"
    db.commit()
    return user


def _owner(db, email="owner-c@example.com"):
    user = User(email=email, password_hash="x", role=UserRole.owner, full_name="Layla", email_verified=True)
    db.add(user)
    db.flush()
    db.add(OwnerProfile(user_id=user.id))
    db.commit()
    return user


def _project(db, owner, *, title="Villa renovation", status=ProjectStatus.open, trade="Electrical", tender_type=TenderType.owner_visible, deadline=FUTURE, suspended=False, address="Block 3, Salmiya"):
    project = Project(
        owner_id=owner.id, title=title, address=address, trade=trade, description="Ground floor works",
        bid_deadline=deadline, status=status, tender_type=tender_type, is_suspended=suspended,
    )
    db.add(project)
    db.commit()
    return project


def _open_dashboard(client, monkeypatch, sender, wa_id, tag) -> str:
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    raw = json.dumps(message_envelope(text_message(f"wamid.CD{tag}", wa_id, "menu"))).encode()
    client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})
    return sender.flows()[-1]["flow_token"]


def _send(client, public_pem, token, screen, data, action="data_exchange"):
    return flow_request(client, public_pem, token=token, action=action, screen=screen, data=data)[0]


@pytest.fixture
def setup(client, monkeypatch, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    me = _contractor(db, "96522220001", name="Haddad Builders")
    token = _open_dashboard(client, monkeypatch, sender, "96522220001", "A")
    owner = _owner(db)
    return {"client": client, "pem": public_pem, "me": me, "owner": owner, "token": token, "db": db, "sender": sender, "monkeypatch": monkeypatch}


def _fresh(db, cls, key):
    db.expire_all()
    return db.get(cls, key)


# --- gates ----------------------------------------------------------------------


def test_an_unverified_contractor_is_turned_back_from_browsing(client, monkeypatch, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    _contractor(db, "96522220002", verified=False)
    token = _open_dashboard(client, monkeypatch, sender, "96522220002", "U")

    reply = _send(client, public_pem, token, "MENU", {"choice": "browse_projects"})

    assert reply["screen"] == "MENU"
    assert "verified" in reply["data"]["error_message"]


def test_a_verified_but_unpaid_contractor_can_browse_but_not_bid(setup):
    db = setup["db"]
    _project(db, setup["owner"])
    unpaid = _contractor(db, "96522220003", name="No Pay Co", paid=False)
    token = _open_dashboard(setup["client"], setup["monkeypatch"], setup["sender"], "96522220003", "P")

    browse = _send(setup["client"], setup["pem"], token, "MENU", {"choice": "browse_projects"})
    assert browse["screen"] == "PROJECT_LIST"
    assert browse["data"]["projects"]

    project_id = browse["data"]["projects"][0]["id"]
    details = _send(setup["client"], setup["pem"], token, "PROJECT_LIST", {"project_id": project_id})
    assert details["screen"] == "MENU"
    assert "subscription" in details["data"]["error_message"].lower()
    assert "Villa renovation" not in json.dumps(details)

    refused = _send(setup["client"], setup["pem"], token, "PROJECT_DETAILS", {"project_id": project_id, "action": "submit"})
    assert refused["screen"] == "MENU"
    assert "subscription" in refused["data"]["error_message"].lower()
    assert db.query(Offer).filter(Offer.contractor_id == unpaid.id).count() == 0


def test_a_verified_but_unpaid_contractor_cannot_see_drawings(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    unpaid = _contractor(db, "96522220004", name="No Pay Two", paid=False)
    token = _open_dashboard(setup["client"], setup["monkeypatch"], setup["sender"], "96522220004", "Q")

    reply = _send(setup["client"], setup["pem"], token, "PROJECT_DETAILS", {"project_id": project.id, "action": "drawings"})

    assert reply["screen"] == "MENU"
    assert "subscription" in reply["data"]["error_message"].lower()


def test_an_unverified_contractor_cannot_search(client, monkeypatch, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    _contractor(db, "96522220005", verified=False)
    token = _open_dashboard(client, monkeypatch, sender, "96522220005", "S")

    reply = _send(client, public_pem, token, "MENU", {"choice": "search_projects"})

    assert reply["screen"] == "MENU"


# --- browse, search and filter ---------------------------------------------------


def test_browse_lists_only_open_unsuspended_tenders(setup):
    db = setup["db"]
    visible = _project(db, setup["owner"], title="Visible tender")
    _project(db, setup["owner"], title="Draft tender", status=ProjectStatus.draft, deadline=None)
    _project(db, setup["owner"], title="Closed tender", status=ProjectStatus.closed)
    _project(db, setup["owner"], title="Suspended tender", suspended=True)

    reply = _send(setup["client"], setup["pem"], setup["token"], "MENU", {"choice": "browse_projects"})

    titles = [p["title"] for p in reply["data"]["projects"]]
    ids = [p["id"] for p in reply["data"]["projects"]]
    assert visible.id in ids
    assert all("Draft" not in t and "Closed" not in t and "Suspended" not in t for t in titles)


def test_search_matches_title_and_filters_by_trade(setup):
    db = setup["db"]
    _project(db, setup["owner"], title="Kitchen fit-out", trade="Plumbing")
    _project(db, setup["owner"], title="Wiring upgrade", trade="Electrical")

    reply = _send(setup["client"], setup["pem"], setup["token"], "SEARCH", {"search": "kitchen", "trade": "Any", "sort": "deadline"})
    assert [p["title"] for p in reply["data"]["projects"]] == ["Kitchen fit-out"]

    reply = _send(setup["client"], setup["pem"], setup["token"], "SEARCH", {"search": "", "trade": "Electrical", "sort": "deadline"})
    assert [p["title"] for p in reply["data"]["projects"]] == ["Wiring upgrade"]


def test_search_with_no_match_says_so(setup):
    reply = _send(setup["client"], setup["pem"], setup["token"], "SEARCH", {"search": "zzz-nothing", "trade": "Any", "sort": "deadline"})
    assert reply["screen"] == "PROJECT_LIST"
    assert reply["data"]["projects"] == []
    assert "No open projects match" in reply["data"]["empty_message"]


def test_search_sorts_newest_first(setup):
    db = setup["db"]
    older = _project(db, setup["owner"], title="Older one")
    older.created_at = NOW - timedelta(days=5)
    newer = _project(db, setup["owner"], title="Newer one")
    newer.created_at = NOW
    db.commit()

    reply = _send(setup["client"], setup["pem"], setup["token"], "SEARCH", {"search": "one", "trade": "Any", "sort": "newest"})

    assert [p["title"] for p in reply["data"]["projects"]] == ["Newer one", "Older one"]


# --- details and submitting -------------------------------------------------------


def test_details_offer_submit_for_a_paid_contractor_on_an_open_tender(setup):
    project = _project(setup["db"], setup["owner"])
    reply = _send(setup["client"], setup["pem"], setup["token"], "PROJECT_LIST", {"project_id": project.id})
    assert reply["screen"] == "PROJECT_DETAILS"
    assert "submit" in [a["id"] for a in reply["data"]["actions"]]


def test_submitting_an_offer_goes_through_review_and_is_saved(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    form = _send(setup["client"], setup["pem"], setup["token"], "PROJECT_DETAILS", {"project_id": project.id, "action": "submit"})
    assert form["screen"] == "SUBMIT_OFFER"

    review = _send(setup["client"], setup["pem"], setup["token"], "SUBMIT_OFFER", {"project_id": project.id, "amount": "12,500", "timeline": "6 months", "message": "Ready to start"})
    assert review["screen"] == "REVIEW_OFFER"
    assert "12,500.00" in review["data"]["summary"]

    done = _send(setup["client"], setup["pem"], setup["token"], "REVIEW_OFFER", {"project_id": project.id, "amount": "12500", "timeline": "6 months", "message": "Ready to start", "decision": "submit"})
    assert done["screen"] == "DONE"
    offer = db.scalar(select(Offer).where(Offer.project_id == project.id))
    assert offer.amount == Decimal("12500")
    assert offer.status == OfferStatus.submitted


@pytest.mark.parametrize("amount", ["abc", "0", "-5", ""])
def test_a_bad_amount_is_refused_on_the_form(setup, amount):
    db = setup["db"]
    project = _project(db, setup["owner"])
    reply = _send(setup["client"], setup["pem"], setup["token"], "SUBMIT_OFFER", {"project_id": project.id, "amount": amount})
    assert reply["screen"] == "SUBMIT_OFFER"
    assert reply["data"]["error_message"]
    assert db.query(Offer).count() == 0


def test_changing_the_offer_on_review_returns_to_the_form_with_the_values(setup):
    project = _project(setup["db"], setup["owner"])
    reply = _send(setup["client"], setup["pem"], setup["token"], "REVIEW_OFFER", {"project_id": project.id, "amount": "900", "timeline": "2 months", "message": "x", "decision": "edit"})
    assert reply["screen"] == "SUBMIT_OFFER"
    assert reply["data"]["amount"] == "900"


def test_a_closed_tender_cannot_be_bid_on(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], status=ProjectStatus.closed)
    reply = _send(setup["client"], setup["pem"], setup["token"], "PROJECT_DETAILS", {"project_id": project.id, "action": "submit"})
    assert reply["screen"] == "PROJECT_DETAILS"
    assert "closed" in reply["data"]["error_message"].lower()
    assert db.query(Offer).count() == 0


# --- revise, history and withdraw ---------------------------------------------------


def _bid(setup, project, amount="10000"):
    _send(setup["client"], setup["pem"], setup["token"], "PROJECT_DETAILS", {"project_id": project.id, "action": "submit"})
    _send(setup["client"], setup["pem"], setup["token"], "REVIEW_OFFER", {"project_id": project.id, "amount": amount, "timeline": "4 months", "message": "first", "decision": "submit"})


def test_a_revision_keeps_the_earlier_version_in_history(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    _bid(setup, project, "10000")

    _send(setup["client"], setup["pem"], setup["token"], "PROJECT_DETAILS", {"project_id": project.id, "action": "revise"})
    _send(setup["client"], setup["pem"], setup["token"], "REVIEW_OFFER", {"project_id": project.id, "amount": "9000", "timeline": "3 months", "message": "better", "decision": "submit"})

    offer = db.scalar(select(Offer).where(Offer.project_id == project.id))
    assert offer.amount == Decimal("9000")
    revisions = db.scalars(select(OfferRevision).where(OfferRevision.offer_id == offer.id)).all()
    assert [r.amount for r in revisions] == [Decimal("10000")]

    history = _send(setup["client"], setup["pem"], setup["token"], "PROJECT_DETAILS", {"project_id": project.id, "action": "history"})
    assert history["screen"] == "OFFER_HISTORY"
    assert "10,000.00" in history["data"]["body"]


def test_withdrawing_needs_a_yes_and_then_marks_the_offer_withdrawn(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    _bid(setup, project)

    refused = _send(setup["client"], setup["pem"], setup["token"], "OFFER_DETAILS", {"project_id": project.id, "action": "withdraw", "confirm": ""})
    assert refused["screen"] == "OFFER_DETAILS"
    assert db.scalar(select(Offer).where(Offer.project_id == project.id)).status == OfferStatus.submitted

    done = _send(setup["client"], setup["pem"], setup["token"], "OFFER_DETAILS", {"project_id": project.id, "action": "withdraw", "confirm": "yes"})
    assert done["screen"] == "DONE"
    db.expire_all()
    offer = db.scalar(select(Offer).where(Offer.project_id == project.id))
    assert offer.status == OfferStatus.withdrawn
    assert db.query(OfferRevision).filter(OfferRevision.offer_id == offer.id).count() == 1


def test_withdrawing_twice_is_refused(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    _bid(setup, project)
    _send(setup["client"], setup["pem"], setup["token"], "OFFER_DETAILS", {"project_id": project.id, "action": "withdraw", "confirm": "yes"})

    again = _send(setup["client"], setup["pem"], setup["token"], "OFFER_DETAILS", {"project_id": project.id, "action": "withdraw", "confirm": "yes"})

    assert again["screen"] == "OFFER_DETAILS"
    assert "already been withdrawn" in again["data"]["error_message"]


def test_a_withdrawn_offer_can_be_submitted_again(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    _bid(setup, project)
    _send(setup["client"], setup["pem"], setup["token"], "OFFER_DETAILS", {"project_id": project.id, "action": "withdraw", "confirm": "yes"})

    _send(setup["client"], setup["pem"], setup["token"], "REVIEW_OFFER", {"project_id": project.id, "amount": "8000", "timeline": "", "message": "back", "decision": "submit"})

    db.expire_all()
    assert db.scalar(select(Offer).where(Offer.project_id == project.id)).status == OfferStatus.submitted


def test_a_closed_tender_offers_no_revise_action(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    _bid(setup, project)
    project.status = ProjectStatus.closed
    db.commit()

    reply = _send(setup["client"], setup["pem"], setup["token"], "MY_OFFERS", {"project_id": project.id})

    assert reply["screen"] == "OFFER_DETAILS"
    assert "revise" not in [a["id"] for a in reply["data"]["actions"]]


# --- my offers: own only -----------------------------------------------------------


def test_my_offers_shows_only_my_offers(setup):
    db = setup["db"]
    mine = _project(db, setup["owner"], title="My bid project")
    other_project = _project(db, setup["owner"], title="Someone else's bid project")
    rival = _contractor(db, "96522220009", name="Rival Builders")
    db.add(Offer(project_id=mine.id, contractor_id=setup["me"].id, amount=Decimal("5000"), status=OfferStatus.submitted))
    db.add(Offer(project_id=other_project.id, contractor_id=rival.id, amount=Decimal("777"), status=OfferStatus.submitted))
    db.commit()

    listing = _send(setup["client"], setup["pem"], setup["token"], "MENU", {"choice": "my_offers"})
    ids = [o["id"] for o in listing["data"]["offers"]]

    assert ids == [mine.id]
    assert "Rival Builders" not in json.dumps(listing)


def test_another_contractors_offer_cannot_be_opened(setup):
    db = setup["db"]
    theirs = _project(db, setup["owner"], title="Their project")
    rival = _contractor(db, "96522220010", name="Rival Two")
    db.add(Offer(project_id=theirs.id, contractor_id=rival.id, amount=Decimal("4444"), status=OfferStatus.submitted))
    db.commit()

    reply = _send(setup["client"], setup["pem"], setup["token"], "MY_OFFERS", {"project_id": theirs.id})

    assert reply["screen"] == "PROJECT_LIST"
    dump = json.dumps(reply)
    assert "4444" not in dump and "Rival Two" not in dump


def test_project_details_never_reveal_who_else_bid_or_how_much(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], tender_type=TenderType.owner_visible)
    rival = _contractor(db, "96522220011", name="Visible Rival")
    db.add(Offer(project_id=project.id, contractor_id=rival.id, amount=Decimal("31337"), status=OfferStatus.submitted))
    db.commit()

    reply = _send(setup["client"], setup["pem"], setup["token"], "PROJECT_LIST", {"project_id": project.id})

    dump = json.dumps(reply)
    assert "31337" not in dump and "Visible Rival" not in dump
    assert "Offers received: 1" in reply["data"]["details"]


# --- awards -------------------------------------------------------------------------


def test_my_awards_lists_only_tenders_i_won(setup):
    db = setup["db"]
    won = _project(db, setup["owner"], title="Won tender", status=ProjectStatus.awarded)
    rival = _contractor(db, "96522220012", name="Other Winner")
    lost = _project(db, setup["owner"], title="Other winner tender", status=ProjectStatus.awarded)
    my_offer = Offer(project_id=won.id, contractor_id=setup["me"].id, amount=Decimal("7000"), status=OfferStatus.approved)
    their_offer = Offer(project_id=lost.id, contractor_id=rival.id, amount=Decimal("8000"), status=OfferStatus.approved)
    db.add_all([my_offer, their_offer])
    db.flush()
    db.add(AwardRecord(project_id=won.id, offer_id=my_offer.id, contractor_id=setup["me"].id, amount=Decimal("7000"), project_revision=1, offer_revision=1, awarded_by=setup["owner"].id))
    db.add(AwardRecord(project_id=lost.id, offer_id=their_offer.id, contractor_id=rival.id, amount=Decimal("8000"), project_revision=1, offer_revision=1, awarded_by=setup["owner"].id))
    db.commit()

    reply = _send(setup["client"], setup["pem"], setup["token"], "MENU", {"choice": "my_awards"})

    assert reply["screen"] == "AWARDS"
    assert "Won tender" in reply["data"]["body"]
    assert "Other winner tender" not in reply["data"]["body"]


# --- drawings: payment gate and signed links -------------------------------------------


def test_a_paid_contractor_gets_signed_drawing_links_in_their_own_chat(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    storage = get_storage()
    path = f"{project.id}/plan-v1.pdf"
    storage.save("project-drawings", path, b"%PDF-1.4 plan", "application/pdf")
    db.add(ProjectDrawing(project_id=project.id, file_path=path, file_name="plan.pdf", revision=1, is_current=True))
    db.commit()

    reply = _send(setup["client"], setup["pem"], setup["token"], "PROJECT_DETAILS", {"project_id": project.id, "action": "drawings"})
    assert reply["screen"] == "DONE"

    dispatch_due(db, setup["sender"], now=datetime.utcnow(), max_attempts=3)
    links = setup["sender"].links()
    assert len(links) == 1
    assert "/files/project-drawings/" in links[0]["url"]
    assert links[0]["to"] == "96522220001"


def test_a_tender_without_drawings_says_so(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    reply = _send(setup["client"], setup["pem"], setup["token"], "PROJECT_DETAILS", {"project_id": project.id, "action": "drawings"})
    assert reply["screen"] == "PROJECT_DETAILS"
    assert "no drawings" in reply["data"]["error_message"].lower()


def test_drawing_links_are_not_stored_after_sending(setup):
    db = setup["db"]
    project = _project(db, setup["owner"])
    path = f"{project.id}/x.pdf"
    get_storage().save("project-drawings", path, b"%PDF-1.4 x", "application/pdf")
    db.add(ProjectDrawing(project_id=project.id, file_path=path, file_name="x.pdf", revision=1, is_current=True))
    db.commit()

    _send(setup["client"], setup["pem"], setup["token"], "PROJECT_DETAILS", {"project_id": project.id, "action": "drawings"})
    dispatch_due(db, setup["sender"], now=datetime.utcnow(), max_attempts=3)

    row = db.scalar(select(WhatsAppOutbox).where(WhatsAppOutbox.kind == "cta_url"))
    assert "url" not in (row.params_json or {})


# --- visibility of suspended and draft tenders -----------------------------------------


def test_a_suspended_tender_cannot_be_opened_even_by_id(setup):
    db = setup["db"]
    project = _project(db, setup["owner"], suspended=True)
    reply = _send(setup["client"], setup["pem"], setup["token"], "PROJECT_LIST", {"project_id": project.id})
    assert reply["screen"] == "PROJECT_LIST"
    assert "no longer available" in reply["data"]["heading"]


def test_a_draft_tender_cannot_be_opened_even_by_id(setup):
    db = setup["db"]
    draft = _project(db, setup["owner"], status=ProjectStatus.draft, deadline=None, title="Secret draft")
    reply = _send(setup["client"], setup["pem"], setup["token"], "PROJECT_LIST", {"project_id": draft.id})
    assert "Secret draft" not in json.dumps(reply)
    assert "no longer available" in reply["data"]["heading"]


def test_a_suspended_contractor_loses_browsing(client, monkeypatch, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    _contractor(db, "96522220013", suspended=True)
    token = _open_dashboard(client, monkeypatch, sender, "96522220013", "X")

    reply = _send(client, public_pem, token, "MENU", {"choice": "browse_projects"})

    assert reply["screen"] == "MENU"
