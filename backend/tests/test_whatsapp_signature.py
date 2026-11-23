import hashlib
import hmac

from app.services.whatsapp_signature import verify_signature

SECRET = "app-secret"
BODY = b'{"object":"whatsapp_business_account","entry":[]}'


def _header(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_accepts_a_correct_signature():
    assert verify_signature(BODY, _header(BODY), SECRET) is True


def test_rejects_a_signature_made_with_another_secret():
    assert verify_signature(BODY, _header(BODY, "other-secret"), SECRET) is False


def test_rejects_a_tampered_body():
    assert verify_signature(BODY + b" ", _header(BODY), SECRET) is False


def test_rejects_a_reformatted_body_even_when_the_json_is_equal():
    # Whitespace changes must fail: the check is over the exact bytes received.
    reformatted = b'{ "object": "whatsapp_business_account", "entry": [] }'
    assert verify_signature(reformatted, _header(BODY), SECRET) is False


def test_rejects_a_missing_header():
    assert verify_signature(BODY, None, SECRET) is False


def test_rejects_an_empty_header():
    assert verify_signature(BODY, "", SECRET) is False


def test_rejects_a_header_without_the_sha256_prefix():
    bare = hmac.new(SECRET.encode(), BODY, hashlib.sha256).hexdigest()
    assert verify_signature(BODY, bare, SECRET) is False


def test_rejects_everything_when_no_app_secret_is_configured():
    assert verify_signature(BODY, _header(BODY, ""), None) is False
    assert verify_signature(BODY, _header(BODY, ""), "") is False
