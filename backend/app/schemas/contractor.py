from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import OfferStatus, ProjectStatus, VerificationStatus
from app.services.money import MoneyAmount


class ContractorProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    company_name: str
    license_number: str | None
    primary_trade: str | None
    service_area: str | None
    verification_status: VerificationStatus
    is_suspended: bool
    avg_rating: Decimal
    review_count: int
    paid_until: datetime | None
    trial_until: datetime | None
    payment_active: bool
    payment_override_active: bool
    # Derived, never stored — spec §2.13's human-facing lifecycle status,
    # one of: documents_incomplete, submitted_for_review, changes_requested,
    # payment_required, verified_active, suspended.
    marketplace_status: str
    created_at: datetime
    email: str | None = None


class ContractorProfileUpdate(BaseModel):
    company_name: str
    license_number: str | None = None
    primary_trade: str | None = None
    service_area: str | None = None


class SubmitForReview(BaseModel):
    company_name: str
    license_number: str | None = None


class MyBidOut(BaseModel):
    project_id: str
    project_title: str
    project_address: str
    project_status: ProjectStatus
    bid_deadline: datetime
    offer_id: str
    amount: MoneyAmount
    offer_status: OfferStatus
    revision: int
    updated_at: datetime
