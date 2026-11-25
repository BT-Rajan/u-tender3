"""The relay endpoint: Cogzi posts a WhatsApp message, U-Tender returns the replies for Cogzi to send."""

import hashlib
import hmac
import json
import time
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.models.whatsapp import WhatsAppIdentity, WhatsAppMessageEvent, WhatsAppOutbox
from app.services.whatsapp_routing import install_whatsapp_handlers
from whatsapp_helpers import PHONE_NUMBER_ID, enable_whatsapp

RELAY = "/relay/whatsapp"
SECRET = "relay-test-secret-value"
FROM = "+96512345678"
WA_ID = "96512345678"


@pytest.fixture(autouse=True)
def _relay_setup(monkeypatch):
    install_whatsapp_handlers()
    enable_whatsapp(monkeypatch)
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "relay_secret", SECRET)
    monkeypatch.setattr(get_settings(), "relay_max_skew_seconds", 300)


OTHER_NUMBER_ID = "demo-number-not-utender"


def _relayed(message_id: str, body: str | None, *, number_id: str = OTHER_NUMBER_ID, **extra) -> dict:
    message = {"id": message_id, "from": FROM, "type": "text", "body": body, "timestamp": str(int(time.time())), "media": None}
    message.update(extra)
    return {"event": "whatsapp.message", "account_id": 1, "phone_number_id": number_id, "message": message}


def _signed_headers(raw: bytes, *, secret: str = SECRET, timestamp: str | None = None) -> dict:
    stamp = timestamp or str(int(time.time()))
    signature = "sha256=" + hmac.new(secret.encode(), f"{stamp}.".encode() + raw, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-Cogzi-Timestamp": stamp, "X-Cogzi-Signature": signature}


def _post(client, payload: dict, **headers):
    raw = json.dumps(payload).encode()
    return client.post(RELAY, content=raw, headers=headers or _signed_headers(raw))


def test_a_request_without_a_valid_signature_is_refused(client):
    raw = json.dumps(_relayed("relay.bad", "utender")).encode()

    assert client.post(RELAY, content=raw, headers=_signed_headers(raw, secret="someone-else")).status_code == 403
    assert client.post(RELAY, content=raw, headers={"Content-Type": "application/json"}).status_code == 403


def test_an_old_signature_is_refused_so_it_cannot_be_replayed_later(client):
    raw = json.dumps(_relayed("relay.old", "utender")).encode()
    stale = str(int(time.time()) - 3600)

    assert client.post(RELAY, content=raw, headers=_signed_headers(raw, timestamp=stale)).status_code == 403


def test_the_relay_is_off_until_a_secret_is_configured(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "relay_secret", None)

    assert _post(client, _relayed("relay.off", "utender")).status_code == 503


def test_a_new_user_who_says_the_trigger_word_gets_the_registration_flow(client):
    response = _post(client, _relayed("relay.hi1", "utender"))

    assert response.status_code == 200
    replies = response.json()["replies"]
    flow = next(reply for reply in replies if reply["type"] == "flow")
    assert flow["flow_id"] == "flow-registration"
    assert flow["screen"] == "WELCOME"
    assert flow["flow_token"]


def test_a_new_user_who_does_not_say_the_trigger_word_gets_nothing_and_nothing_is_stored(client, db):
    response = _post(client, _relayed("relay.hi2", "hello there"))

    assert response.json() == {"replies": []}
    assert db.scalar(select(func.count()).select_from(WhatsAppMessageEvent)) == 0


def test_someone_already_registered_is_answered_without_the_trigger_word(client, db):
    db.add(WhatsAppIdentity(wa_id=WA_ID, phone_e164=FROM))
    db.commit()

    replies = _post(client, _relayed("relay.known", "any update?")).json()["replies"]

    assert replies, "a known user is answered even without the trigger word"


def test_a_repeated_delivery_produces_no_second_set_of_replies(client):
    first = _post(client, _relayed("relay.twice", "utender")).json()["replies"]
    second = _post(client, _relayed("relay.twice", "utender")).json()["replies"]

    assert first, "the first delivery is answered"
    assert second == [], "a repeat of the same message is not answered again"


def test_replies_are_marked_sent_so_U_Tender_never_sends_them_a_second_time(client, db):
    replies = _post(client, _relayed("relay.handoff", "utender")).json()["replies"]
    rows = db.scalars(select(WhatsAppOutbox).where(WhatsAppOutbox.recipient_wa_id == WA_ID)).all()

    assert replies
    assert rows and all(row.status == "sent" for row in rows)
    assert all("flow_token" not in (row.params_json or {}) for row in rows), "the token is not kept after it was handed over"


def test_a_message_on_the_relayed_number_is_answered_whatever_it_says(client):
    replies = _post(client, _relayed("relay.number", "random words", number_id=PHONE_NUMBER_ID)).json()["replies"]

    assert replies, "a message on U-Tender's own number is answered"
