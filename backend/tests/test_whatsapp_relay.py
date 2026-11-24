"""U-Tender sends through Cogzi's relay: signed bodies, message IDs back, and clear failure modes."""

import hashlib
import hmac
import json

import httpx
import pytest

from app.config import get_settings
from app.routers import whatsapp as whatsapp_router
from app.services.whatsapp_client import WhatsAppCloudClient, WhatsAppSendError
from app.services.whatsapp_relay import WhatsAppRelayClient

RELAY_URL = "https://msg.karkathar.org/api/utender-relay"
SECRET = "relay-test-secret"


def _client(handler):
    return WhatsAppRelayClient(relay_url=RELAY_URL, secret=SECRET, transport=httpx.MockTransport(handler))


def test_a_text_message_is_posted_signed_and_returns_the_message_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        seen["signature"] = request.headers["X-Hub-Signature-256"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"message_id": "wamid.RELAYED1"})

    message_id = _client(handler).send_text("96512345678", "Hello")

    assert message_id == "wamid.RELAYED1"
    assert seen["url"] == RELAY_URL
    expected = "sha256=" + hmac.new(SECRET.encode(), seen["body"], hashlib.sha256).hexdigest()
    assert seen["signature"] == expected
    sent = json.loads(seen["body"])
    assert sent["to"] == "96512345678"
    assert sent["message"]["type"] == "text"
    assert sent["message"]["text"]["body"] == "Hello"


def test_a_flow_message_keeps_its_interactive_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message_id": "wamid.FLOW1"})

    _client(handler).send_flow("96512345678", flow_id="flow-registration", flow_token="tok", screen="SPLASH", body="Hi", cta="Start")

    assert seen["body"]["message"]["type"] == "interactive"
    assert seen["body"]["message"]["interactive"]["action"]["parameters"]["flow_id"] == "flow-registration"


def test_a_server_error_is_transient_so_the_outbox_retries():
    client = _client(lambda request: httpx.Response(503, json={"error": "down"}))
    with pytest.raises(WhatsAppSendError) as excinfo:
        client.send_text("96512345678", "Hello")
    assert excinfo.value.transient is True


def test_a_refusal_is_permanent():
    client = _client(lambda request: httpx.Response(403, json={"error": "Invalid signature"}))
    with pytest.raises(WhatsAppSendError) as excinfo:
        client.send_text("96512345678", "Hello")
    assert excinfo.value.transient is False


def test_a_response_without_a_message_id_is_treated_as_transient():
    client = _client(lambda request: httpx.Response(200, json={}))
    with pytest.raises(WhatsAppSendError):
        client.send_text("96512345678", "Hello")


def test_the_relay_is_not_used_without_a_url_and_secret(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_relay_url", None)
    monkeypatch.setattr(settings, "whatsapp_forward_secret", None)
    with pytest.raises(WhatsAppSendError):
        WhatsAppRelayClient.from_settings(settings)


def test_the_sender_is_the_relay_when_a_relay_url_is_set(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_relay_url", RELAY_URL)
    monkeypatch.setattr(settings, "whatsapp_forward_secret", SECRET)
    assert isinstance(whatsapp_router.build_whatsapp_sender(), WhatsAppRelayClient)


def test_the_sender_is_the_direct_client_without_a_relay_url(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_relay_url", None)
    monkeypatch.setattr(settings, "whatsapp_access_token", "token")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "PNID")
    sender = whatsapp_router.build_whatsapp_sender()
    assert isinstance(sender, WhatsAppCloudClient) and not isinstance(sender, WhatsAppRelayClient)
