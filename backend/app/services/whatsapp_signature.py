import hashlib
import hmac

SIGNATURE_PREFIX = "sha256="


# Meta signs every webhook and Flow data-endpoint request: the header is
# "sha256=" followed by HMAC-SHA256(app_secret, raw_body), hex-encoded. The
# check must run over the exact bytes received, before any JSON parsing, so
# whitespace or key-order changes can't slip past it.
def verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str | None) -> bool:
    if not app_secret or not signature_header or not signature_header.startswith(SIGNATURE_PREFIX):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(SIGNATURE_PREFIX + expected, signature_header)
