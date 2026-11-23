"""WhatsApp foundation: identity mapping, Flow session state, message
event idempotency, and the outgoing-message outbox.

Purely additive: four new tables, nothing existing is altered. Downgrade
drops them, which removes WhatsApp operational history, so take a backup
first if a deployment has started receiving messages.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("wa_id", sa.String(32), nullable=False, unique=True),
        sa.Column("phone_e164", sa.String(20), nullable=False, unique=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_whatsapp_identities_user_id", "whatsapp_identities", ["user_id"])

    op.create_table(
        "whatsapp_message_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_key", sa.String(255), nullable=False, unique=True),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("provider_message_id", sa.String(128), nullable=True),
        sa.Column("wa_id", sa.String(32), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="received"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("received_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_whatsapp_message_events_provider_message_id", "whatsapp_message_events", ["provider_message_id"])
    op.create_index("ix_whatsapp_message_events_wa_id", "whatsapp_message_events", ["wa_id"])
    op.create_index("ix_whatsapp_message_events_status", "whatsapp_message_events", ["status"])

    op.create_table(
        "whatsapp_flow_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "identity_id",
            sa.String(36),
            sa.ForeignKey("whatsapp_identities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("flow_name", sa.String(64), nullable=False),
        sa.Column("flow_token_hash", sa.String(64), nullable=False),
        sa.Column("screen", sa.String(64), nullable=True),
        sa.Column("state_json", sa.JSON, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("flow_token_hash", name="uq_whatsapp_flow_token"),
    )
    op.create_index("ix_whatsapp_flow_sessions_identity_id", "whatsapp_flow_sessions", ["identity_id"])

    op.create_table(
        "whatsapp_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dedupe_key", sa.String(191), nullable=False, unique=True),
        sa.Column("recipient_wa_id", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("template_name", sa.String(128), nullable=True),
        sa.Column("params_json", sa.JSON, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime, nullable=False),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("provider_message_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_whatsapp_outbox_next_attempt_at", "whatsapp_outbox", ["next_attempt_at"])
    op.create_index("ix_whatsapp_outbox_status_next", "whatsapp_outbox", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_outbox_status_next", table_name="whatsapp_outbox")
    op.drop_index("ix_whatsapp_outbox_next_attempt_at", table_name="whatsapp_outbox")
    op.drop_table("whatsapp_outbox")

    op.drop_index("ix_whatsapp_flow_sessions_identity_id", table_name="whatsapp_flow_sessions")
    op.drop_table("whatsapp_flow_sessions")

    op.drop_index("ix_whatsapp_message_events_status", table_name="whatsapp_message_events")
    op.drop_index("ix_whatsapp_message_events_wa_id", table_name="whatsapp_message_events")
    op.drop_index("ix_whatsapp_message_events_provider_message_id", table_name="whatsapp_message_events")
    op.drop_table("whatsapp_message_events")

    op.drop_index("ix_whatsapp_identities_user_id", table_name="whatsapp_identities")
    op.drop_table("whatsapp_identities")
