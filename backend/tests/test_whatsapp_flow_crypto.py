import base64
import json
import os

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services.flow_crypto import (
    FlowCryptoError,
    decrypt_request,
    encrypt_response,
    generate_key_pair,
    load_private_key,
)
from whatsapp_helpers import decode_response, encode_request, flow_key_pair


@pytest.fixture(scope="module")
def keys():
    private_pem, public_pem = flow_key_pair()
    private_key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    return private_pem, public_pem, private_key


def test_round_trip_request_and_reply(keys):
    _, public_pem, private_key = keys
    payload = {"version": "3.0", "action": "data_exchange", "screen": "NAME", "data": {"full_name": "Layla"}}

    body, aes_key, iv = encode_request(payload, public_pem)
    decrypted = decrypt_request(body, private_key)

    assert decrypted.payload == payload
    assert decrypted.aes_key == aes_key
    assert decrypted.iv == iv

    reply = {"screen": "NEXT", "data": {"ok": True}}
    encrypted_reply = encrypt_response(reply, decrypted.aes_key, decrypted.iv)
    assert decode_response(encrypted_reply, aes_key, iv) == reply


def test_reply_keeps_arabic_text_readable_in_the_ciphertext_round_trip(keys):
    _, public_pem, private_key = keys
    body, aes_key, iv = encode_request({"action": "INIT"}, public_pem)
    decrypted = decrypt_request(body, private_key)
    reply = {"data": {"error_message": "تعذر إكمال الطلب"}}
    assert decode_response(encrypt_response(reply, decrypted.aes_key, decrypted.iv), aes_key, iv) == reply


def test_reply_uses_the_flipped_iv_not_the_original():
    aes_key = os.urandom(16)
    iv = os.urandom(12)
    encrypted_reply = encrypt_response({"data": {"status": "active"}}, aes_key, iv)
    # Decrypting with the original IV must fail: the reply is bound to the flipped one.
    with pytest.raises(Exception):
        AESGCM(aes_key).decrypt(iv, base64.b64decode(encrypted_reply), None)


def test_rejects_a_request_encrypted_for_another_key(keys):
    _, other_public_pem = generate_key_pair(2048)
    _, _, private_key = keys
    body, _, _ = encode_request({"action": "ping"}, other_public_pem)
    with pytest.raises(FlowCryptoError, match="not encrypted for this key"):
        decrypt_request(body, private_key)


def test_rejects_a_tampered_ciphertext(keys):
    _, public_pem, private_key = keys
    body, _, _ = encode_request({"action": "ping"}, public_pem)
    data = bytearray(base64.b64decode(body["encrypted_flow_data"]))
    data[0] ^= 0x01
    body["encrypted_flow_data"] = base64.b64encode(bytes(data)).decode()
    with pytest.raises(FlowCryptoError, match="could not be decrypted"):
        decrypt_request(body, private_key)


def test_rejects_a_tampered_iv(keys):
    _, public_pem, private_key = keys
    body, _, iv = encode_request({"action": "ping"}, public_pem)
    body["initial_vector"] = base64.b64encode(bytes(12)).decode()
    with pytest.raises(FlowCryptoError):
        decrypt_request(body, private_key)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"encrypted_aes_key": "%%%", "initial_vector": "AAAA", "encrypted_flow_data": "AAAA"},
        {"encrypted_aes_key": "AAAA", "initial_vector": "", "encrypted_flow_data": "AAAAAAAAAAAAAAAAAAAAAAAAAAAA"},
        {"encrypted_aes_key": "AAAA", "initial_vector": "AAAA", "encrypted_flow_data": "AAAA"},
    ],
)
def test_rejects_malformed_bodies(keys, body):
    _, _, private_key = keys
    with pytest.raises(FlowCryptoError):
        decrypt_request(body, private_key)


def test_rejects_a_decrypted_payload_that_is_not_a_json_object(keys):
    _, public_pem, private_key = keys
    public_key = serialization.load_pem_public_key(public_pem.encode())
    aes_key = os.urandom(16)
    iv = os.urandom(12)
    encrypted_key = public_key.encrypt(
        aes_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    data = AESGCM(aes_key).encrypt(iv, json.dumps(["not", "an", "object"]).encode(), None)
    body = {
        "encrypted_aes_key": base64.b64encode(encrypted_key).decode(),
        "encrypted_flow_data": base64.b64encode(data).decode(),
        "initial_vector": base64.b64encode(iv).decode(),
    }
    with pytest.raises(FlowCryptoError):
        decrypt_request(body, private_key)


def test_load_private_key_rejects_a_non_pem_value():
    with pytest.raises(ValueError):
        load_private_key("not a key")


def test_load_private_key_rejects_keys_below_2048_bits():
    small = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    pem = small.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    with pytest.raises(FlowCryptoError, match="2048"):
        load_private_key(pem)


def test_load_private_key_accepts_a_2048_bit_key(keys):
    private_pem, _, _ = keys
    assert load_private_key(private_pem).key_size == 2048
