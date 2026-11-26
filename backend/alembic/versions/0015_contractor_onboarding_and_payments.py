"""Contractor onboarding details, MyFatoorah payments, plans, one-time codes and portal invitations.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-26

Adds the onboarding columns to contractor_profiles and creates four tables. The Stripe columns are left
in place so existing rows keep their history; no code writes to them any more.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contractor_profiles", sa.Column("business_address", sa.String(length=500), nullable=True))
    op.add_column("contractor_profiles", sa.Column("website", sa.String(length=255), nullable=True))
    op.add_column("contractor_profiles", sa.Column("business_email", sa.String(length=255), nullable=True))
    op.add_column("contractor_profiles", sa.Column("business_registration_id", sa.String(length=100), nullable=True))
    op.add_column("contractor_profiles", sa.Column("trades", sa.JSON(), nullable=True))
    op.add_column("contractor_profiles", sa.Column("onboarding_completed_at", mysql.DATETIME(fsp=6), nullable=True))
    op.add_column("contractor_profiles", sa.Column("paid_until", mysql.DATETIME(fsp=6), nullable=True))
    op.add_column("contractor_profiles", sa.Column("activation_due_at", mysql.DATETIME(fsp=6), nullable=True))

    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("activation_fee", sa.Numeric(12, 3), nullable=False),
        sa.Column("monthly_fee", sa.Numeric(12, 3), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), server_default=sa.func.now(), nullable=True),
    )

    op.create_table(
        "payment_invoices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("contractor_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False, unique=True),
        sa.Column("myfatoorah_invoice_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("payment_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("covers_from", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("covers_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("paid_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_payment_invoices_contractor_id", "payment_invoices", ["contractor_id"])
    op.create_index("ix_payment_invoices_status", "payment_invoices", ["status"])

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("consumed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_otp_codes_phone", "otp_codes", ["phone"])

    op.create_table(
        "portal_invites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("used_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_portal_invites_user_id", "portal_invites", ["user_id"])


def downgrade():
    # Dropping a table also drops its indexes. MySQL refuses to drop an index that a foreign key uses,
    # so the indexes are not dropped one by one first.
    op.drop_table("portal_invites")
    op.drop_table("otp_codes")
    op.drop_table("payment_invoices")
    op.drop_table("subscription_plans")
    for column in ["activation_due_at", "paid_until", "onboarding_completed_at", "trades",
                   "business_registration_id", "business_email", "website", "business_address"]:
        op.drop_column("contractor_profiles", column)
