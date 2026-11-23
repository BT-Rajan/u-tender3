import pytest

from app.config import Settings, UnsafeConfigurationError, validate_runtime_settings


def _production(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "jwt_secret": "a-real-jwt-secret",
        "storage_signing_secret": "a-real-signing-secret",
        "cron_secret": "a-real-cron-secret",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_development_allows_default_secrets():
    validate_runtime_settings(Settings(_env_file=None))


def test_whatsapp_is_disabled_by_default():
    assert Settings(_env_file=None).whatsapp_enabled is False


def test_production_refuses_default_jwt_secret():
    with pytest.raises(UnsafeConfigurationError, match="jwt_secret"):
        validate_runtime_settings(_production(jwt_secret="change-me-in-production"))


def test_production_refuses_default_storage_signing_secret():
    with pytest.raises(UnsafeConfigurationError, match="storage_signing_secret"):
        validate_runtime_settings(_production(storage_signing_secret="change-me-in-production"))


def test_production_refuses_missing_cron_secret():
    with pytest.raises(UnsafeConfigurationError, match="cron_secret"):
        validate_runtime_settings(_production(cron_secret=None))


def test_production_with_whatsapp_requires_every_whatsapp_secret():
    with pytest.raises(UnsafeConfigurationError) as excinfo:
        validate_runtime_settings(_production(whatsapp_enabled=True))
    message = str(excinfo.value)
    for name in (
        "whatsapp_app_secret",
        "whatsapp_verify_token",
        "whatsapp_access_token",
        "whatsapp_phone_number_id",
        "whatsapp_flow_private_key",
    ):
        assert name in message


def test_production_with_whatsapp_and_all_secrets_starts():
    validate_runtime_settings(
        _production(
            whatsapp_enabled=True,
            whatsapp_app_secret="app-secret",
            whatsapp_verify_token="verify",
            whatsapp_access_token="token",
            whatsapp_phone_number_id="100",
            whatsapp_flow_private_key="-----BEGIN PRIVATE KEY-----",
        )
    )


def test_whatsapp_secrets_are_not_required_when_whatsapp_is_disabled():
    validate_runtime_settings(_production(whatsapp_enabled=False))
