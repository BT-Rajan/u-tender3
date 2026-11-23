"""WhatsApp notifications: new notification types, and the Meta template approval table.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-23

- notifications.type is a MySQL ENUM. It gains verification_rejected,
  owner_verification_rejected and tender_published. Existing values are kept as they are.
- whatsapp_template_status records Meta's review state per template and language.

Downgrade removes the table and narrows the ENUM back. On MySQL it fails if any notification still
uses one of the three new types, so clear or convert those rows first.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# Every value the ENUM held after 0006, plus the three new ones.
_EXISTING = (
    "document_rejected", "document_approved", "verification_activated", "payment_activated",
    "payment_failed", "payment_override_granted", "payment_override_revoked", "contractor_suspended",
    "contractor_reactivated", "document_expiring", "tender_amendment", "drawing_revised",
    "clarification_asked", "clarification_answered", "bid_submitted", "bid_revised", "bid_withdrawn",
    "deadline_approaching", "tender_closed", "evaluation_ready", "award_won", "award_lost",
    "tender_cancelled", "tender_no_award", "owner_verification_activated", "owner_document_rejected",
    "owner_document_approved", "owner_suspended", "owner_reactivated", "project_suspended",
    "project_reactivated", "offer_suspended", "offer_reactivated",
)
_NEW = ("verification_rejected", "owner_verification_rejected", "tender_published")


def _enum(values: tuple[str, ...]) -> str:
    return "ENUM(" + ",".join(f"'{v}'" for v in values) + ") NOT NULL"


def upgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.execute("ALTER TABLE notifications MODIFY COLUMN type " + _enum(_EXISTING + _NEW))

    op.create_table(
        "whatsapp_template_status",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("name", "language", name="uq_whatsapp_template_name_language"),
    )


def downgrade() -> None:
    op.drop_table("whatsapp_template_status")
    if op.get_bind().dialect.name == "mysql":
        op.execute("ALTER TABLE notifications MODIFY COLUMN type " + _enum(_EXISTING))
