"""Full Phase 2 journeys through the real HTTP endpoints.

Each test uses only what Meta would send: a signed webhook delivery, then encrypted
Flow requests carrying the flow_token from the message the bot sent. The Cloud
API is replaced by RecordingSender, so the only thing mocked is the network.
"""

import json

import pytest
from sqlalchemy import select

from app.models.enums import UserRole
from app.models.owner import OwnerProfile
from app.models.user import User
from app.models.whatsapp import WhatsAppMessageEvent, WhatsAppOutbox
from app.routers import whatsapp as whatsapp_router
from app.services.whatsapp_routing import install_whatsapp_handlers
from whatsapp_helpers import (
    RecordingSender,
    enable_whatsapp,
    flow_request,
    message_envelope,
    sign,
    text_message,
)

WEBHOOK = "/whatsapp/webhook"


@pytest.fixture(autouse=True)
def _install_handlers():
    """These tests drive the real Flow endpoint and webhook, so the production handlers must be registered."""
    install_whatsapp_handlers()
    yield
WA_ID = "96512345678"


def _deliver(client, monkeypatch, sender: RecordingSender, *messages):
    """POST a signed webhook delivery, with the outbox dispatched into `sender`."""
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    raw = json.dumps(message_envelope(*messages)).encode()
    response = client.post(WEBHOOK, content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign(raw)})
    assert response.status_code == 200
    return response


def test_new_owner_registers_on_whatsapp_then_sees_the_owner_dashboard(monkeypatch, client, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()

    _deliver(client, monkeypatch, sender, text_message("wamid.E2E1", WA_ID, "hi"))
    flow = sender.flows()[0]
    assert flow["flow_id"] == "flow-registration"
    assert flow["screen"] == "WELCOME"
    token = flow["flow_token"]

    reply, _ = flow_request(client, public_pem, token=token, action="INIT")
    assert reply == {"screen": "WELCOME", "data": {}}
    flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "owner", "language": "en"})
    reply, _ = flow_request(client, public_pem, token=token, action="data_exchange", screen="OWNER_DETAILS", data={"full_name": "Layla Al-Sabah"})
    assert reply["screen"] == "SUCCESS"

    user = db.scalar(select(User).where(User.phone == f"+{WA_ID}"))
    assert user.role == UserRole.owner
    assert db.get(OwnerProfile, user.id) is not None

    # The next message from the same number opens the dashboard for the new account.
    sender.sent.clear()
    _deliver(client, monkeypatch, sender, text_message("wamid.E2E2", WA_ID, "menu"))
    dashboard = sender.flows()[0]
    assert dashboard["flow_id"] == "flow-owner"
    menu_token = dashboard["flow_token"]

    reply, _ = flow_request(client, public_pem, token=menu_token, action="INIT")
    assert reply["screen"] == "MENU"
    assert reply["data"]["greeting"] == "Hello Layla"
    assert "Documents are incomplete" in reply["data"]["status"]

    reply, _ = flow_request(client, public_pem, token=menu_token, action="data_exchange", screen="MENU", data={"choice": "my_documents"})
    assert reply["screen"] == "DOCUMENTS"
    # This owner has no requirements configured, so the checklist says so explicitly.
    assert reply["data"]["checklist"] == "No documents are required for your account."


def test_new_contractor_registers_then_sees_the_contractor_dashboard(monkeypatch, client, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()

    _deliver(client, monkeypatch, sender, text_message("wamid.E2E3", WA_ID, "hi"))
    token = sender.flows()[0]["flow_token"]

    flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "contractor", "language": "ar"})
    reply, _ = flow_request(
        client,
        public_pem,
        token=token,
        action="data_exchange",
        screen="CONTRACTOR_DETAILS",
        data={"contact_name": "Omar Haddad", "company_name": "Haddad Builders", "primary_trade": "Plumbing"},
    )
    assert reply["screen"] == "SUCCESS"

    sender.sent.clear()
    _deliver(client, monkeypatch, sender, text_message("wamid.E2E4", WA_ID, "menu"))
    assert sender.flows()[0]["flow_id"] == "flow-contractor"


def test_an_interrupted_registration_resumes_where_it_stopped(monkeypatch, client, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()

    _deliver(client, monkeypatch, sender, text_message("wamid.INT1", WA_ID, "hi"))
    first_token = sender.flows()[0]["flow_token"]
    flow_request(client, public_pem, token=first_token, action="data_exchange", screen="ROLE", data={"role": "owner", "language": "ar"})
    # The customer closes the Flow here. Nothing was submitted for OWNER_DETAILS.

    sender.sent.clear()
    _deliver(client, monkeypatch, sender, text_message("wamid.INT2", WA_ID, "back"))
    resume_token = sender.flows()[0]["flow_token"]
    assert resume_token != first_token

    reply, _ = flow_request(client, public_pem, token=first_token, action="INIT")
    assert reply == {"screen": "EXPIRED", "data": {}}

    reply, _ = flow_request(client, public_pem, token=resume_token, action="INIT")
    assert reply == {"screen": "OWNER_DETAILS", "data": {}}

    reply, _ = flow_request(client, public_pem, token=resume_token, action="data_exchange", screen="OWNER_DETAILS", data={"full_name": "Layla Al-Sabah"})
    assert reply["screen"] == "SUCCESS"
    user = db.scalar(select(User).where(User.phone == f"+{WA_ID}"))
    assert user.language.value == "ar"


def test_a_duplicate_webhook_does_not_send_a_second_flow(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    message = text_message("wamid.DUPE1", WA_ID, "hi")

    _deliver(client, monkeypatch, sender, message)
    _deliver(client, monkeypatch, sender, message)

    assert len(sender.flows()) == 1
    assert db.query(WhatsAppMessageEvent).count() == 1
    assert db.query(WhatsAppOutbox).count() == 1


def test_a_failed_send_is_left_in_the_outbox_for_the_cron_to_retry(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)

    class BrokenSender(RecordingSender):
        def send_flow(self, *args, **kwargs):
            from app.services.whatsapp_client import WhatsAppSendError

            raise WhatsAppSendError("network down", transient=True)

    _deliver(client, monkeypatch, BrokenSender(), text_message("wamid.RETRY1", WA_ID, "hi"))

    row = db.query(WhatsAppOutbox).one()
    assert row.status == "pending"
    assert row.attempts == 1
    # The webhook still acknowledged Meta, so a retry never comes from Meta.
    assert db.query(WhatsAppMessageEvent).one().status == "processed"


def test_the_flow_token_is_removed_from_the_outbox_after_a_successful_send(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    _deliver(client, monkeypatch, sender, text_message("wamid.SECRET1", WA_ID, "hi"))

    row = db.query(WhatsAppOutbox).one()
    assert row.status == "sent"
    assert "flow_token" not in (row.params_json or {})
    assert sender.flows()[0]["flow_token"]
