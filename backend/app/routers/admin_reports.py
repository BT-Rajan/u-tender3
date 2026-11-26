"""Admin reports: a summary of the whole platform, and period reports for tenders, billing and activations.

Every period report takes ?from=YYYY-MM-DD&to=YYYY-MM-DD (days in the tender timezone, both inclusive, at most a
year, default the last 30 days). Without ?format=csv the JSON has the summary and up to 200 rows; with
?format=csv the file has every row in the period.
"""

import csv
import io
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_admin
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.contractor import ContractorProfile
from app.models.enums import UserRole, VerificationStatus
from app.models.offer import Offer
from app.models.onboarding import INVOICE_PAID, KIND_ACTIVATION, PaymentInvoice, SubscriptionPlan
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.user import User

router = APIRouter(prefix="/admin/reports", tags=["admin"], dependencies=[Depends(require_admin)])

MAX_PERIOD_DAYS = 366
JSON_ROW_LIMIT = 200
FORMULA_PREFIXES = ("=", "+", "-", "@")


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().tender_timezone)


def _utc_from_local_midnight(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=_tz()).astimezone(timezone.utc).replace(tzinfo=None)


def _period(from_: str | None, to: str | None):
    """(start_day, end_day, start_utc, end_utc) for a report. end_utc is exclusive."""
    try:
        end_day = date.fromisoformat(to) if to else datetime.now(_tz()).date()
        start_day = date.fromisoformat(from_) if from_ else end_day - timedelta(days=29)
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must look like 2026-11-30.")
    if start_day > end_day:
        raise HTTPException(status_code=400, detail="The start date is after the end date.")
    if (end_day - start_day).days >= MAX_PERIOD_DAYS:
        raise HTTPException(status_code=400, detail="A report covers at most one year.")
    return start_day, end_day, _utc_from_local_midnight(start_day), _utc_from_local_midnight(end_day + timedelta(days=1))


