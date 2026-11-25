import json

from sqlalchemy import select

from app.models.whatsapp import WhatsAppMessageEvent
from app.routers.whatsapp import register_flow_handler
from app.services.whatsapp_events import register_inbound_handler
from whatsapp_helpers import (
    VERIFY_TOKEN,
    encode_request,
    decode_response,
    enable_whatsapp,
    flow_key_pair,
    message_envelope,
    sign,
    status_update,
    text_message,
)

WEBHOOK = "/whatsapp/webhook"
FLOWS = "/whatsapp/flows"


def _post_signed(client, body: dict, secret: str | None = None, header: str | None = None):
    raw = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if header is not None:
        headers["X-Hub-Signature-256"] = header
    elif secret is not None:
        headers["X-Hub-Signature-256"] = sign(raw, secret)
    return client.post(WEBHOOK, content=raw, headers=headers)


# --- verification handshake -------------------------------------------------


def test_verification_echoes_the_challenge_when_the_token_matches(monkeypatch, client):
    enable_whatsapp(monkeypatch)
    response = client.get(
        WEBHOOK,
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "1158201444"},
    )
    assert response.status_code == 200
    assert response.text == "1158201444"


def test_verification_rejects_a_wrong_token(monkeypatch, client):
    enable_whatsapp(monkeypatch)
    response = client.get(
        WEBHOOK,
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
    )
    assert response.status_code == 403


def test_verification_rejects_any_other_mode(monkeypatch, client):
    enable_whatsapp(monkeypatch)
    response = client.get(
        WEBHOOK,
        params={"hub.mode": "unsubscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "1"},
    )
    assert response.status_code == 403


def test_verification_without_a_configured_token_never_succeeds(monkeypatch, client):
    enable_whatsapp(monkeypatch, whatsapp_verify_token=None)
    response = client.get(
        WEBHOOK,
        params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"},
    )
    assert response.status_code == 403


# --- feature switch ---------------------------------------------------------


def test_every_whatsapp_route_is_404_while_disabled(client):
    assert client.get(WEBHOOK, params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "1"}).status_code == 404
    assert _post_signed(client, message_envelope(), secret="whatever").status_code == 404
    assert client.post(FLOWS, content=b"{}").status_code == 404


# --- signed delivery --------------------------------------------------------


def test_a_correctly_signed_message_is_recorded(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)
    body = message_envelope(text_message("wamid.HTTP1", "96512345678", "hello"))

    response = _post_signed(client, body, secret="test-app-secret")

    assert response.status_code == 200
    assert response.json() == {"received": True}
    stored = db.scalars(select(WhatsAppMessageEvent)).all()
    assert [event.provider_message_id for event in stored] == ["wamid.HTTP1"]


def test_an_invalid_signature_is_refused_and_nothing_is_stored(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)
    response = _post_signed(client, message_envelope(text_message("wamid.BAD", "96512345678", "x")), secret="not-the-secret")

    assert response.status_code == 403
    assert db.query(WhatsAppMessageEvent).count() == 0


def test_a_missing_signature_is_refused(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)
    response = _post_signed(client, message_envelope(text_message("wamid.NOSIG", "96512345678", "x")))

    assert response.status_code == 403
    assert db.query(WhatsAppMessageEvent).count() == 0


def test_a_signature_over_different_bytes_is_refused(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)
    body = message_envelope(text_message("wamid.TAMPER", "96512345678", "x"))
    raw = json.dumps(body).encode()
    response = client.post(
        WEBHOOK,
        content=raw + b" ",
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign(raw)},
    )
    assert response.status_code == 403


def test_a_duplicate_delivery_is_acknowledged_but_not_processed_twice(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)
    calls = []
    register_inbound_handler(lambda session, event, message: calls.append(message["id"]))
    body = message_envelope(text_message("wamid.REDO", "96512345678", "again"))

    first = _post_signed(client, body, secret="test-app-secret")
    second = _post_signed(client, body, secret="test-app-secret")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls == ["wamid.REDO"]
    assert db.query(WhatsAppMessageEvent).count() == 1


def test_status_updates_are_accepted(monkeypatch, client, db):
    enable_whatsapp(monkeypatch)
    body = message_envelope(statuses=[status_update("wamid.OUT", "96512345678", "read")])

    response = _post_signed(client, body, secret="test-app-secret")

    assert response.status_code == 200
    assert db.query(WhatsAppMessageEvent).one().event_type == "status_read"


def test_a_signed_but_malformed_json_body_is_a_400(monkeypatch, client):
    enable_whatsapp(monkeypatch)
    raw = b"{not json"
    response = client.post(WEBHOOK, content=raw, headers={"X-Hub-Signature-256": sign(raw)})
    assert response.status_code == 400


def test_a_signed_json_array_is_a_400(monkeypatch, client):
    enable_whatsapp(monkeypatch)
    raw = b"[1, 2, 3]"
    response = client.post(WEBHOOK, content=raw, headers={"X-Hub-Signature-256": sign(raw)})
    assert response.status_code == 400


