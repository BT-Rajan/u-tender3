"""Configuration fails closed: no defaults, no environment switch, every run is checked."""

import pytest
from pydantic import ValidationError

from app.config import Settings, UnsafeConfigurationError, validate_runtime_settings

GOOD = "k7Qz1mV8pL3rT6wN9bH2cX5yF0dS4gJa"  # 32 characters, no placeholder marker
DATABASE = "mysql+pymysql://app_user:s3cret@127.0.0.1:3306/utender3"


def _settings(**overrides) -> Settings:
    values = {
        "database_url": DATABASE,
        "jwt_secret": GOOD,
        "storage_signing_secret": GOOD[::-1],
        "cron_secret": GOOD[:16] + GOOD[16:][::-1],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


REQUIRED_ENV = ("DATABASE_URL", "JWT_SECRET", "STORAGE_SIGNING_SECRET", "CRON_SECRET")


@pytest.fixture
def no_required_env(monkeypatch):
    """Settings also read the process environment, and the test run sets these. Clear them so a missing value is really missing."""
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)


def test_the_database_url_has_no_default(no_required_env):
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None, jwt_secret=GOOD, storage_signing_secret=GOOD, cron_secret=GOOD)


@pytest.mark.parametrize("name", ["jwt_secret", "storage_signing_secret", "cron_secret"])
def test_each_secret_has_no_default(name, no_required_env):
    values = {"database_url": DATABASE, "jwt_secret": GOOD, "storage_signing_secret": GOOD, "cron_secret": GOOD}
    values.pop(name)
    with pytest.raises(ValidationError, match=name):
        Settings(_env_file=None, **values)


def test_a_complete_configuration_passes():
    validate_runtime_settings(_settings())


def test_whatsapp_is_disabled_by_default():
    assert _settings().whatsapp_enabled is False


def test_a_placeholder_secret_is_refused():
    with pytest.raises(UnsafeConfigurationError, match="jwt_secret still holds a placeholder"):
        validate_runtime_settings(_settings(jwt_secret="change-me-" + "x" * 30))


def test_a_short_secret_is_refused():
    with pytest.raises(UnsafeConfigurationError, match="storage_signing_secret must be at least 32 characters"):
        validate_runtime_settings(_settings(storage_signing_secret="too-short"))


def test_a_placeholder_database_url_is_refused():
    with pytest.raises(UnsafeConfigurationError, match="database_url still holds a placeholder"):
        validate_runtime_settings(_settings(database_url="mysql+pymysql://CHANGE_ME:CHANGE_ME@127.0.0.1:3306/utender"))


def test_a_non_mysql_database_url_is_refused():
    with pytest.raises(UnsafeConfigurationError, match="mysql\\+pymysql"):
        validate_runtime_settings(_settings(database_url="sqlite:///./dev.db"))


def test_whatsapp_enabled_requires_every_whatsapp_secret():
    with pytest.raises(UnsafeConfigurationError) as excinfo:
        validate_runtime_settings(_settings(whatsapp_enabled=True))
    message = str(excinfo.value)
    for name in (
        "whatsapp_app_secret",
        "whatsapp_verify_token",
        "whatsapp_access_token",
        "whatsapp_phone_number_id",
        "whatsapp_flow_private_key",
    ):
        assert name in message


def test_whatsapp_enabled_with_every_secret_passes():
    validate_runtime_settings(
        _settings(
            whatsapp_enabled=True,
            whatsapp_app_secret="app-secret",
            whatsapp_verify_token="verify",
            whatsapp_access_token="token",
            whatsapp_phone_number_id="100",
            whatsapp_flow_private_key="-----BEGIN PRIVATE KEY-----",
        )
    )


def test_whatsapp_secrets_are_not_required_when_whatsapp_is_disabled():
    validate_runtime_settings(_settings(whatsapp_enabled=False))


def test_there_is_no_environment_switch_that_relaxes_the_checks():
    assert "app_env" not in Settings.model_fields
