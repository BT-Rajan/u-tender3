"""Messages Cogzi forwards from the shared number reach the same inbound routing as Meta's own webhook.

Cogzi signs the forwarded body with WHATSAPP_FORWARD_SECRET, not with U-Tender's app secret.
"""

import json

import pytest
from sqlalchemy import select

from app.routers import whatsapp as whatsapp_router
from app.services.whatsapp_routing import install_whatsapp_handlers
from whatsapp_helpers import RecordingSender, enable_whatsapp, message_envelope, sign, text_message

FORWARD = "/whatsapp/forward"
FORWARD_SECRET = "test-forward-secret"
WA_ID = "96512345678"


@pytest.fixture(autouse=True)
def _install_handlers():
    install_whatsapp_handlers()
    yield


def _post(client, monkeypatch, sender, raw: bytes, signature: str | None):
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return client.post(FORWARD, content=raw, headers=headers)


def test_a_forwarded_utender_message_starts_the_registration_flow(monkeypatch, client, db):
    enable_whatsapp(monkeypatch, whatsapp_forward_secret=FORWARD_SECRET)
    sender = RecordingSender()
    raw = json.dumps(message_envelope(text_message("wamid.FWD1", WA_ID, "utender"))).encode()

    response = _post(client, monkeypatch, sender, raw, sign(raw, FORWARD_SECRET))

    assert response.status_code == 200
    assert sender.flows()[0]["flow_id"] == "flow-registration"


def test_a_forwarded_message_signed_with_the_app_secret_is_refused(monkeypatch, client, db):
    enable_whatsapp(monkeypatch, whatsapp_forward_secret=FORWARD_SECRET)
    sender = RecordingSender()
    raw = json.dumps(message_envelope(text_message("wamid.FWD2", WA_ID, "utender"))).encode()

    response = _post(client, monkeypatch, sender, raw, sign(raw))

    assert response.status_code == 403
    assert sender.sent == []


def test_a_forwarded_message_with_a_bad_signature_is_refused(monkeypatch, client, db):
    enable_whatsapp(monkeypatch, whatsapp_forward_secret=FORWARD_SECRET)
    raw = json.dumps(message_envelope(text_message("wamid.FWD3", WA_ID, "utender"))).encode()

    response = _post(client, monkeypatch, RecordingSender(), raw, "sha256=00")

    assert response.status_code == 403


def test_without_a_forward_secret_the_route_is_not_found(monkeypatch, client, db):
    enable_whatsapp(monkeypatch, whatsapp_forward_secret=None)
    raw = json.dumps(message_envelope(text_message("wamid.FWD4", WA_ID, "utender"))).encode()

    response = _post(client, monkeypatch, RecordingSender(), raw, sign(raw, FORWARD_SECRET))

    assert response.status_code == 404


def test_a_repeated_forward_of_the_same_message_is_not_handled_twice(monkeypatch, client, db):
    enable_whatsapp(monkeypatch, whatsapp_forward_secret=FORWARD_SECRET)
    sender = RecordingSender()
    raw = json.dumps(message_envelope(text_message("wamid.FWD5", WA_ID, "utender"))).encode()

    _post(client, monkeypatch, sender, raw, sign(raw, FORWARD_SECRET))
    first = len(sender.sent)
    _post(client, monkeypatch, sender, raw, sign(raw, FORWARD_SECRET))

    assert len(sender.sent) == first
