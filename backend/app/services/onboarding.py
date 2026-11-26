"""Contractor onboarding helpers: one-time WhatsApp codes, 24-hour portal invitations, and the WhatsApp
message that carries the web portal link.

Codes and invitation tokens are stored only as HMAC hashes. A code is locked after too many wrong tries.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.onboarding import OTP_PURPOSES, OtpCode, PortalInvite
from app.models.whatsapp import WhatsAppIdentity
from app.services import whatsapp_outbox

CODE_LENGTH = 6


class OnboardingError(Exception):
    """A user-facing error: the message is shown to the person."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def normalize_phone(raw: str) -> str:
    """Digits only, with the country code (for example 919344404069). WhatsApp uses the same form."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 8 or len(digits) > 15:
        raise OnboardingError("Enter the WhatsApp number with its country code, for example 919344404069.")
    return digits


def _keyed(*parts: str) -> str:
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, "|".join(parts).encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def create_code(db: Session, phone: str, purpose: str, *, now: datetime) -> str:
    """A new code for this number. Earlier unused codes for the same purpose stop working."""
    if purpose not in OTP_PURPOSES:
        raise OnboardingError("Unknown code purpose.")
    code = new_code()
    for old in db.scalars(select(OtpCode).where(OtpCode.phone == phone, OtpCode.purpose == purpose, OtpCode.consumed_at.is_(None))).all():
        old.consumed_at = now
    db.add(
        OtpCode(
            phone=phone,
            purpose=purpose,
            code_hash=_keyed("otp", purpose, phone, code),
            expires_at=now + timedelta(minutes=get_settings().otp_ttl_minutes),
        )
    )
    db.flush()
    return code


def check_code(db: Session, phone: str, purpose: str, code: str, *, now: datetime) -> bool:
    """True once for the right code while it is in date. A wrong code counts toward the attempt limit."""
    row = db.scalar(
        select(OtpCode)
        .where(OtpCode.phone == phone, OtpCode.purpose == purpose, OtpCode.consumed_at.is_(None))
        .order_by(OtpCode.created_at.desc())
    )
    if row is None or row.expires_at <= now or row.attempts >= get_settings().otp_max_attempts:
        return False
    if not hmac.compare_digest(row.code_hash, _keyed("otp", purpose, phone, (code or "").strip())):
        row.attempts += 1
        db.commit()
        return False
    row.consumed_at = now
    db.commit()
    return True


def send_code(phone: str, code: str) -> None:
    """Send the code on WhatsApp. Outside the 24-hour customer window WhatsApp only accepts an approved template."""
    from app.services.whatsapp_client import WhatsAppCloudClient

    settings = get_settings()
    if not settings.whatsapp_enabled:
        raise OnboardingError("WhatsApp is not connected yet, so codes cannot be sent.")
    client = WhatsAppCloudClient.from_settings(settings)
    try:
        if settings.whatsapp_otp_template:
            client.send_template(
                phone,
                settings.whatsapp_otp_template,
                "en",
                [{"type": "body", "parameters": [{"type": "text", "text": code}]}],
            )
        else:
            client.send_text(phone, f"Your U-Tender code is {code}. It expires in {settings.otp_ttl_minutes} minutes. Do not share it.")
    finally:
        client.close()


def create_invite(db: Session, user_id: str, *, now: datetime) -> str:
    """A 24-hour, single-use link for finishing sign-up on the web. Returns the full link."""
    raw = secrets.token_urlsafe(32)
    for old in db.scalars(select(PortalInvite).where(PortalInvite.user_id == user_id, PortalInvite.used_at.is_(None))).all():
        old.used_at = now
    db.add(
        PortalInvite(
            user_id=user_id,
            token_hash=_keyed("invite", raw),
            expires_at=now + timedelta(hours=get_settings().invite_ttl_hours),
        )
    )
    db.flush()
    return f"{get_settings().app_url.rstrip('/')}/contractor/join?token={raw}"


def use_invite(db: Session, raw: str, *, now: datetime) -> str | None:
    """The user id for a valid, unused invitation, marked as used. None when it is missing, expired or used."""
    if not raw:
        return None
    row = db.scalar(select(PortalInvite).where(PortalInvite.token_hash == _keyed("invite", raw)))
    if row is None or row.used_at is not None or row.expires_at <= now:
        return None
    row.used_at = now
    db.flush()
    return row.user_id


def queue_portal_message(db: Session, wa_id: str, invite_link: str, *, now: datetime, dedupe_suffix: str) -> None:
    """The message that follows a WhatsApp sign-up: the web link to finish, and how to log in later."""
    body = (
        "Your account is created. Finish your profile and subscribe on the U-Tender web portal: "
        f"{invite_link}\n\nThe link works for 24 hours. After that, log in with your email and password at "
        f"{get_settings().app_url.rstrip('/')}/login."
    )
    whatsapp_outbox.enqueue(
        db,
        dedupe_key=f"{whatsapp_outbox.PORTAL_LINK_PREFIX}{dedupe_suffix}",
        recipient_wa_id=wa_id,
        kind=whatsapp_outbox.KIND_TEXT,
        now=now,
        params={"body": body},
    )
