# Drafts meet the standard: every draft has a trade and a future deadline.
"""An owner edits a saved draft on WhatsApp and submits the form again. The Flow sends back every field on the
form, so these tests send the full set, for each shape a saved draft can have. Every reply is checked against
the Flow's declared screen (flow_contract), so a reply WhatsApp would show as "Something went wrong" fails here."""

import json
from pathlib import Path
from datetime import datetime, timedelta

import pytest

from app.models.enums import ProjectStatus, TenderType, UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.user import User
from app.routers import whatsapp as whatsapp_router
from app.services.whatsapp_identity import get_or_create_identity
from app.services.whatsapp_routing import install_whatsapp_handlers
from flow_contract import check_reply
from whatsapp_helpers import RecordingSender, enable_whatsapp, flow_request, message_envelope, sign, text_message

NOW = datetime.utcnow()
WA = "96511119001"


@pytest.fixture(autouse=True)
def _handlers():
    install_whatsapp_handlers()
    yield


def _owner(db):
    user = User(email=None, password_hash=None, role=UserRole.owner, full_name="Layla", phone=f"+{WA}")
    db.add(user)
    db.flush()
    db.add(OwnerProfile(user_id=user.id, verification_status=VerificationStatus.approved))
    identity = get_or_create_identity(db, WA, now=NOW)
    identity.user_id = user.id
    identity.role = "owner"
    db.commit()
    return user


def _open(client, monkeypatch, sender) -> str:
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    raw = json.dumps(message_envelope(text_message("wamid.DRAFTEDIT1", WA, "menu"))).encode()
    client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})
    return sender.flows()[-1]["flow_token"]


def _send(client, pem, token, screen, data, action="data_exchange"):
    reply = flow_request(client, pem, token=token, action=action, screen=screen, data=data)[0]
    if reply is not None:
        check_reply("owner_dashboard", reply)
    return reply


@pytest.fixture
def owner_flow(client, monkeypatch, db):
    _, pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    owner = _owner(db)
    token = _open(client, monkeypatch, sender)
    return {"client": client, "pem": pem, "token": token, "owner": owner, "db": db}


def _draft(db, owner, **fields) -> Project:
    project = Project(
        owner_id=owner.id,
        title=fields.pop("title", "Half-written villa"),
        address=fields.pop("address", "Block 3, Salmiya"),
        description=fields.pop("description", None),
        trade=fields.pop("trade", "Electrical"),
        bid_deadline=fields.pop("bid_deadline", NOW + timedelta(days=10)),
        status=ProjectStatus.draft,
        tender_type=fields.pop("tender_type", TenderType.owner_visible),
    )
    db.add(project)
    db.commit()
    return project


SHAPES = {
    "no description": {"description": None},
    "trade outside the list": {"trade": "Carpentry"},
    "trade in the list": {"trade": "Electrical"},
    "address not set": {"address": "Not set"},
    "long multi-line description": {"description": "Line one.\nLine two. " + "x" * 1400},
    "sealed with a deadline": {"tender_type": TenderType.sealed, "bid_deadline": NOW + timedelta(days=10)},
}


@pytest.mark.parametrize("shape", list(SHAPES))
def test_editing_a_draft_and_submitting_the_full_form_is_never_an_error_screen(owner_flow, shape):
    db = owner_flow["db"]
    draft = _draft(db, owner_flow["owner"], **SHAPES[shape])

    form = _send(owner_flow["client"], owner_flow["pem"], owner_flow["token"], "TENDER_DETAILS", {"tender_id": draft.id, "action": "edit"})
    assert form["screen"] == "CREATE_TENDER", form

    # The form as WhatsApp sends it back: every field on the screen, untouched values included.
    submitted = {
        "tender_id": form["data"]["tender_id"],
        "title": form["data"]["title"],
        "address": form["data"]["address"],
        "description": form["data"]["description"],
        "trade": form["data"]["trade"],
        "bid_deadline": "",
        "tender_type": form["data"]["tender_type"],
    }
    reply = _send(owner_flow["client"], owner_flow["pem"], owner_flow["token"], "CREATE_TENDER", submitted)

    assert reply["screen"] in ("REVIEW", "CREATE_TENDER"), reply
    if reply["screen"] == "CREATE_TENDER":
        assert reply["data"]["error_message"], "a refused form must say why"


def test_review_submitted_without_a_choice_keeps_the_summary_and_says_what_to_pick(owner_flow):
    db = owner_flow["db"]
    draft = _draft(db, owner_flow["owner"], title="Villa", address="Block 3")

    reply = _send(owner_flow["client"], owner_flow["pem"], owner_flow["token"], "REVIEW", {"tender_id": draft.id, "documents": []})

    assert reply["screen"] == "REVIEW", reply
    assert reply["data"]["summary"].strip(), "an error on review must keep the summary, never a blank text block"
    assert "Publish now" in reply["data"]["error_message"]


def test_publishing_a_draft_whose_deadline_has_passed_keeps_the_summary_on_review(owner_flow):
    db = owner_flow["db"]
    draft = _draft(db, owner_flow["owner"], title="Villa", address="Block 3", bid_deadline=NOW - timedelta(days=1))

    reply = _send(owner_flow["client"], owner_flow["pem"], owner_flow["token"], "REVIEW", {"tender_id": draft.id, "next_step": "publish"})

    assert reply["screen"] == "REVIEW", reply
    assert reply["data"]["summary"].strip()
    assert reply["data"]["error_message"], "publish without a deadline must say why"
    db.expire_all()
    assert db.get(Project, draft.id).status == ProjectStatus.draft


# --- the splash screen that opens each dashboard Flow ----------------------------------------


def test_the_owner_flow_opens_on_the_splash_and_continue_shows_the_menu(owner_flow):
    splash = _send(owner_flow["client"], owner_flow["pem"], owner_flow["token"], "SPLASH", {}, action="INIT")
    assert splash == {"screen": "SPLASH", "data": {}}

    menu = _send(owner_flow["client"], owner_flow["pem"], owner_flow["token"], "SPLASH", {})
    assert menu["screen"] == "MENU"


@pytest.mark.parametrize("name", ["owner_dashboard", "contractor_dashboard"])
def test_every_dashboard_flow_starts_on_a_splash_that_continues_to_the_menu(name):
    from flow_contract import _screen

    flow = json.loads((Path(__file__).resolve().parents[1] / "whatsapp_flows" / f"{name}.json").read_text(encoding="utf-8"))
    assert flow["screens"][0]["id"] == "SPLASH"
    footer = next(c for c in flow["screens"][0]["layout"]["children"] if c["type"] == "Footer")
    assert footer["on-click-action"]["name"] == "data_exchange"
    assert flow["routing_model"]["SPLASH"] == ["MENU"]
    assert _screen(name, "SPLASH")["id"] == "SPLASH"
