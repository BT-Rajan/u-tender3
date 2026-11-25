from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required, no default. The app refuses to start without an explicit MySQL URL.
    database_url: str

    # Required, no default. Must be random and at least 32 characters.
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 30

    # local: files live under storage_root, served through a signed backend
    # route. s3: boto3 presigned URLs. Switching is config-only.
    storage_backend: str = "local"  # "local" | "s3"
    storage_root: str = "./storage"
    # Required, no default. Must be random and at least 32 characters.
    storage_signing_secret: str

    s3_bucket_drawings: str = "project-drawings"
    s3_bucket_documents: str = "contractor-documents"
    s3_bucket_owner_documents: str = "owner-documents"
    s3_region: str | None = None
    s3_endpoint_url: str | None = None  # set for MinIO / S3-compatible hosts
    s3_object_prefix: str = ""  # optional key prefix, e.g. "prod/" to share a bucket across environments
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    # Fallback signed-URL lifetime for callers with no business-rule-driven
    # expiry of their own (drawings use drawing_url_expiry_seconds instead,
    # tied to the bid deadline, per spec §2.14's "do not rely solely on bid
    # deadline if post-close access is intentionally permitted" note).
    signed_url_default_expiry_seconds: int = 60 * 60 * 24  # 24h

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_id_monthly: str | None = None
    stripe_price_id_annual: str | None = None

    resend_api_key: str | None = None
    email_from: str = "U-Tender <notifications@u-tender.example>"

    # Required, no default. Must be random and at least 32 characters.
    cron_secret: str
    app_url: str = "http://localhost:5173"  # frontend origin, used in email links
    api_url: str = "http://localhost:8000"  # this backend's own public origin

    cors_origins: str = "http://localhost:5173"

    # Matches the original app's raised Server Action body limit (25MB ->
    # 50MB) to accommodate zipped folders of drawings.
    max_upload_mb: int = 50

    # WhatsApp Cloud API. U-Tender uses its own Meta app, separate from
    # Cogzi. Every value below is a secret or an identifier that belongs in
    # the deployment's secret store, never in the database.
    whatsapp_enabled: bool = False
    whatsapp_app_secret: str | None = None  # signs webhooks and Flow requests
    whatsapp_verify_token: str | None = None  # GET subscription handshake
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_api_version: str = "v21.0"
    whatsapp_api_url: str = "https://graph.facebook.com"
    whatsapp_flow_private_key: str | None = None  # PEM, RSA >= 2048 bits; never leaves U-Tender
    whatsapp_outbox_max_attempts: int = 8
    whatsapp_message_retention_days: int = 30
    # Flow IDs issued by Meta when Cogzi publishes the Flows in
    # backend/whatsapp_flows/. Until these are set, the bot falls back to text.
    whatsapp_flow_id_registration: str | None = None
    whatsapp_flow_id_owner_dashboard: str | None = None
    whatsapp_flow_id_contractor_dashboard: str | None = None
    # Message templates for review decisions. These must be approved in Meta
    # Business Manager before they can be sent outside the 24-hour window.
    whatsapp_template_document_approved: str = "document_approved"
    whatsapp_template_document_rejected: str = "document_rejected"
    # Send a template only once Meta reports it approved. A template with no status on record is held, never sent blind.
    whatsapp_require_approved_templates: bool = True

    # Owners type deadlines in this zone. The database stores UTC.
    tender_timezone: str = "Asia/Kuwait"

    # Document upload. One rule set for web and WhatsApp uploads.
    document_max_mb: int = 10
    # Upload links are short-lived and single-use. Each one also needs the
    # one-time code sent in a separate WhatsApp message.
    upload_link_ttl_minutes: int = 20
    upload_link_max_wrong_codes: int = 5


MIN_SECRET_LENGTH = 32
PLACEHOLDER_MARKERS = ("change-me", "changeme", "replace-me", "change_me", "example")
SECRET_FIELDS = ("jwt_secret", "storage_signing_secret", "cron_secret")


class UnsafeConfigurationError(RuntimeError):
    """Raised at startup when a required setting is missing, a placeholder, or too weak."""


def _secret_problem(name: str, value: str) -> str | None:
    if len(value) < MIN_SECRET_LENGTH:
        return f"{name} must be at least {MIN_SECRET_LENGTH} characters"
    if any(marker in value.lower() for marker in PLACEHOLDER_MARKERS):
        return f"{name} still holds a placeholder value"
    return None


def validate_runtime_settings(settings: Settings) -> None:
    """Refuse to run on missing, placeholder or weak configuration. Every environment, no exceptions.

    Nothing is defaulted. A problem is reported with the names of the settings
    that need fixing, so the failure is explicit and the fix is obvious.
    """
    problems: list[str] = []

    if "change_me" in settings.database_url.lower():
        problems.append("database_url still holds a placeholder value")
    elif not settings.database_url.startswith("mysql+pymysql://"):
        problems.append("database_url must be a mysql+pymysql:// URL (MySQL or MariaDB only)")

    for name in SECRET_FIELDS:
        problem = _secret_problem(name, getattr(settings, name) or "")
        if problem:
            problems.append(problem)

    if settings.whatsapp_enabled:
        for name in (
            "whatsapp_app_secret",
            "whatsapp_verify_token",
            "whatsapp_access_token",
            "whatsapp_phone_number_id",
            "whatsapp_flow_private_key",
        ):
            if not getattr(settings, name):
                problems.append(f"{name} is required when whatsapp_enabled is true")

    if problems:
        raise UnsafeConfigurationError("Refusing to start: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
