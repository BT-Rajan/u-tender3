"""Admin billing: payment setup (MyFatoorah keys and the OTP template), plan deletion, and manual paid-until and
trial-until dates for a contractor. Plans are created and updated in admin.py. Every change is audit-logged, and
secret values never appear in the log.
"""

from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_admin
from app.models.contractor import ContractorProfile
from app.models.onboarding import PaymentInvoice, SubscriptionPlan
from app.models.user import User
from app.services import app_settings
from app.services.audit import log_action

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class BillingSettingsIn(BaseModel):
    # Send a field to change it. An empty value clears it, so the server's .env value applies again.
    myfatoorah_api_key: str | None = Field(default=None, max_length=300)
    myfatoorah_webhook_secret: str | None = Field(default=None, max_length=300)
    myfatoorah_base_url: str | None = Field(default=None, max_length=200)
    whatsapp_otp_template: str | None = Field(default=None, max_length=120)


def _settings_out(db: Session) -> dict[str, Any]:
    return {
        "myfatoorah_api_key": app_settings.describe(db, "myfatoorah_api_key"),
        "myfatoorah_webhook_secret": app_settings.describe(db, "myfatoorah_webhook_secret"),
        "myfatoorah_base_url": app_settings.describe(db, "myfatoorah_base_url"),
        "whatsapp_otp_template": app_settings.describe(db, "whatsapp_otp_template"),
        "payments_ready": bool(app_settings.get_value(db, "myfatoorah_api_key")),
    }


@router.get("/settings/billing")
def get_billing_settings(db: Session = Depends(get_db)):
    return _settings_out(db)


@router.put("/settings/billing")
def put_billing_settings(body: BillingSettingsIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    for key in body.model_fields_set:
        try:
            app_settings.set_value(db, key, getattr(body, key), actor_id=admin.id, now=now)
        except app_settings.SettingError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return _settings_out(db)


@router.delete("/plans/{plan_id}", status_code=204)
def delete_plan(plan_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    plan = db.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found.")
    has_invoices = db.scalar(select(PaymentInvoice.id).where(PaymentInvoice.plan_id == plan_id).limit(1)) is not None
    if has_invoices:
        raise HTTPException(status_code=409, detail="This plan has payment history, so it cannot be deleted. Hide it instead.")
    name = plan.name
    db.delete(plan)
    db.commit()
    log_action(db, actor_id=admin.id, action="plan.delete", target_type="subscription_plan", target_id=plan_id, previous_value=name)
    return Response(status_code=204)


class BillingDatesIn(BaseModel):
    # Dates are days in the tender timezone (Asia/Kuwait by default). A date ends at 23:59:59 that day.
    paid_until: date | None = None
    trial_until: date | None = None
    reason: str = Field(min_length=3, max_length=500)


def _end_of_day_utc(day: date | None) -> datetime | None:
    if day is None:
        return None
    local = datetime.combine(day, time(23, 59, 59), tzinfo=ZoneInfo(get_settings().tender_timezone))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@router.patch("/contractors/{contractor_id}/billing")
def set_contractor_billing(contractor_id: str, body: BillingDatesIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Set or clear a contractor's paid-until or trial-until date by hand, with a reason. Only the fields sent change."""
    profile = db.get(ContractorProfile, contractor_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Contractor not found.")
    fields = [name for name in ("paid_until", "trial_until") if name in body.model_fields_set]
    if not fields:
        raise HTTPException(status_code=400, detail="Send paid_until or trial_until to change.")

    changes: list[tuple[str, datetime | None, datetime | None]] = []
    for name in fields:
        previous = getattr(profile, name)
        new = _end_of_day_utc(getattr(body, name))
        setattr(profile, name, new)
        changes.append((name, previous, new))
    db.commit()
    for name, previous, new in changes:
        log_action(
            db,
            actor_id=admin.id,
            action=f"contractor.{name}",
            target_type="contractor_profile",
            target_id=contractor_id,
            previous_value=_iso(previous),
            new_value=_iso(new),
            reason=body.reason,
        )
    db.refresh(profile)
    return {
        "contractor_id": contractor_id,
        "paid_until": _iso(profile.paid_until),
        "trial_until": _iso(profile.trial_until),
        "payment_active": profile.is_payment_active,
        "trial_active": profile.is_trial_active,
        "active": profile.is_verified_active,
    }
