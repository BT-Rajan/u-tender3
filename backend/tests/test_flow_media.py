"""Checks for files a WhatsApp Flow uploads. The encrypting helper follows Meta's media upload steps."""

import base64
import hashlib
import hmac
import os

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.services.flow_media import FlowMediaError, decrypt_flow_media, download_cdn_file


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _encrypt_like_meta(plaintext: bytes):
    """Return (cdn_file, encryption_metadata) the way Meta stores an upload."""
    key, mac_key, iv = os.urandom(32), os.urandom(32), os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    mac = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()[:10]
    cdn_file = ciphertext + mac
    metadata = {
        "encryption_key": _b64(key),
        "hmac_key": _b64(mac_key),
        "iv": _b64(iv),
        "encrypted_hash": _b64(hashlib.sha256(cdn_file).digest()),
        "plaintext_hash": _b64(hashlib.sha256(plaintext).digest()),
    }
    return cdn_file, metadata


def test_a_file_round_trips_through_the_checks():
    plaintext = b"%PDF-1.4 tender drawings " * 500
    cdn_file, metadata = _encrypt_like_meta(plaintext)

    assert decrypt_flow_media(cdn_file, metadata) == plaintext


def test_a_changed_byte_in_the_encrypted_file_is_refused():
    cdn_file, metadata = _encrypt_like_meta(b"drawing")
    tampered = bytes([cdn_file[0] ^ 0xFF]) + cdn_file[1:]

    with pytest.raises(FlowMediaError):
        decrypt_flow_media(tampered, metadata)


def test_a_wrong_plaintext_hash_is_refused():
    cdn_file, metadata = _encrypt_like_meta(b"drawing")
    metadata["plaintext_hash"] = _b64(hashlib.sha256(b"something else").digest())

    with pytest.raises(FlowMediaError):
        decrypt_flow_media(cdn_file, metadata)


def test_missing_keys_are_refused_without_a_crash():
    cdn_file, metadata = _encrypt_like_meta(b"drawing")
    del metadata["hmac_key"]

    with pytest.raises(FlowMediaError):
        decrypt_flow_media(cdn_file, metadata)


def test_only_secure_links_are_downloaded():
    with pytest.raises(FlowMediaError):
        download_cdn_file("http://example.invalid/file")
