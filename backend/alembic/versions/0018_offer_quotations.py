"""Create offer_quotations: a contractor's quotation file for a tender, linked to the offer once submitted."""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_quotations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("offer_id", sa.String(36), sa.ForeignKey("offers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "contractor_id",
            sa.String(36),
            sa.ForeignKey("contractor_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_offer_quotations_offer_id", "offer_quotations", ["offer_id"])
    op.create_index("ix_offer_quotations_project_id", "offer_quotations", ["project_id"])
    op.create_index("ix_offer_quotations_contractor_id", "offer_quotations", ["contractor_id"])


def downgrade() -> None:
    op.drop_table("offer_quotations")
