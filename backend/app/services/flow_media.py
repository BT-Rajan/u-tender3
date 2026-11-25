"""Decrypt the files a WhatsApp Flow uploads (DocumentPicker).

Meta keeps each file encrypted on its CDN. The Flow request carries the keys in
encryption_metadata. The checks follow Meta's media upload reference:

1. The CDN file is the ciphertext followed by the first 10 bytes of HMAC-SHA256.
2. SHA-256 of the whole CDN file equals encrypted_hash.
3. HMAC-SHA256(hmac_key, iv + ciphertext) starts with those 10 bytes.
4. AES-256-CBC decrypts the ciphertext with iv, then PKCS#7 padding is removed.
5. SHA-256 of the plaintext equals plaintext_hash.

A file that fails any check is never stored.
"""

import base64
import binascii
import hashlib
import hmac
from collections.abc import Callable
from typing import Any

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# 25 MB, the largest file a Flow DocumentPicker accepts.
MAX_FILE_BYTES = 25 * 1024 * 1024
MAC_LENGTH = 10
AES_BLOCK = 16
DOWNLOAD_TIMEOUT_SECONDS = 60


class FlowMediaError(Exception):
    """The file could not be fetched or failed a check. It is not used."""


def _bytes_of(value: Any, length: int, what: str) -> bytes:
    try:
        raw = base64.b64decode(str(value), validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise FlowMediaError(f"{what} is not valid base64.") from exc
    if len(raw) != length:
        raise FlowMediaError(f"{what} has the wrong length.")
    return raw


def _digest_matches(digest: bytes, expected: str) -> bool:
    # Meta sends hashes as base64. Hex is accepted too, so a format difference doesn't block an upload.
    return expected == base64.b64encode(digest).decode() or expected.lower() == digest.hex()


def decrypt_flow_media(cdn_file: bytes, metadata: dict[str, Any]) -> bytes:
    """Check and decrypt one uploaded file. Raises FlowMediaError if any check fails."""
    try:
        encrypted_hash = str(metadata["encrypted_hash"])
        plaintext_hash = str(metadata["plaintext_hash"])
        iv = _bytes_of(metadata["iv"], AES_BLOCK, "iv")
        aes_key = _bytes_of(metadata["encryption_key"], 32, "encryption_key")
        mac_key = _bytes_of(metadata["hmac_key"], 32, "hmac_key")
    except KeyError as exc:
        raise FlowMediaError(f"The upload is missing {exc.args[0]}.") from exc

    if len(cdn_file) <= MAC_LENGTH:
        raise FlowMediaError("The uploaded file is empty.")
    if not _digest_matches(hashlib.sha256(cdn_file).digest(), encrypted_hash):
        raise FlowMediaError("The encrypted file does not match its hash.")

    ciphertext, mac = cdn_file[:-MAC_LENGTH], cdn_file[-MAC_LENGTH:]
    expected_mac = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()[:MAC_LENGTH]
    if not hmac.compare_digest(expected_mac, mac):
        raise FlowMediaError("The file's signature is wrong.")
    if not ciphertext or len(ciphertext) % AES_BLOCK:
        raise FlowMediaError("The encrypted file has the wrong length.")

    decryptor = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(AES_BLOCK * 8).unpadder()
    try:
        plaintext = unpadder.update(padded) + unpadder.finalize()
    except ValueError as exc:
        raise FlowMediaError("The file's padding is wrong.") from exc

    if not _digest_matches(hashlib.sha256(plaintext).digest(), plaintext_hash):
        raise FlowMediaError("The decrypted file does not match its hash.")
    return plaintext


def download_cdn_file(cdn_url: str) -> bytes:
    """Fetch the encrypted file from Meta's CDN, refusing anything too large or not https."""
    if not cdn_url.startswith("https://"):
        raise FlowMediaError("The upload link is not secure.")
    limit = MAX_FILE_BYTES + MAC_LENGTH + AES_BLOCK
    try:
        with httpx.Client(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=False) as client:
            with client.stream("GET", cdn_url) as response:
                if response.status_code != 200:
                    raise FlowMediaError("The uploaded file could not be downloaded.")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise FlowMediaError("The uploaded file is too large.")
                    chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise FlowMediaError("The uploaded file could not be downloaded.") from exc
    return b"".join(chunks)


FileFetcher = Callable[[str], bytes]
