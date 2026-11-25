"""Tender numbers: a six-digit reference for each published tender.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-25

Adds projects.reference_code with a unique constraint. Existing tenders keep NULL until
they are published again; NULL values never clash with each other.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("reference_code", sa.String(length=6), nullable=True))
    op.create_unique_constraint("uq_projects_reference_code", "projects", ["reference_code"])


def downgrade():
    op.drop_constraint("uq_projects_reference_code", "projects", type_="unique")
    op.drop_column("projects", "reference_code")