def test_a_webhook_with_no_app_secret_configured_refuses_every_delivery(monkeypatch, client, db):
    enable_whatsapp(monkeypatch, whatsapp_app_secret=None)
    response = _post_signed(client, message_envelope(text_message("wamid.NOSECRET", "96512345678", "x")), header="sha256=00")
    assert response.status_code == 403
    assert db.query(WhatsAppMessageEvent).count() == 0


# --- Flow data endpoint -----------------------------------------------------


def _flow_post(client, body: dict, secret: str = "test-app-secret", header: str | None = None):
    raw = json.dumps(body).encode()
    signature = header if header is not None else sign(raw, secret)
    return client.post(FLOWS, content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})


def test_flow_ping_returns_an_encrypted_active_status(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch)
    body, aes_key, iv = encode_request({"version": "3.0", "action": "ping"}, public_pem)

    response = _flow_post(client, body)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert decode_response(response.text, aes_key, iv) == {"data": {"status": "active"}}


def test_flow_error_notification_is_acknowledged(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch)
    body, aes_key, iv = encode_request({"action": "error_notification", "data": {"error": "x"}}, public_pem)

    response = _flow_post(client, body)

    assert decode_response(response.text, aes_key, iv) == {"data": {"acknowledged": True}}


def test_flow_request_with_a_bad_signature_is_432(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch)
    body, _, _ = encode_request({"action": "ping"}, public_pem)
    assert _flow_post(client, body, secret="wrong").status_code == 432


def test_flow_request_with_no_signature_is_432(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch)
    body, _, _ = encode_request({"action": "ping"}, public_pem)
    raw = json.dumps(body).encode()
    response = client.post(FLOWS, content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 432


def test_flow_request_encrypted_for_another_key_is_421(monkeypatch, client):
    from app.services.flow_crypto import generate_key_pair

    enable_whatsapp(monkeypatch)
    _, other_public_pem = generate_key_pair(2048)
    body, _, _ = encode_request({"action": "ping"}, other_public_pem)

    assert _flow_post(client, body).status_code == 421


def test_flow_request_with_garbage_ciphertext_is_421(monkeypatch, client):
    enable_whatsapp(monkeypatch)
    response = _flow_post(client, {"encrypted_aes_key": "AAAA", "initial_vector": "AAAA", "encrypted_flow_data": "AAAA"})
    assert response.status_code == 421


def test_flow_request_with_no_private_key_configured_is_421(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch, whatsapp_flow_private_key=None)
    body, _, _ = encode_request({"action": "ping"}, public_pem)
    assert _flow_post(client, body).status_code == 421


def test_flow_request_with_an_invalid_private_key_is_421(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch, whatsapp_flow_private_key="not a pem")
    body, _, _ = encode_request({"action": "ping"}, public_pem)
    assert _flow_post(client, body).status_code == 421


def test_flow_request_that_is_not_a_json_object_is_421(monkeypatch, client):
    enable_whatsapp(monkeypatch)
    raw = b"[1,2]"
    response = client.post(FLOWS, content=raw, headers={"X-Hub-Signature-256": sign(raw)})
    assert response.status_code == 421


def test_unhandled_data_exchange_gets_an_encrypted_fallback_with_the_screen(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch)
    body, aes_key, iv = encode_request({"action": "data_exchange", "screen": "NAME", "data": {}}, public_pem)

    reply = decode_response(_flow_post(client, body).text, aes_key, iv)

    assert reply["screen"] == "DONE"
    assert "no longer available" in reply["data"]["message"]


def test_a_registered_flow_handler_supplies_the_reply(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch)
    register_flow_handler(
        lambda db, payload: {"screen": "NEXT", "data": {"from": payload["screen"]}} if payload.get("action") == "data_exchange" else None
    )
    body, aes_key, iv = encode_request({"action": "data_exchange", "screen": "START", "data": {}}, public_pem)

    reply = decode_response(_flow_post(client, body).text, aes_key, iv)

    assert reply == {"screen": "NEXT", "data": {"from": "START"}}


def test_flow_handlers_are_not_consulted_for_ping(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch)
    register_flow_handler(lambda db, payload: {"data": {"status": "wrong"}})
    body, aes_key, iv = encode_request({"action": "ping"}, public_pem)

    assert decode_response(_flow_post(client, body).text, aes_key, iv) == {"data": {"status": "active"}}


def test_flow_request_is_not_logged_with_its_decrypted_content(monkeypatch, client, caplog):
    _, public_pem = enable_whatsapp(monkeypatch)
    secret_answer = "PRIVATE-ANSWER-123"
    body, _, _ = encode_request({"action": "data_exchange", "screen": "X", "data": {"answer": secret_answer}}, public_pem)
    _flow_post(client, body)
    assert secret_answer not in caplog.text
