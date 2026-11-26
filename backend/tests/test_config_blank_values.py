"""A blank env line means "not set" for optional settings.

.env.example ships lines such as ``S3_ENDPOINT_URL=`` with no value. Without
this rule the empty string reaches boto3 and S3 storage fails to start.
"""

from app.config import Settings


def test_blank_optional_string_is_none(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("WHATSAPP_OTP_TEMPLATE", "   ")
    settings = Settings(_env_file=None)
    assert settings.s3_endpoint_url is None
    assert settings.whatsapp_otp_template is None


def test_blank_required_string_keeps_its_value(monkeypatch):
    # email_from is a plain str with a default, not an optional value.
    monkeypatch.setenv("EMAIL_FROM", "")
    settings = Settings(_env_file=None)
    assert settings.email_from == ""


def test_set_value_is_kept(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    settings = Settings(_env_file=None)
    assert settings.s3_endpoint_url == "http://minio:9000"
