"""Shared helpers for the WhatsApp test modules.

These build requests the way Meta does: signed bodies, Flow requests encrypted
with RSA-OAEP + AES-GCM, and webhook envelopes. They don't use the code under
test to make them, so the tests check the real wire format.
"""

import base64
import hashlib
import hmac
import json
import os
from functools import lru_cache
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings
from app.services.flow_crypto import generate_key_pair

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"
ACCESS_TOKEN = "test-access-token"
PHONE_NUMBER_ID = "1000000000001"
CRON_SECRET = "test-cron-secret"


@lru_cache(maxsize=1)
def flow_key_pair() -> tuple[str, str]:
    """One RSA-2048 pair per test session. Generating keys is the slow part."""
    return generate_key_pair(2048)


def sign(raw_body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def enable_whatsapp(monkeypatch, **overrides: Any) -> tuple[str, str]:
    """Turn WhatsApp on for one test with fake secrets. Returns the Flow (private, public) PEM pair.

    The settings object is a process-wide singleton, so monkeypatch restores it
    after each test.
    """
    private_pem, public_pem = flow_key_pair()
    values: dict[str, Any] = {
        "whatsapp_enabled": True,
        "whatsapp_app_secret": APP_SECRET,
        "whatsapp_verify_token": VERIFY_TOKEN,
        "whatsapp_access_token": ACCESS_TOKEN,
        "whatsapp_phone_number_id": PHONE_NUMBER_ID,
        "whatsapp_flow_private_key": private_pem,
        "cron_secret": CRON_SECRET,
        "whatsapp_outbox_max_attempts": 3,
    }
    values.update(overrides)
    settings = get_settings()
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    return private_pem, public_pem


def message_envelope(*messages: dict[str, Any], statuses: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": PHONE_NUMBER_ID}}
    if messages:
        value["messages"] = list(messages)
    if statuses:
        value["statuses"] = statuses
    return {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{"field": "messages", "value": value}]}]}


def text_message(message_id: str, wa_id: str, body: str) -> dict[str, Any]:
    return {"from": wa_id, "id": message_id, "timestamp": "1700000000", "type": "text", "text": {"body": body}}


def status_update(message_id: str, wa_id: str, status: str) -> dict[str, Any]:
    return {"id": message_id, "status": status, "timestamp": "1700000001", "recipient_id": wa_id}


def encode_request(payload: dict[str, Any], public_pem: str, aes_key: bytes | None = None, iv: bytes | None = None) -> tuple[dict[str, str], bytes, bytes]:
    """Encrypt a Flow request the way WhatsApp does. Returns (body, aes_key, iv)."""
    aes_key = aes_key or os.urandom(16)
    iv = iv or os.urandom(12)
    public_key = serialization.load_pem_public_key(public_pem.encode())
    encrypted_key = public_key.encrypt(
        aes_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    ciphertext_and_tag = AESGCM(aes_key).encrypt(iv, json.dumps(payload).encode(), None)
    body = {
        "encrypted_aes_key": base64.b64encode(encrypted_key).decode(),
        "encrypted_flow_data": base64.b64encode(ciphertext_and_tag).decode(),
        "initial_vector": base64.b64encode(iv).decode(),
        "version": "3.0",
    }
    return body, aes_key, iv


def decode_response(encrypted_text: str, aes_key: bytes, iv: bytes) -> dict[str, Any]:
    """Decrypt a reply the way WhatsApp does: same key, IV with every bit flipped."""
    flipped = bytes(byte ^ 0xFF for byte in iv)
    plaintext = AESGCM(aes_key).decrypt(flipped, base64.b64decode(encrypted_text), None)
    return json.loads(plaintext)
