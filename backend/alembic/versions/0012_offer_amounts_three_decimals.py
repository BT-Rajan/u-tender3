"""Bid amounts keep three decimal places (KWD fils).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-23

utender2 stored bids as DECIMAL(15,3). u-tender3 stored DECIMAL(12,2), which would
round imported bids. This widens offers, offer_revisions and award_records amounts
to DECIMAL(15,3). Widening loses no data. Downgrade narrows back to DECIMAL(12,2),
which fails if any amount has a fraction of a fils or a value above 10 digits.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

TABLES = ("offers", "offer_revisions", "award_records")


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "amount",
                existing_type=sa.Numeric(12, 2),
                type_=sa.Numeric(15, 3),
                existing_nullable=False,
            )


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "amount",
                existing_type=sa.Numeric(15, 3),
                type_=sa.Numeric(12, 2),
                existing_nullable=False,
            )
