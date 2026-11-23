import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.document_upload import DocumentUploadLink

# Error codes are stable so the upload page can show a fixed message for each.
# The page never says whether a token exists, only that the link can't be used.
LINK_INVALID = "invalid"  # not found, expired, used, or revoked: one answer for all four
LINK_LOCKED = "locked"  # too many wrong codes
CODE_WRONG = "wrong_code"

MESSAGES = {
    LINK_INVALID: "This upload link is no longer valid. Send any message to U-Tender to get a new one.",
    LINK_LOCKED: "Too many wrong codes. Send any message to U-Tender to get a new link.",
    CODE_WRONG: "That code is not right. Check the code in your WhatsApp message.",
}


class UploadLinkError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(MESSAGES[code])
        self.code = code
        self.message = MESSAGES[code]


@dataclass(frozen=True)
class IssuedUploadLink:
    link_id: str
    token: str  # raw token: only ever placed in the message link, never stored
    code: str  # raw one-time code: only ever placed in its own message, never stored
    expires_at: datetime


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _code_hash(token: str, code: str) -> str:
    # The code is bound to its own token, so a code from one link can't open another.
    return _sha256(f"{token}:{code}")


def issue_upload_link(db: Session, *, user_id: str, requirement_id: str, now: datetime) -> IssuedUploadLink:
    """Issue a fresh link for one requirement, replacing any earlier unused link for it.

    Only the newest link works. Anything issued earlier for the same requirement is
    revoked here, so a forwarded old link stops working as soon as a new one is sent.
    """
    settings = get_settings()
    for stale in db.scalars(
        select(DocumentUploadLink).where(
            DocumentUploadLink.user_id == user_id,
            DocumentUploadLink.requirement_id == requirement_id,
            DocumentUploadLink.used_at.is_(None),
            DocumentUploadLink.revoked_at.is_(None),
        )
    ).all():
        stale.revoked_at = now

    token = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = now + timedelta(minutes=settings.upload_link_ttl_minutes)
    link = DocumentUploadLink(
        token_hash=_sha256(token),
        code_hash=_code_hash(token, code),
        user_id=user_id,
        requirement_id=requirement_id,
        expires_at=expires_at,
    )
    db.add(link)
    db.commit()
    return IssuedUploadLink(link_id=link.id, token=token, code=code, expires_at=expires_at)


def verify_upload_link(db: Session, *, token: str, code: str, now: datetime) -> DocumentUploadLink:
    """Check a token and its code. Returns the link when both are right; raises UploadLinkError otherwise.

    Every wrong code is counted. After upload_link_max_wrong_codes the link is
    revoked, so a guessed token can't be brute-forced through the code.
    """
    settings = get_settings()
    if not token or not code:
        raise UploadLinkError(LINK_INVALID)

    link = db.scalar(select(DocumentUploadLink).where(DocumentUploadLink.token_hash == _sha256(token)))
    if link is None or link.used_at is not None or link.revoked_at is not None or link.expires_at <= now:
        raise UploadLinkError(LINK_INVALID)
    if link.wrong_code_count >= settings.upload_link_max_wrong_codes:
        raise UploadLinkError(LINK_LOCKED)

    if not hmac.compare_digest(link.code_hash, _code_hash(token, code.strip())):
        link.wrong_code_count += 1
        if link.wrong_code_count >= settings.upload_link_max_wrong_codes:
            link.revoked_at = now
            db.commit()
            raise UploadLinkError(LINK_LOCKED)
        db.commit()
        raise UploadLinkError(CODE_WRONG)

    return link


def consume_upload_link(db: Session, link: DocumentUploadLink, *, now: datetime) -> None:
    """Burn a link after its file has been accepted. A second use is refused."""
    link.used_at = now
    db.commit()
