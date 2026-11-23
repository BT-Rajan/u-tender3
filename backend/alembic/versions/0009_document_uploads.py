"""Secure document upload links and document version history.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-23

Additive only: two new tables. The existing contractor_documents and
owner_documents tables are unchanged. Downgrade drops the upload-link and
version tables, so audit history is lost. Back up first if uploads have happened.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_upload_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "requirement_id",
            sa.String(36),
            sa.ForeignKey("document_requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("used_at", sa.DateTime, nullable=True),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.Column("wrong_code_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_document_upload_links_user_id", "document_upload_links", ["user_id"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_kind", sa.String(16), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "requirement_id",
            sa.String(36),
            sa.ForeignKey("document_requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("uploaded_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("superseded_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("file_path", name="uq_document_version_path"),
    )
    op.create_index("ix_document_versions_user_id", "document_versions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_document_versions_user_id", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("ix_document_upload_links_user_id", table_name="document_upload_links")
    op.drop_table("document_upload_links")
