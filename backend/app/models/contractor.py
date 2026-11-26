from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.common import DateTime
from app.db import Base
from app.models.enums import VerificationStatus


class ContractorProfile(Base):
    __tablename__ = "contractor_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_trade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    service_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=True), nullable=False, default=VerificationStatus.incomplete
    )
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avg_rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), default=Decimal("0"))
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Onboarding wizard (step 1). Required: business name (company_name), address, business email, registration id, trades.
    business_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_registration_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trades: Mapped[list | None] = mapped_column(JSON, nullable=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Paid through this date by MyFatoorah invoices (or set by an admin). Access to bidding follows this date.
    paid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # A trial set by an admin. Until this date the contractor can send offers without a paid subscription.
    trial_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Set when the first payment is confirmed: the admin must activate the account by this time.
    activation_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Denormalized "is there currently an active admin payment override"
    # flag — kept in sync by the payment_overrides service whenever a
    # PaymentOverride row is created or revoked. Reading this is a hot path
    # (every tender-feed and bid-submit request), so it's a column rather
    # than a per-request join; the PaymentOverride table is the audited
    # system of record for who/why/when.
    payment_override_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="contractor_profile")

    @property
    def is_paid_active(self) -> bool:
        # Paid through a MyFatoorah invoice (or an admin's manual entry) that covers today. Grace after paid_until is set in config.
        from datetime import timedelta
        from app.config import get_settings

        if self.paid_until is None:
            return False
        grace = timedelta(days=get_settings().payment_grace_days)
        return self.paid_until + grace > datetime.utcnow()

    @property
    def is_trial_active(self) -> bool:
        return self.trial_until is not None and self.trial_until > datetime.utcnow()

    # Paid, or in a trial. Either one lets the contractor send offers, on the web and on WhatsApp.
    @property
    def is_payment_active(self) -> bool:
        return self.is_paid_active or self.is_trial_active

    # The same value under the name the API returns (ContractorProfileOut.payment_active).
    @property
    def payment_active(self) -> bool:
        return self.is_payment_active

    # THE single source of truth for marketplace activation. Every route that gates tender visibility, drawings
    # or offers must check this, never verification_status alone and never the payment dates alone.
    @property
    def is_verified_active(self) -> bool:
        if self.is_suspended:
            return False
        if self.verification_status != VerificationStatus.approved:
            return False
        return self.is_payment_active or self.payment_override_active

    # Human-facing lifecycle status. Purely derived, never stored, so it cannot drift from the fields it is computed from.
    @property
    def marketplace_status(self) -> str:
        if self.is_suspended:
            return "suspended"
        if self.verification_status == VerificationStatus.incomplete:
            return "documents_incomplete"
        if self.verification_status == VerificationStatus.pending_review:
            return "submitted_for_review"
        if self.verification_status == VerificationStatus.changes_requested:
            return "changes_requested"
        if self.payment_override_active or self.is_payment_active:
            return "verified_active"
        return "payment_required"
