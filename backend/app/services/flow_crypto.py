import base64
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MIN_RSA_KEY_BITS = 2048
ALLOWED_AES_KEY_BYTES = (16, 24, 32)


class FlowCryptoError(Exception):
    """The request cannot be decrypted with this key, or is not a Flow request.

    The caller maps it to 421 so WhatsApp refetches the key and retries.
    """


@dataclass(frozen=True)
class DecryptedFlowRequest:
    payload: dict[str, Any]
    aes_key: bytes
    iv: bytes


def load_private_key(pem: str) -> rsa.RSAPrivateKey:
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise FlowCryptoError("The Flow private key must be RSA.")
    if key.key_size < MIN_RSA_KEY_BITS:
        raise FlowCryptoError(f"The Flow private key must be at least {MIN_RSA_KEY_BITS} bits.")
    return key


def _b64decode(value: Any) -> bytes | None:
    if not isinstance(value, str):
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        return None


def decrypt_request(body: dict[str, Any], private_key: rsa.RSAPrivateKey) -> DecryptedFlowRequest:
    """Decrypt a Flow data-endpoint request.

    The body carries encrypted_aes_key (RSA-OAEP/SHA-256 under our public key),
    initial_vector, and encrypted_flow_data (AES-GCM ciphertext with the 16-byte
    tag appended).
    """
    encrypted_key = _b64decode(body.get("encrypted_aes_key"))
    iv = _b64decode(body.get("initial_vector"))
    data = _b64decode(body.get("encrypted_flow_data"))

    if encrypted_key is None or not iv or data is None or len(data) <= 16:
        raise FlowCryptoError("The request is not an encrypted Flow request.")

    try:
        aes_key = private_key.decrypt(
            encrypted_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
    except ValueError as exc:
        raise FlowCryptoError("The request was not encrypted for this key.") from exc

    if len(aes_key) not in ALLOWED_AES_KEY_BYTES:
        raise FlowCryptoError("The request was not encrypted for this key.")

    try:
        plaintext = AESGCM(aes_key).decrypt(iv, data, None)
        payload = json.loads(plaintext)
    except (InvalidTag, ValueError) as exc:
        raise FlowCryptoError("The request could not be decrypted.") from exc

    if not isinstance(payload, dict):
        raise FlowCryptoError("The request could not be decrypted.")

    return DecryptedFlowRequest(payload=payload, aes_key=aes_key, iv=iv)


def encrypt_response(response: dict[str, Any], aes_key: bytes, iv: bytes) -> str:
    """Encrypt a reply with the request's AES key and its IV with every bit flipped.

    Returns base64 text, which is what the endpoint writes back as text/plain.
    """
    flipped_iv = bytes(byte ^ 0xFF for byte in iv)
    plaintext = json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode()
    ciphertext_and_tag = AESGCM(aes_key).encrypt(flipped_iv, plaintext, None)
    return base64.b64encode(ciphertext_and_tag).decode()


def generate_key_pair(key_size: int = 2048) -> tuple[str, str]:
    """A fresh RSA key pair as (private_pem, public_pem). Used by setup tooling and tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return private_pem, public_pem


def new_aes_key() -> bytes:
    return os.urandom(16)