def _iso(value: datetime | None) -> str | None:
    """A stored (UTC, naive) time as Kuwait time with its offset, so the report reads correctly anywhere."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(_tz()).isoformat()


def _cell(value) -> str:
    if value is None:
        return ""
    text = str(value)
    # Stop spreadsheet programs from running a cell as a formula.
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def _csv_response(rows: list[dict], fieldnames: list[str], filename: str) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({name: _cell(row.get(name)) for name in fieldnames})
    # A byte-order mark lets Excel read Arabic names correctly.
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _json_rows(rows: list[dict]) -> dict:
    return {"rows": rows[:JSON_ROW_LIMIT], "rows_total": len(rows)}


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    """Platform totals as they stand now."""
    now = datetime.utcnow()
    roles = {role.value: count for role, count in db.query(User.role, func.count(User.id)).group_by(User.role).all()}
    contractors = db.query(ContractorProfile).all()
    owners = db.query(OwnerProfile).all()
    pending_activation = [c for c in contractors if c.activation_due_at is not None and c.verification_status != VerificationStatus.approved]
    awarded_count, awarded_value = db.query(func.count(AwardRecord.id), func.coalesce(func.sum(AwardRecord.amount), 0)).one()
    return {
        "generated_at": _iso(now),
        "users": {role: roles.get(role, 0) for role in ("owner", "contractor", "admin")},
        "contractors": {
            "total": len(contractors),
            "by_status": dict(Counter(c.marketplace_status for c in contractors)),
            "active": sum(1 for c in contractors if c.is_verified_active),
            "paid": sum(1 for c in contractors if c.is_paid_active),
            "on_trial": sum(1 for c in contractors if c.is_trial_active),
            "waiting_activation": len(pending_activation),
            "activation_overdue": sum(1 for c in pending_activation if c.activation_due_at < now),
        },
        "owners": {"total": len(owners), "by_status": dict(Counter(o.marketplace_status for o in owners))},
        "projects": {
            "total": db.query(func.count(Project.id)).scalar(),
            "by_status": {status.value: count for status, count in db.query(Project.status, func.count(Project.id)).group_by(Project.status).all()},
        },
        "offers": {
            "total": db.query(func.count(Offer.id)).scalar(),
            "by_status": {status.value: count for status, count in db.query(Offer.status, func.count(Offer.id)).group_by(Offer.status).all()},
        },
        "awards": {"count": awarded_count, "value": str(Decimal(awarded_value))},
    }


@router.get("/tenders")
def tender_report(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    fmt: str = Query(default="json", alias="format"),
    db: Session = Depends(get_db),
):
    start_day, end_day, start, end = _period(from_, to)
    projects = (
        db.query(Project, User)
        .join(User, User.id == Project.owner_id)
        .filter(Project.created_at >= start, Project.created_at < end)
        .order_by(Project.created_at.desc())
        .all()
    )
    project_ids = [project.id for project, _ in projects]
    offer_counts = dict(
        db.query(Offer.project_id, func.count(Offer.id)).filter(Offer.project_id.in_(project_ids)).group_by(Offer.project_id).all()
    ) if project_ids else {}
    awards = {
        award.project_id: award
        for award in (db.query(AwardRecord).filter(AwardRecord.project_id.in_(project_ids)).all() if project_ids else [])
    }
    rows = [
        {
            "reference": project.reference_code or "",
            "title": project.title,
            "trade": project.trade or "",
            "owner": owner.full_name or owner.email or "",
            "status": project.status.value,
            "tender_type": project.tender_type.value,
            "bid_deadline": _iso(project.bid_deadline),
            "offers": offer_counts.get(project.id, 0),
            "awarded_amount": str(awards[project.id].amount) if project.id in awards else "",
            "created_at": _iso(project.created_at),
        }
        for project, owner in projects
    ]
    if fmt == "csv":
        return _csv_response(rows, list(rows[0].keys()) if rows else _TENDER_FIELDS, f"tenders-{start_day}-{end_day}.csv")

    awards_in_period = db.query(func.count(AwardRecord.id), func.coalesce(func.sum(AwardRecord.amount), 0)).filter(
        AwardRecord.created_at >= start, AwardRecord.created_at < end
    ).one()
    return {
        "period": {"from": start_day.isoformat(), "to": end_day.isoformat()},
        "summary": {
            "projects_created": len(projects),
            "by_status": dict(Counter(project.status.value for project, _ in projects)),
            "offers_received": db.query(func.count(Offer.id)).filter(Offer.created_at >= start, Offer.created_at < end).scalar(),
            "awards": awards_in_period[0],
            "awarded_value": str(Decimal(awards_in_period[1])),
        },
        **_json_rows(rows),
    }


_TENDER_FIELDS = ["reference", "title", "trade", "owner", "status", "tender_type", "bid_deadline", "offers", "awarded_amount", "created_at"]


@router.get("/billing")
def billing_report(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    fmt: str = Query(default="json", alias="format"),
    db: Session = Depends(get_db),
):
    """Paid invoices by the day they were paid. Totals are kept per currency, never added across currencies."""
    start_day, end_day, start, end = _period(from_, to)
    paid = (
        db.query(PaymentInvoice, SubscriptionPlan, ContractorProfile, User)
        .join(SubscriptionPlan, SubscriptionPlan.id == PaymentInvoice.plan_id)
        .join(ContractorProfile, ContractorProfile.user_id == PaymentInvoice.contractor_id)
        .join(User, User.id == PaymentInvoice.contractor_id)
        .filter(PaymentInvoice.status == INVOICE_PAID, PaymentInvoice.paid_at >= start, PaymentInvoice.paid_at < end)
        .order_by(PaymentInvoice.paid_at.desc())
        .all()
    )
    totals: dict[str, Decimal] = {}
    by_plan: dict[str, dict] = {}
    by_kind = Counter()
    for invoice, plan, _, _ in paid:
        totals[invoice.currency] = totals.get(invoice.currency, Decimal("0")) + Decimal(invoice.amount)
        entry = by_plan.setdefault(plan.name, {"plan": plan.name, "count": 0, "totals": {}})
        entry["count"] += 1
        entry["totals"][invoice.currency] = str(Decimal(entry["totals"].get(invoice.currency, "0")) + Decimal(invoice.amount))
        by_kind[invoice.kind] += 1
    rows = [
        {
            "paid_at": _iso(invoice.paid_at),
            "company": contractor.company_name,
            "email": user.email or "",
            "plan": plan.name,
            "kind": invoice.kind,
            "amount": str(invoice.amount),
            "currency": invoice.currency,
            "reference": invoice.reference,
            "myfatoorah_invoice_id": invoice.myfatoorah_invoice_id or "",
        }
        for invoice, plan, contractor, user in paid
    ]
    if fmt == "csv":
        return _csv_response(rows, list(rows[0].keys()) if rows else _BILLING_FIELDS, f"billing-{start_day}-{end_day}.csv")

    created_in_period = db.query(PaymentInvoice.status, func.count(PaymentInvoice.id)).filter(
        PaymentInvoice.created_at >= start, PaymentInvoice.created_at < end
    ).group_by(PaymentInvoice.status).all()
    created = dict(created_in_period)
    contractors = db.query(ContractorProfile).all()
    return {
        "period": {"from": start_day.isoformat(), "to": end_day.isoformat()},
        "summary": {
            "paid_count": len(paid),
            "totals": {currency: str(value) for currency, value in totals.items()},
            "by_plan": list(by_plan.values()),
            "by_kind": {"activation": by_kind.get("activation", 0), "monthly": by_kind.get("monthly", 0)},
            "invoices_created": sum(created.values()),
            "still_pending": created.get("pending", 0),
            "canceled_or_expired": created.get("canceled", 0) + created.get("expired", 0),
            "paid_contractors_now": sum(1 for c in contractors if c.is_paid_active),
            "trials_now": sum(1 for c in contractors if c.is_trial_active),
        },
        **_json_rows(rows),
    }


_BILLING_FIELDS = ["paid_at", "company", "email", "plan", "kind", "amount", "currency", "reference", "myfatoorah_invoice_id"]


@router.get("/activations")
def activation_report(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    fmt: str = Query(default="json", alias="format"),
    db: Session = Depends(get_db),
):
    """Contractors whose first payment was made in the period, and how long the admin took to activate them.
    The queue figures at the top are for now, not for the period."""
    start_day, end_day, start, end = _period(from_, to)
    now = datetime.utcnow()
    first_payments = (
        db.query(PaymentInvoice, ContractorProfile, User)
        .join(ContractorProfile, ContractorProfile.user_id == PaymentInvoice.contractor_id)
        .join(User, User.id == PaymentInvoice.contractor_id)
        .filter(
            PaymentInvoice.kind == KIND_ACTIVATION,
            PaymentInvoice.status == INVOICE_PAID,
            PaymentInvoice.paid_at >= start,
            PaymentInvoice.paid_at < end,
        )
        .order_by(PaymentInvoice.paid_at.desc())
        .all()
    )
    contractor_ids = [contractor.user_id for _, contractor, _ in first_payments]
    activated_at = dict(
        db.query(AuditLog.target_id, func.max(AuditLog.created_at))
        .filter(AuditLog.action == "contractor.activate", AuditLog.target_id.in_(contractor_ids))
        .group_by(AuditLog.target_id)
        .all()
    ) if contractor_ids else {}
    sla = timedelta(hours=get_settings().activation_sla_hours)

    rows = []
    hours_list = []
    on_time = late = waiting = 0
    for invoice, contractor, user in first_payments:
        done = activated_at.get(contractor.user_id)
        hours = round((done - invoice.paid_at).total_seconds() / 3600, 1) if done else None
        if done is None:
            status = "waiting"
            waiting += 1
        else:
            status = "activated"
            hours_list.append(hours)
            if done - invoice.paid_at <= sla:
                on_time += 1
            else:
                late += 1
        rows.append(
            {
                "company": contractor.company_name,
                "contact": user.full_name or "",
                "email": user.email or "",
                "paid_at": _iso(invoice.paid_at),
                "activation_due_at": _iso(contractor.activation_due_at),
                "activated_at": _iso(done),
                "hours_to_activate": "" if hours is None else hours,
                "status": status,
            }
        )
    if fmt == "csv":
        return _csv_response(rows, list(rows[0].keys()) if rows else _ACTIVATION_FIELDS, f"activations-{start_day}-{end_day}.csv")

    queue = db.query(ContractorProfile).filter(
        ContractorProfile.activation_due_at.isnot(None), ContractorProfile.verification_status != VerificationStatus.approved
    ).all()
    return {
        "period": {"from": start_day.isoformat(), "to": end_day.isoformat()},
        "summary": {
            "first_payments": len(rows),
            "activated_within_sla": on_time,
            "activated_late": late,
            "still_waiting": waiting,
            "average_hours_to_activate": round(sum(hours_list) / len(hours_list), 1) if hours_list else None,
            "queue_now": len(queue),
            "queue_overdue_now": sum(1 for c in queue if c.activation_due_at < now),
            "activation_target_hours": get_settings().activation_sla_hours,
        },
        **_json_rows(rows),
    }


_ACTIVATION_FIELDS = ["company", "contact", "email", "paid_at", "activation_due_at", "activated_at", "hours_to_activate", "status"]
