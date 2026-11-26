"""Contractor onboarding, subscriptions and one-time codes.

- SubscriptionPlan: the plans an admin creates. Each has a one-time activation fee and a monthly fee.
- PaymentInvoice: one MyFatoorah invoice. Its status comes from MyFatoorah, checked before we act on it.
- OtpCode: a short numeric code sent on WhatsApp to sign up or reset a password. Only its hash is stored.
- PortalInvite: a 24-hour, single-use link that opens the web sign-up for a contractor. Only its hash is stored.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import DateTime, gen_uuid

INVOICE_PENDING = "pending"
INVOICE_PAID = "paid"
INVOICE_CANCELED = "canceled"
INVOICE_EXPIRED = "expired"
INVOICE_STATUSES = (INVOICE_PENDING, INVOICE_PAID, INVOICE_CANCELED, INVOICE_EXPIRED)

KIND_ACTIVATION = "activation"  # activation fee plus the first month
KIND_MONTHLY = "monthly"  # a later month
INVOICE_KINDS = (KIND_ACTIVATION, KIND_MONTHLY)

OTP_SIGNUP = "signup"
OTP_RESET = "reset"
OTP_PURPOSES = (OTP_SIGNUP, OTP_RESET)


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    activation_fee: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KWD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PaymentInvoice(Base):
    __tablename__ = "payment_invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    contractor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscription_plans.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Our reference, sent to MyFatoorah as CustomerReference. Unique, so a webhook can be matched to a row.
    reference: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    myfatoorah_invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    payment_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=INVOICE_PENDING, index=True)
    covers_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    covers_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PortalInvite(Base):
    __tablename__ = "portal_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
