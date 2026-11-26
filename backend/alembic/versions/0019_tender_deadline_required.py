"""Make projects.bid_deadline required. Every tender now has a deadline, drafts included, so the
database matches the standard (and the live column already rejected nulls)."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.execute("ALTER TABLE projects MODIFY bid_deadline DATETIME NOT NULL")


def downgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.execute("ALTER TABLE projects MODIFY bid_deadline DATETIME NULL")
