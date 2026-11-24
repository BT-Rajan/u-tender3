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


_INDEX = "ix_whatsapp_identities_user_id"
_TMP_INDEX = "ix_whatsapp_identities_user_id_tmp"


def _swap_user_id_index(unique: bool) -> None:
    """Replace the user_id index with one of the requested uniqueness.

    MySQL/MariaDB will not drop an index that a foreign key relies on, and
    the user_id foreign key relies on this one. So the replacement index is
    created first under a temporary name (the foreign key stays covered
    throughout), the old index is dropped, and the new one takes the real
    name. SQLite cannot rename indexes, so there the new index is simply
    created after the drop.
    """
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.create_index(_TMP_INDEX, "whatsapp_identities", ["user_id"], unique=unique)
        op.drop_index(_INDEX, table_name="whatsapp_identities")
        op.execute(f"ALTER TABLE whatsapp_identities RENAME INDEX {_TMP_INDEX} TO {_INDEX}")
    else:
        op.drop_index(_INDEX, table_name="whatsapp_identities")
        op.create_index(_INDEX, "whatsapp_identities", ["user_id"], unique=unique)


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(255), nullable=True)
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=True)

    _swap_user_id_index(unique=True)


def downgrade() -> None:
    _swap_user_id_index(unique=False)

    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=False)
        batch.alter_column("email", existing_type=sa.String(255), nullable=False)
