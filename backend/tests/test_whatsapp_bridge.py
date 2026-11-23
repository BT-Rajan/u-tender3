"""Option 1 bridge: Cogzi forwards inbound messages for a number it still owns. Only the trigger word starts a flow."""

import json

import pytest
from sqlalchemy import select

from app.models.whatsapp import WhatsAppMessageEvent, WhatsAppOutbox
from app.routers import whatsapp as whatsapp_router
from app.services.whatsapp_bridge import envelope_for_trigger
from app.services.whatsapp_routing import install_whatsapp_handlers
from whatsapp_helpers import RecordingSender, enable_whatsapp, sign

BRIDGE_SECRET = "cogzi-webhook-secret"
URL = "/whatsapp/bridge/cogzi"
PHONE = "96533334444"


@pytest.fixture(autouse=True)
def _handlers():
    install_whatsapp_handlers()
    yield


def _event(body="utender", message_id="wamid.BRIDGE1", kind="text", event="message.received", phone=f"+{PHONE}"):
    return {
        "event": event,
        "timestamp": "2026-11-23T10:00:00Z",
        "tenant_id": 1,
        "data": {
            "message_id": message_id,
            "phone_number_id": "501748163027222",
            "sender": {"name": "Test", "phone": phone},
            "message": {"type": kind, "body": body, "received_at": "2026-11-23T10:00:00Z"},
        },
    }


def _post(client, monkeypatch, sender, event, *, secret=BRIDGE_SECRET, raw=None):
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    raw = raw if raw is not None else json.dumps(event).encode()
    return client.post(URL, content=raw, headers={"X-Hub-Signature-256": sign(raw, secret), "Content-Type": "application/json"})


def test_the_bridge_is_off_until_enabled_and_given_a_secret(client, monkeypatch):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=None)
    assert _post(client, monkeypatch, RecordingSender(), _event()).status_code == 404


def test_a_forwarded_event_with_a_bad_signature_is_refused(client, monkeypatch, db):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    response = _post(client, monkeypatch, RecordingSender(), _event(), secret="not-the-secret")
    assert response.status_code == 403
    assert db.query(WhatsAppMessageEvent).count() == 0


def test_the_app_secret_cannot_sign_bridge_events(client, monkeypatch, db):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    response = _post(client, monkeypatch, RecordingSender(), _event(), secret="test-app-secret")
    assert response.status_code == 403


def test_the_trigger_word_starts_the_registration_flow(client, monkeypatch, db):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    sender = RecordingSender()

    response = _post(client, monkeypatch, sender, _event(body="utender"))

    assert response.json() == {"received": True, "started": True}
    flow = sender.flows()[0]
    assert flow["to"] == PHONE
    assert flow["flow_id"] == "flow-registration"
    assert flow["screen"] == "ROLE"


@pytest.mark.parametrize("body", ["  UTENDER  ", "Utender", "utender\n"])
def test_the_trigger_is_matched_ignoring_case_and_surrounding_space(client, monkeypatch, body):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    sender = RecordingSender()
    assert _post(client, monkeypatch, sender, _event(body=body)).json()["started"] is True


@pytest.mark.parametrize("body", ["hello", "I want utender", "utender please", ""])
def test_any_other_text_is_ignored(client, monkeypatch, db, body):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    sender = RecordingSender()
    response = _post(client, monkeypatch, sender, _event(body=body, message_id=f"wamid.IGN{len(body)}"))
    assert response.json() == {"received": True, "started": False}
    assert sender.sent == []
    assert db.query(WhatsAppMessageEvent).count() == 0


def test_non_text_messages_are_ignored(client, monkeypatch):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    sender = RecordingSender()
    assert _post(client, monkeypatch, sender, _event(kind="image")).json()["started"] is False


def test_other_event_types_are_ignored(client, monkeypatch):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    sender = RecordingSender()
    assert _post(client, monkeypatch, sender, _event(event="message.sent")).json()["started"] is False


def test_a_forwarded_message_that_arrives_twice_starts_one_flow(client, monkeypatch, db):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    sender = RecordingSender()
    _post(client, monkeypatch, sender, _event(message_id="wamid.TWICE"))
    _post(client, monkeypatch, sender, _event(message_id="wamid.TWICE"))
    assert len(sender.flows()) == 1
    assert db.query(WhatsAppOutbox).count() == 1


def test_malformed_json_is_a_400(client, monkeypatch):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    raw = b"{not json"
    assert _post(client, monkeypatch, RecordingSender(), None, raw=raw).status_code == 400


def test_the_bridge_stores_only_a_digest_of_the_forwarded_message(client, monkeypatch, db):
    enable_whatsapp(monkeypatch, whatsapp_bridge_secret=BRIDGE_SECRET)
    _post(client, monkeypatch, RecordingSender(), _event(body="utender"))
    row = db.scalar(select(WhatsAppMessageEvent))
    assert row.provider_message_id == "wamid.BRIDGE1"
    assert len(row.payload_sha256) == 64
    assert "utender" not in str(row.__dict__.values())


def test_the_envelope_uses_the_same_wamid_and_number_shape_as_meta():
    from app.config import Settings

    settings = Settings(_env_file=None, whatsapp_bridge_trigger="utender")
    envelope = envelope_for_trigger(_event(message_id="wamid.X", phone="+96533334444"), settings)
    message = envelope["entry"][0]["changes"][0]["value"]["messages"][0]
    assert message["id"] == "wamid.X"
    assert message["from"] == "96533334444"
    assert message["type"] == "text"
