"""Settings an admin edits in the app instead of the server's .env file.

A value saved here overrides the .env value. Clearing it falls back to .env.
Secret values are encrypted at rest with a key derived from jwt_secret, so rotating jwt_secret means the
admin enters the secrets again. Secret values are never written to the audit log.
"""

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.app_setting import AppSetting
from app.services.audit import log_action

# key -> (name of the .env setting it overrides, whether the value is secret)
EDITABLE: dict[str, tuple[str, bool]] = {
    "myfatoorah_api_key": ("myfatoorah_api_key", True),
    "myfatoorah_webhook_secret": ("myfatoorah_webhook_secret", True),
    "myfatoorah_base_url": ("myfatoorah_base_url", False),
    "whatsapp_otp_template": ("whatsapp_otp_template", False),
}
DEFAULT_MYFATOORAH_BASE_URL = "https://apitest.myfatoorah.com"


class SettingError(ValueError):
    """An admin entered a value that cannot be used. The message is shown to the admin."""


@dataclass(frozen=True)
class MyFatoorahConfig:
    api_key: str | None
    base_url: str
    webhook_secret: str | None


def _fernet() -> Fernet:
    digest = hashlib.sha256(("app-settings|" + get_settings().jwt_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # Written under an older jwt_secret. Treat as not set so the .env value (or nothing) is used.
        return None


def get_value(db: Session, key: str) -> str | None:
    """The effective value: the admin's saved value if there is one, otherwise the .env value."""
    if key not in EDITABLE:
        raise KeyError(key)
    row = db.get(AppSetting, key)
    if row is not None and row.value:
        return _decrypt(row.value) if row.is_secret else row.value
    env_value = getattr(get_settings(), EDITABLE[key][0])
    return env_value or None


def _source(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    if row is not None and row.value and (not row.is_secret or _decrypt(row.value)):
        return "admin"
    return "env" if get_value(db, key) else "none"


def describe(db: Session, key: str) -> dict:
    """What the admin screen shows. A secret is never returned, only whether it is set and its last four characters."""
    value = get_value(db, key)
    source = _source(db, key)
    if EDITABLE[key][1]:
        hint = f"...{value[-4:]}" if value and len(value) >= 8 else ("set" if value else None)
        return {"configured": bool(value), "hint": hint, "source": source}
    return {"value": value, "source": source}


def myfatoorah_config(db: Session) -> MyFatoorahConfig:
    return MyFatoorahConfig(
        api_key=get_value(db, "myfatoorah_api_key"),
        base_url=(get_value(db, "myfatoorah_base_url") or DEFAULT_MYFATOORAH_BASE_URL).rstrip("/"),
        webhook_secret=get_value(db, "myfatoorah_webhook_secret"),
    )


def set_value(db: Session, key: str, value: str | None, *, actor_id: str, now: datetime) -> None:
    """Save a value, or clear it with an empty value so the .env value applies again."""
    if key not in EDITABLE:
        raise SettingError("Unknown setting.")
    secret = EDITABLE[key][1]
    cleaned = (value or "").strip() or None
    if cleaned and key == "myfatoorah_base_url" and not cleaned.startswith("https://"):
        raise SettingError("The MyFatoorah address must start with https://.")
    if cleaned and key == "whatsapp_otp_template" and not all(ch.isalnum() or ch == "_" for ch in cleaned):
        raise SettingError("A template name uses only letters, numbers and underscores.")

    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key)
        db.add(row)
    previous_was_set = bool(row.value)
    row.is_secret = secret
    if cleaned is None:
        row.value = None
    elif secret:
        row.value = _fernet().encrypt(cleaned.encode()).decode()
    else:
        row.value = cleaned
    row.updated_by = actor_id
    row.updated_at = now
    db.commit()

    if secret:
        previous_text = "set" if previous_was_set else "not set"
        new_text = "set" if cleaned else "cleared"
    else:
        previous_text = None
        new_text = cleaned or "cleared"
    log_action(
        db,
        actor_id=actor_id,
        action="setting.update",
        target_type="app_setting",
        target_id=key,
        previous_value=previous_text,
        new_value=new_text,
    )
