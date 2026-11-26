"""Contractor subscriptions: invoices through MyFatoorah, and what a confirmed payment changes.

Rules:
- The first invoice covers the activation fee plus the first month. Later invoices cover one month each.
- An invoice is marked paid only after MyFatoorah reports it Paid (GetPaymentStatus), never on a webhook alone.
- A paid invoice extends paid_until. The first payment starts the admin's activation deadline (48 hours).
- Applying the same paid invoice twice changes nothing.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.contractor import ContractorProfile
from app.models.enums import NotificationType, VerificationStatus
from app.models.onboarding import (
    INVOICE_CANCELED,
    INVOICE_PAID,
    INVOICE_PENDING,
    KIND_ACTIVATION,
    KIND_MONTHLY,
    PaymentInvoice,
    SubscriptionPlan,
)
from app.models.user import User
from app.services import myfatoorah
from app.services.app_settings import myfatoorah_config
from app.services.notify import notify

PERIOD_DAYS = 30


class BillingError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def onboarding_complete(profile: ContractorProfile) -> bool:
    return profile.onboarding_completed_at is not None


def _has_paid_activation(db: Session, contractor_id: str) -> bool:
    return db.scalar(
        select(PaymentInvoice.id).where(
            PaymentInvoice.contractor_id == contractor_id,
            PaymentInvoice.kind == KIND_ACTIVATION,
            PaymentInvoice.status == INVOICE_PAID,
        )
    ) is not None


def list_plans(db: Session) -> list[SubscriptionPlan]:
    return list(db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True)).order_by(SubscriptionPlan.monthly_fee)).all())


def create_invoice(db: Session, contractor: User, plan_id: str, *, now: datetime) -> PaymentInvoice:
    profile = db.get(ContractorProfile, contractor.id)
    if profile is None:
        raise BillingError("Only contractor accounts can subscribe.")
    if not onboarding_complete(profile):
        raise BillingError("Finish your business details before you subscribe.")
    plan = db.get(SubscriptionPlan, plan_id)
    if plan is None or not plan.is_active:
        raise BillingError("That plan is not available.")

    kind = KIND_MONTHLY if _has_paid_activation(db, contractor.id) else KIND_ACTIVATION
    if kind == KIND_ACTIVATION:
        amount = Decimal(plan.activation_fee) + Decimal(plan.monthly_fee)
        covers_from = now
    else:
        amount = Decimal(plan.monthly_fee)
        covers_from = max(profile.paid_until or now, now)
    covers_until = covers_from + timedelta(days=PERIOD_DAYS)

    reference = f"UT-{uuid.uuid4().hex[:20]}"
    app_url = get_settings().app_url.rstrip("/")
    try:
        invoice_id, payment_url = myfatoorah.send_payment(
            config=myfatoorah_config(db),
            amount=amount,
            currency=plan.currency,
            customer_name=profile.company_name or contractor.full_name or "Contractor",
            customer_email=profile.business_email or contractor.email,
            reference=reference,
            callback_url=f"{app_url}/contractor/subscribe?paid={reference}",
            error_url=f"{app_url}/contractor/subscribe?failed={reference}",
        )
    except myfatoorah.MyFatoorahError as exc:
        raise BillingError(str(exc)) from exc

    invoice = PaymentInvoice(
        contractor_id=contractor.id,
        plan_id=plan.id,
        kind=kind,
        amount=amount,
        currency=plan.currency,
        reference=reference,
        myfatoorah_invoice_id=invoice_id,
        payment_url=payment_url,
        status=INVOICE_PENDING,
        covers_from=covers_from,
        covers_until=covers_until,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def apply_paid(db: Session, invoice: PaymentInvoice, *, now: datetime) -> None:
    """Mark an invoice paid and extend the contractor's access. Safe to run more than once."""
    if invoice.status == INVOICE_PAID:
        return
    profile = db.get(ContractorProfile, invoice.contractor_id)
    invoice.status = INVOICE_PAID
    invoice.paid_at = now
    if profile is not None:
        candidate = invoice.covers_until or now
        profile.paid_until = max(profile.paid_until or candidate, candidate)
        if invoice.kind == KIND_ACTIVATION and profile.activation_due_at is None and profile.verification_status != VerificationStatus.approved:
            profile.activation_due_at = now + timedelta(hours=get_settings().activation_sla_hours)
    db.commit()
    contractor = db.get(User, invoice.contractor_id)
    if contractor is not None:
        notify(db, contractor, NotificationType.payment_activated)
        db.commit()


def refresh_invoice(db: Session, invoice: PaymentInvoice, *, now: datetime) -> PaymentInvoice:
    """Ask MyFatoorah for the invoice's status and act on it. Pending invoices stay pending."""
    if invoice.status != INVOICE_PENDING or invoice.myfatoorah_invoice_id is None:
        return invoice
    try:
        status = myfatoorah.get_payment_status(invoice.myfatoorah_invoice_id, config=myfatoorah_config(db))
    except myfatoorah.MyFatoorahError as exc:
        raise BillingError(str(exc)) from exc
    if status == myfatoorah.PAID:
        apply_paid(db, invoice, now=now)
    elif status == myfatoorah.CANCELED:
        invoice.status = INVOICE_CANCELED
        db.commit()
    return invoice


def handle_webhook(db: Session, body: dict, signature_header: str | None, *, now: datetime) -> str:
    """Process a MyFatoorah webhook. Returns a short result for logging."""
    data = body.get("Data") or {}
    invoice_number = (data.get("Invoice") or {}).get("Id")
    if invoice_number is None:
        return "ignored: no invoice"
    invoice = db.scalar(select(PaymentInvoice).where(PaymentInvoice.myfatoorah_invoice_id == int(invoice_number)))
    if invoice is None:
        return "ignored: unknown invoice"
    secret = myfatoorah_config(db).webhook_secret
    if secret and not myfatoorah.signature_matches(data, signature_header, secret=secret):
        return "rejected: bad signature"
    refresh_invoice(db, invoice, now=now)
    return f"checked: {invoice.status}"
