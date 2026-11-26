"""Contractor onboarding: the business-details wizard, and the status endpoint that tells the app what to do next."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_contractor
from app.models.contractor import ContractorProfile
from app.models.enums import VerificationStatus
from app.models.user import User
from app.services import payments
from app.services.registration import TRADE_OPTIONS

router = APIRouter(tags=["onboarding"])


class BusinessDetails(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    business_address: str = Field(min_length=5, max_length=500)
    website: str | None = Field(default=None, max_length=255)
    business_email: EmailStr
    business_registration_id: str = Field(min_length=2, max_length=100)
    trades: list[str] = Field(min_length=1, max_length=10)


def _clean_website(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    site = value.strip()
    if not site.startswith(("http://", "https://")):
        site = f"https://{site}"
    if " " in site or "." not in site.split("//", 1)[-1]:
        raise HTTPException(status_code=400, detail="Enter the website address, for example www.example.com.")
    return site


def _details_out(profile: ContractorProfile) -> dict[str, Any]:
    return {
        "business_name": profile.company_name,
        "business_address": profile.business_address,
        "website": profile.website,
        "business_email": profile.business_email,
        "business_registration_id": profile.business_registration_id,
        "trades": list(profile.trades or []),
        "complete": payments.onboarding_complete(profile),
    }


def _profile(db: Session, user: User) -> ContractorProfile:
    profile = db.get(ContractorProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Contractor profile not found.")
    return profile


@router.get("/contractor/onboarding")
def get_onboarding(user: User = Depends(require_contractor), db: Session = Depends(get_db)):
    return _details_out(_profile(db, user))


@router.put("/contractor/onboarding")
def save_onboarding(body: BusinessDetails, user: User = Depends(require_contractor), db: Session = Depends(get_db)):
    unknown = [trade for trade in body.trades if trade not in TRADE_OPTIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Choose trades from the list. Not recognised: {', '.join(unknown)}.")
    profile = _profile(db, user)
    profile.company_name = body.business_name.strip()
    profile.business_address = body.business_address.strip()
    profile.website = _clean_website(body.website)
    profile.business_email = str(body.business_email).strip().lower()
    profile.business_registration_id = body.business_registration_id.strip()
    profile.trades = list(dict.fromkeys(body.trades))
    profile.primary_trade = profile.trades[0]
    profile.onboarding_completed_at = profile.onboarding_completed_at or datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return _details_out(profile)


@router.get("/contractor/status")
def contractor_status(user: User = Depends(require_contractor), db: Session = Depends(get_db)):
    """What the app should show next, and whether the account can bid. Offers stay open while the account is active."""
    profile = _profile(db, user)
    now = datetime.utcnow()
    paid = profile.is_payment_active
    approved = profile.verification_status == VerificationStatus.approved
    overdue = bool(profile.activation_due_at and not approved and profile.activation_due_at < now)

    if profile.is_suspended:
        next_step = "suspended"
    elif not payments.onboarding_complete(profile):
        next_step = "details"
    elif not paid:
        next_step = "subscribe"
    elif not approved:
        next_step = "awaiting_activation"
    else:
        next_step = "active"

    return {
        "next_step": next_step,
        "onboarding_complete": payments.onboarding_complete(profile),
        "verification_status": profile.verification_status.value,
        "is_suspended": profile.is_suspended,
        "paid_until": profile.paid_until,
        "trial_until": profile.trial_until,
        "trial_active": profile.is_trial_active,
        "payment_active": paid,
        "activation_due_at": profile.activation_due_at,
        "activation_overdue": overdue,
        "active": profile.is_verified_active,
        "can_bid": profile.is_verified_active,
        "grace_days": get_settings().payment_grace_days,
    }
