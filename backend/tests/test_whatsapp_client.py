import json
import logging

import httpx
import pytest

from app.services.whatsapp_client import WhatsAppCloudClient, WhatsAppSendError, mask_recipient

API_URL = "https://graph.facebook.com"
VERSION = "v21.0"
PHONE_ID = "1000000000001"
TOKEN = "super-secret-token-value"
RECIPIENT = "96512345678"


def _client(handler) -> WhatsAppCloudClient:
    return WhatsAppCloudClient(
        access_token=TOKEN,
        phone_number_id=PHONE_ID,
        api_version=VERSION,
        api_url=API_URL,
        transport=httpx.MockTransport(handler),
    )


def _ok(message_id: str = "wamid.OK1"):
    return httpx.Response(200, json={"messaging_product": "whatsapp", "messages": [{"id": message_id}]})


def test_send_text_posts_the_expected_payload_to_the_expected_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["json"] = json.loads(request.content)
        return _ok("wamid.TEXT")

    message_id = _client(handler).send_text(RECIPIENT, "Hello")

    assert message_id == "wamid.TEXT"
    assert seen["url"] == f"{API_URL}/{VERSION}/{PHONE_ID}/messages"
    assert seen["auth"] == f"Bearer {TOKEN}"
    assert seen["json"] == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": RECIPIENT,
        "type": "text",
        "text": {"body": "Hello", "preview_url": False},
    }


def test_send_template_includes_language_and_components_only_when_given():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _ok()

    client = _client(handler)
    client.send_template(RECIPIENT, "document_approved", "en")
    client.send_template(
        RECIPIENT,
        "offer_submitted",
        "ar",
        [{"type": "body", "parameters": [{"type": "text", "text": "Tower A"}]}],
    )

    bare, with_components = seen
    assert bare["type"] == "template"
    assert bare["template"] == {"name": "document_approved", "language": {"code": "en"}}
    assert with_components["template"]["language"] == {"code": "ar"}
    assert with_components["template"]["components"][0]["parameters"][0]["text"] == "Tower A"


def test_a_200_without_a_message_id_is_treated_as_transient():
    client = _client(lambda request: httpx.Response(200, json={}))
    with pytest.raises(WhatsAppSendError) as excinfo:
        client.send_text(RECIPIENT, "x")
    assert excinfo.value.transient is True


def test_a_400_is_permanent():
    body = {"error": {"message": "Invalid parameter", "code": 100}}
    client = _client(lambda request: httpx.Response(400, json=body))
    with pytest.raises(WhatsAppSendError) as excinfo:
        client.send_template(RECIPIENT, "bad", "en")
    assert excinfo.value.transient is False
    assert excinfo.value.status_code == 400
    assert excinfo.value.error_code == "100"


@pytest.mark.parametrize("code", [4, 80007, 130429])
def test_meta_throttling_codes_are_transient_even_on_a_400(code):
    client = _client(lambda request: httpx.Response(400, json={"error": {"code": code}}))
    with pytest.raises(WhatsAppSendError) as excinfo:
        client.send_text(RECIPIENT, "x")
    assert excinfo.value.transient is True


def test_429_is_transient():
    client = _client(lambda request: httpx.Response(429, json={}))
    with pytest.raises(WhatsAppSendError) as excinfo:
        client.send_text(RECIPIENT, "x")
    assert excinfo.value.transient is True


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_is_transient(status):
    client = _client(lambda request: httpx.Response(status, text="upstream"))
    with pytest.raises(WhatsAppSendError) as excinfo:
        client.send_text(RECIPIENT, "x")
    assert excinfo.value.transient is True


def test_a_non_json_error_body_still_classifies_by_status():
    client = _client(lambda request: httpx.Response(403, text="<html>forbidden</html>"))
    with pytest.raises(WhatsAppSendError) as excinfo:
        client.send_text(RECIPIENT, "x")
    assert excinfo.value.transient is False
    assert excinfo.value.error_code is None


def test_a_network_failure_is_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(WhatsAppSendError) as excinfo:
        _client(handler).send_text(RECIPIENT, "x")
    assert excinfo.value.transient is True
    assert excinfo.value.status_code is None


def test_errors_and_logs_never_contain_the_token_or_the_message_body(caplog):
    caplog.set_level(logging.DEBUG, logger="utender.whatsapp")
    secret_body = "Private tender detail: Tower A budget 90000"

    client = _client(lambda request: httpx.Response(400, json={"error": {"code": 100}}))
    with pytest.raises(WhatsAppSendError) as excinfo:
        client.send_text(RECIPIENT, secret_body)

    combined = " ".join([str(excinfo.value), caplog.text])
    assert TOKEN not in combined
    assert secret_body not in combined
    assert RECIPIENT not in combined


def test_mask_recipient_keeps_only_the_last_four_digits():
    assert mask_recipient(RECIPIENT) == "***5678"
    assert mask_recipient("123") == "***"


def test_from_settings_refuses_when_not_configured(monkeypatch):
    from app.config import Settings

    settings = Settings(_env_file=None, whatsapp_access_token=None, whatsapp_phone_number_id=None)
    with pytest.raises(WhatsAppSendError) as excinfo:
        WhatsAppCloudClient.from_settings(settings)
    assert excinfo.value.transient is False
