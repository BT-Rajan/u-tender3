"""Timestamps keep microseconds on MySQL.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-25

Plain MySQL DATETIME drops fractions of a second. Ordering by submission time,
or by the newest link or code, then ties for writes made in the same second.
This widens every DATETIME column to DATETIME(6) and keeps its nullability and
default. Downgrade returns to whole seconds. Existing values are truncated at
that point, so only the fractions are lost.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012b"
branch_labels = None
depends_on = None


def _datetime_columns():
    inspector = sa.inspect(op.get_bind())
    for table in inspector.get_table_names():
        for column in inspector.get_columns(table):
            if isinstance(column["type"], sa.DateTime):
                yield table, column


def _modify(table: str, column: dict, fsp: int) -> None:
    null = "NULL" if column["nullable"] else "NOT NULL"
    default = column.get("default")
    default_sql = f" DEFAULT {default}" if default and "CURRENT_TIMESTAMP" in str(default).upper() else ""
    op.execute(
        f"ALTER TABLE `{table}` MODIFY `{column['name']}` DATETIME({fsp}) {null}{default_sql}"
        if fsp
        else f"ALTER TABLE `{table}` MODIFY `{column['name']}` DATETIME {null}{default_sql}"
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    for table, column in list(_datetime_columns()):
        _modify(table, column, 6)


def downgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    for table, column in list(_datetime_columns()):
        _modify(table, column, 0)
