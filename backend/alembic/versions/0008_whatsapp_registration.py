"""WhatsApp-only registration: accounts may exist without an email or password,
and a user may have at most one WhatsApp identity.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-23

Changes:
- users.email and users.password_hash become nullable. Existing rows keep their
  values, so existing web accounts are unaffected.
- whatsapp_identities.user_id becomes UNIQUE, so one user cannot hold two
  WhatsApp identities.

Downgrade restores NOT NULL. It fails if any WhatsApp-only account (NULL email
or password) exists, which is deliberate: the data can't be reconstructed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


INDEX = "ix_whatsapp_identities_user_id"
STAGING_INDEX = "tmp_whatsapp_identities_user_id"


def _replace_user_id_index(*, unique: bool) -> None:
    """Swap the user_id index for one with the wanted uniqueness.

    MySQL refuses to drop an index that a foreign key relies on. A second index on
    the same column is created first, so the foreign key always has one to use.
    """
    op.create_index(STAGING_INDEX, "whatsapp_identities", ["user_id"])
    op.drop_index(INDEX, table_name="whatsapp_identities")
    op.create_index(INDEX, "whatsapp_identities", ["user_id"], unique=unique)
    op.drop_index(STAGING_INDEX, table_name="whatsapp_identities")


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(255), nullable=True)
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=True)

    _replace_user_id_index(unique=True)


def downgrade() -> None:
    _replace_user_id_index(unique=False)

    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=False)
        batch.alter_column("email", existing_type=sa.String(255), nullable=False)
