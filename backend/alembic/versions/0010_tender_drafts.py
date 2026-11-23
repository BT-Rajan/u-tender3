"""Tender drafts: a project can be saved before its bid deadline is known.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-23

Makes projects.bid_deadline nullable. Existing rows all have a deadline, so nothing
changes for them. Publishing still requires a future deadline. Downgrade restores
NOT NULL and fails if any draft without a deadline exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.alter_column("bid_deadline", existing_type=sa.DateTime(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.alter_column("bid_deadline", existing_type=sa.DateTime(), nullable=False)
