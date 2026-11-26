"""Remove Stripe, add admin-set trial periods, and store settings an admin can edit.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-26

- contractor_profiles gets trial_until (a trial set by an admin; offers allowed until then).
- A contractor whose Stripe subscription still covered today keeps access: its period end is copied into paid_until.
- The Stripe columns are dropped (stripe_customer_id, stripe_subscription_id, subscription_status,
  subscription_current_period_end).
- app_settings holds the MyFatoorah keys and the OTP template name, edited by an admin.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

SUBSCRIPTION_STATUS_VALUES = (
    "not_started",
    "pending",
    "trialing",
    "active",
    "past_due",
    "failed",
    "canceled",
    "expired",
    "waived",
)


def upgrade():
    op.add_column("contractor_profiles", sa.Column("trial_until", mysql.DATETIME(fsp=6), nullable=True))
    op.execute(
        "UPDATE contractor_profiles SET paid_until = subscription_current_period_end "
        "WHERE paid_until IS NULL AND subscription_status IN ('active', 'trialing') "
        "AND subscription_current_period_end IS NOT NULL"
    )
    op.drop_column("contractor_profiles", "stripe_customer_id")
    op.drop_column("contractor_profiles", "stripe_subscription_id")
    op.drop_column("contractor_profiles", "subscription_current_period_end")
    op.drop_column("contractor_profiles", "subscription_status")

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=True),
    )


def downgrade():
    op.drop_table("app_settings")
    op.add_column("contractor_profiles", sa.Column("subscription_status", sa.Enum(*SUBSCRIPTION_STATUS_VALUES, name="subscriptionstatus"), nullable=True))
    op.add_column("contractor_profiles", sa.Column("subscription_current_period_end", mysql.DATETIME(fsp=6), nullable=True))
    op.add_column("contractor_profiles", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))
    op.add_column("contractor_profiles", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
    op.drop_column("contractor_profiles", "trial_until")
