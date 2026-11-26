"""Contractor subscriptions through MyFatoorah: plans, invoices, status checks and the payment webhook."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_contractor
from app.models.onboarding import PaymentInvoice, SubscriptionPlan
from app.models.user import User
from app.services import payments

router = APIRouter(tags=["billing"])
logger = logging.getLogger("billing")


class InvoiceRequest(BaseModel):
    plan_id: str


def _plan_out(plan: SubscriptionPlan) -> dict:
    return {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "activation_fee": str(plan.activation_fee),
        "monthly_fee": str(plan.monthly_fee),
        "currency": plan.currency,
    }


def _invoice_out(invoice: PaymentInvoice) -> dict:
    return {
        "id": invoice.id,
        "kind": invoice.kind,
        "status": invoice.status,
        "amount": str(invoice.amount),
        "currency": invoice.currency,
        "payment_url": invoice.payment_url if invoice.status == "pending" else None,
        "covers_from": invoice.covers_from,
        "covers_until": invoice.covers_until,
        "paid_at": invoice.paid_at,
        "created_at": invoice.created_at,
    }


@router.get("/billing/plans")
def plans(_user: User = Depends(require_contractor), db: Session = Depends(get_db)):
    return [_plan_out(plan) for plan in payments.list_plans(db)]


@router.post("/billing/invoices", status_code=201)
def create_invoice(body: InvoiceRequest, user: User = Depends(require_contractor), db: Session = Depends(get_db)):
    try:
        invoice = payments.create_invoice(db, user, body.plan_id, now=datetime.utcnow())
    except payments.BillingError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    return _invoice_out(invoice)


@router.get("/billing/invoices")
def list_invoices(user: User = Depends(require_contractor), db: Session = Depends(get_db)):
    rows = db.scalars(select(PaymentInvoice).where(PaymentInvoice.contractor_id == user.id).order_by(PaymentInvoice.created_at.desc())).all()
    return [_invoice_out(row) for row in rows]


@router.post("/billing/invoices/{invoice_id}/refresh")
def refresh(invoice_id: str, user: User = Depends(require_contractor), db: Session = Depends(get_db)):
    """Ask MyFatoorah for this invoice's status now. The payment return page calls this."""
    invoice = db.get(PaymentInvoice, invoice_id)
    if invoice is None or invoice.contractor_id != user.id:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    try:
        payments.refresh_invoice(db, invoice, now=datetime.utcnow())
    except payments.BillingError as exc:
        raise HTTPException(status_code=502, detail=exc.message)
    db.refresh(invoice)
    return _invoice_out(invoice)


@router.post("/billing/webhook/myfatoorah")
async def myfatoorah_webhook(request: Request, db: Session = Depends(get_db)):
    """MyFatoorah calls this when a payment changes. The result always comes from GetPaymentStatus."""
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed JSON")
    signature = request.headers.get("myfatoorah-signature")
    result = payments.handle_webhook(db, body, signature, now=datetime.utcnow())
    logger.info("MyFatoorah webhook: %s", result)
    if result.startswith("rejected"):
        raise HTTPException(status_code=403, detail="Signature does not match.")
    return {"received": True}
