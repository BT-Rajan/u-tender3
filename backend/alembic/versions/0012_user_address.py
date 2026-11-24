"""Store the address a WhatsApp registrant gives on the registration Flow.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-24

Additive: a nullable column on users. Accounts made before this migration have no address.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("address", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "address")
