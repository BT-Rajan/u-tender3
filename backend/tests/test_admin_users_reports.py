from zoneinfo import ZoneInfo
"""Admin user management and reports: the unified user list, its filters and suspend guards, and the platform
summary and period reports with CSV export. Only admins may use any of it."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.config import get_settings
from app.main import app
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.contractor import ContractorProfile
from app.models.enums import OfferStatus, ProjectStatus, TenderType, UserRole, VerificationStatus
from app.models.offer import Offer
from app.models.onboarding import INVOICE_CANCELED, INVOICE_PAID, INVOICE_PENDING, KIND_ACTIVATION, KIND_MONTHLY, PaymentInvoice, SubscriptionPlan
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.user import User
from app.services.audit import log_action

NOW = datetime.utcnow()
PASSWORD = "reports-pass-1"


def _login(email, password=PASSWORD) -> TestClient:
    client = TestClient(app)
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client


def _admin(db, email="admin-reports@example.com") -> TestClient:
    db.add(User(email=email, password_hash=hash_password(PASSWORD), role=UserRole.admin, full_name="Admin"))
    db.commit()
    return _login(email)


def _owner(db, email, name="Layla Owner", created_at=None):
    user = User(email=email, password_hash=hash_password(PASSWORD), role=UserRole.owner, full_name=name, email_verified=True)
    if created_at:
        user.created_at = created_at
    db.add(user)
    db.flush()
    db.add(OwnerProfile(user_id=user.id, verification_status=VerificationStatus.approved))
    db.commit()
    return user


def _contractor(db, email, company="Haddad Builders", *, approved=True, paid_until=None, trial_until=None, created_at=None):
    user = User(email=email, password_hash=hash_password(PASSWORD), role=UserRole.contractor, full_name="Omar Haddad", phone="+96511112222")
    if created_at:
        user.created_at = created_at
    db.add(user)
    db.flush()
    db.add(
        ContractorProfile(
            user_id=user.id,
            company_name=company,
            primary_trade="Electrical",
            verification_status=VerificationStatus.approved if approved else VerificationStatus.incomplete,
            paid_until=paid_until,
            trial_until=trial_until,
            onboarding_completed_at=NOW,
        )
    )
    db.commit()
    return user


def _project(db, owner, title="Villa renovation", *, status=ProjectStatus.open, created_at=None, reference=None):
    project = Project(
        owner_id=owner.id, title=title, address="Block 3, Salmiya", trade="Electrical", description="Ground floor",
        bid_deadline=NOW + timedelta(days=10), status=status, tender_type=TenderType.owner_visible, reference_code=reference,
    )
    if created_at:
        project.created_at = created_at
    db.add(project)
    db.commit()
    return project


# --- user management ----------------------------------------------------------------------


def test_only_admins_can_use_user_management_or_reports(db):
    _contractor(db, "plain@example.com")
    client = _login("plain@example.com")
    assert client.get("/admin/users").status_code == 403
    assert client.get("/admin/reports/summary").status_code == 403
    assert client.get("/admin/reports/billing").status_code == 403


def test_the_user_list_shows_every_role_and_filters_by_role_and_search(db):
    admin = _admin(db)
    _owner(db, "owner-list@example.com", "Layla Owner")
    _contractor(db, "contractor-list@example.com", company="Noor Electrical")

    everyone = admin.get("/admin/users").json()
    assert everyone["total"] >= 3
    assert {"owner", "contractor", "admin"} <= {item["role"] for item in everyone["items"]}

    contractors = admin.get("/admin/users", params={"role": "contractor"}).json()["items"]
    assert contractors and all(item["role"] == "contractor" for item in contractors)

    found = admin.get("/admin/users", params={"q": "noor"}).json()["items"]
    assert [item["email"] for item in found] == ["contractor-list@example.com"]
    assert found[0]["company_name"] == "Noor Electrical"


def test_an_unknown_role_filter_is_refused(db):
    assert _admin(db).get("/admin/users", params={"role": "superuser"}).status_code == 400


def test_the_status_filter_finds_suspended_accounts(db):
    admin = _admin(db)
    contractor = _contractor(db, "to-suspend@example.com")
    assert admin.post(f"/admin/users/{contractor.id}/suspend", json={"suspended": True}).status_code == 200

    suspended = admin.get("/admin/users", params={"status": "suspended"}).json()["items"]

    assert [item["id"] for item in suspended] == [contractor.id]
    assert suspended[0]["is_suspended"] is True


def test_suspending_a_contractor_through_user_management_is_audited_and_blocks_offers(db):
    admin = _admin(db)
    owner = _owner(db, "owner-block@example.com")
    project = _project(db, owner)
    contractor = _contractor(db, "block-me@example.com", paid_until=NOW + timedelta(days=30))
    assert _login("block-me@example.com").post(f"/projects/{project.id}/offers", json={"amount": "4300.00"}).status_code == 200

    response = admin.post(f"/admin/users/{contractor.id}/suspend", json={"suspended": True})

    assert response.status_code == 200
    assert response.json() == {"user_id": contractor.id, "is_suspended": True}
    row = db.query(AuditLog).filter_by(action="contractor.suspend", target_id=contractor.id).one()
    assert row.new_value == "True"
    assert _login("block-me@example.com").post(f"/projects/{project.id}/offers", json={"amount": "4500.00"}).status_code == 403


def test_suspending_an_owner_through_user_management_is_audited(db):
    admin = _admin(db)
    owner = _owner(db, "owner-suspend@example.com")

    assert admin.post(f"/admin/users/{owner.id}/suspend", json={"suspended": True}).status_code == 200
    assert db.query(AuditLog).filter_by(action="owner.suspend", target_id=owner.id).count() == 1

    assert admin.post(f"/admin/users/{owner.id}/suspend", json={"suspended": False}).status_code == 200
    assert db.query(AuditLog).filter_by(action="owner.reactivate", target_id=owner.id).count() == 1


def test_an_admin_cannot_suspend_their_own_account_or_another_admin(db):
    admin_client = _admin(db)
    me = db.query(User).filter_by(email="admin-reports@example.com").one()
    other = User(email="other-admin@example.com", password_hash=hash_password(PASSWORD), role=UserRole.admin, full_name="Other")
    db.add(other)
    db.commit()

    assert admin_client.post(f"/admin/users/{me.id}/suspend", json={"suspended": True}).status_code == 400
    assert admin_client.post(f"/admin/users/{other.id}/suspend", json={"suspended": True}).status_code == 400


def test_the_user_detail_shows_the_role_profile_and_recent_activity(db):
    admin = _admin(db)
    contractor = _contractor(db, "detail@example.com", paid_until=NOW + timedelta(days=5))
    log_action(db, actor_id=None, action="contractor.trial_until", target_type="contractor_profile", target_id=contractor.id, reason="Trial agreed")

    body = admin.get(f"/admin/users/{contractor.id}").json()

    assert body["role"] == "contractor"
    assert body["contractor"]["payment_active"] is True
    assert body["contractor"]["marketplace_status"] == "verified_active"
    assert body["recent_activity"][0]["action"] == "contractor.trial_until"
    assert body["recent_activity"][0]["reason"] == "Trial agreed"


def test_an_unknown_user_is_not_found(db):
    admin = _admin(db)
    assert admin.get("/admin/users/no-such-user").status_code == 404
    assert admin.post("/admin/users/no-such-user/suspend", json={"suspended": True}).status_code == 404


# --- summary ----------------------------------------------------------------------------------


def test_the_summary_counts_the_platform_as_it_stands(db):
    admin = _admin(db)
    owner = _owner(db, "owner-summary@example.com")
    _contractor(db, "active-summary@example.com", paid_until=NOW + timedelta(days=30))
    _contractor(db, "trial-summary@example.com", trial_until=NOW + timedelta(days=7))
    _contractor(db, "waiting-summary@example.com", approved=False)
    _project(db, owner, status=ProjectStatus.open)
    _project(db, owner, status=ProjectStatus.awarded)

    body = admin.get("/admin/reports/summary").json()

    assert body["users"]["contractor"] >= 3
    assert body["contractors"]["on_trial"] == 1
    assert body["contractors"]["paid"] == 1
    assert body["contractors"]["active"] == 2
    assert body["projects"]["by_status"]["open"] >= 1
    assert body["projects"]["by_status"]["awarded"] >= 1
    assert body["awards"]["count"] == 0


# --- tender report -----------------------------------------------------------------------------


def test_the_tender_report_counts_only_projects_created_in_the_period(db):
    admin = _admin(db)
    owner = _owner(db, "owner-tenders@example.com")
    today = datetime.now(ZoneInfo("Asia/Kuwait")).date()
    _project(db, owner, "In period", reference="A00001")
    _project(db, owner, "Long ago", created_at=NOW - timedelta(days=60))

    body = admin.get("/admin/reports/tenders", params={"from": (today - timedelta(days=3)).isoformat(), "to": today.isoformat()}).json()

    assert body["summary"]["projects_created"] == 1
    assert [row["title"] for row in body["rows"]] == ["In period"]
    assert body["rows"][0]["reference"] == "A00001"


def test_the_tender_csv_has_a_header_and_neutralises_formulas(db):
    admin = _admin(db)
    owner = _owner(db, "owner-csv@example.com")
    _project(db, owner, title="=HYPERLINK(\"http://evil\")")
    today = datetime.now(ZoneInfo("Asia/Kuwait")).date()

    response = admin.get("/admin/reports/tenders", params={"from": today.isoformat(), "to": today.isoformat(), "format": "csv"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    text = response.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("reference,title,trade,owner")
    assert "'=HYPERLINK" in text


# --- billing report ------------------------------------------------------------------------------


def _plan(db, name="Standard", activation="50", monthly="20"):
    plan = SubscriptionPlan(name=name, activation_fee=Decimal(activation), monthly_fee=Decimal(monthly), currency="KWD", is_active=True)
    db.add(plan)
    db.commit()
    return plan


def _invoice(db, contractor, plan, *, amount, kind=KIND_MONTHLY, status=INVOICE_PAID, currency="KWD", paid_at=NOW, created_at=None, reference=None):
    invoice = PaymentInvoice(
        contractor_id=contractor.id, plan_id=plan.id, kind=kind, amount=Decimal(amount), currency=currency,
        reference=reference or f"UT-{contractor.id[:8]}-{amount}-{status}-{currency}-{kind}",
        status=status, paid_at=paid_at if status == INVOICE_PAID else None,
    )
    if created_at:
        invoice.created_at = created_at
    db.add(invoice)
    db.commit()
    return invoice


def test_the_billing_report_totals_paid_invoices_per_currency(db):
    admin = _admin(db)
    plan = _plan(db)
    contractor = _contractor(db, "billing-a@example.com", company="Alpha Co")
    _invoice(db, contractor, plan, amount="70", kind=KIND_ACTIVATION, reference="UT-B1")
    _invoice(db, contractor, plan, amount="20", kind=KIND_MONTHLY, reference="UT-B2")
    _invoice(db, contractor, plan, amount="99", status=INVOICE_PENDING, reference="UT-B3")
    _invoice(db, contractor, plan, amount="5", currency="USD", reference="UT-B4")
    today = datetime.now(ZoneInfo("Asia/Kuwait")).date()

    body = admin.get("/admin/reports/billing", params={"from": (today - timedelta(days=3)).isoformat(), "to": today.isoformat()}).json()

    assert body["summary"]["paid_count"] == 3
    assert body["summary"]["totals"] == {"KWD": "90.000", "USD": "5.000"}
    assert body["summary"]["by_kind"] == {"activation": 1, "monthly": 2}
    assert body["summary"]["still_pending"] == 1
    assert body["summary"]["by_plan"][0]["plan"] == "Standard"
    assert {row["reference"] for row in body["rows"]} == {"UT-B1", "UT-B2", "UT-B4"}


def test_the_billing_csv_lists_each_paid_invoice(db):
    admin = _admin(db)
    plan = _plan(db, name="Gold")
    contractor = _contractor(db, "billing-csv@example.com", company="Beta Co")
    _invoice(db, contractor, plan, amount="20", reference="UT-CSV-1")
    today = datetime.now(ZoneInfo("Asia/Kuwait")).date()

    response = admin.get("/admin/reports/billing", params={"from": today.isoformat(), "to": today.isoformat(), "format": "csv"})

    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("paid_at,company,email,plan,kind,amount,currency,reference")
    assert any("Beta Co" in line and "UT-CSV-1" in line for line in lines[1:])


def test_a_billing_report_outside_the_period_is_empty(db):
    admin = _admin(db)
    plan = _plan(db)
    contractor = _contractor(db, "billing-old@example.com")
    _invoice(db, contractor, plan, amount="20", paid_at=NOW - timedelta(days=90), reference="UT-OLD")
    today = datetime.now(ZoneInfo("Asia/Kuwait")).date()

    body = admin.get("/admin/reports/billing", params={"from": (today - timedelta(days=3)).isoformat(), "to": today.isoformat()}).json()

    assert body["summary"]["paid_count"] == 0
    assert body["rows"] == []


# --- activation report -----------------------------------------------------------------------------


def test_the_activation_report_separates_on_time_late_and_waiting(db):
    admin = _admin(db)
    plan = _plan(db)
    quick = _contractor(db, "quick@example.com", company="Quick Co", approved=True)
    late_one = _contractor(db, "late@example.com", company="Late Co", approved=True)
    waiting = _contractor(db, "waiting@example.com", company="Waiting Co", approved=False)
    for user in (quick, late_one, waiting):
        profile = db.get(ContractorProfile, user.id)
        profile.activation_due_at = NOW + timedelta(hours=48)
    db.commit()
    _invoice(db, quick, plan, amount="70", kind=KIND_ACTIVATION, paid_at=NOW - timedelta(hours=10), reference="UT-Q")
    _invoice(db, late_one, plan, amount="70", kind=KIND_ACTIVATION, paid_at=NOW - timedelta(hours=60), reference="UT-L")
    _invoice(db, waiting, plan, amount="70", kind=KIND_ACTIVATION, paid_at=NOW - timedelta(hours=2), reference="UT-W")
    db.add(AuditLog(actor_id=None, action="contractor.activate", target_type="contractor_profile", target_id=quick.id, created_at=NOW - timedelta(hours=4)))
    db.add(AuditLog(actor_id=None, action="contractor.activate", target_type="contractor_profile", target_id=late_one.id, created_at=NOW))
    db.commit()
    today = datetime.now(ZoneInfo("Asia/Kuwait")).date()

    body = admin.get("/admin/reports/activations", params={"from": (today - timedelta(days=3)).isoformat(), "to": today.isoformat()}).json()

    assert body["summary"]["first_payments"] == 3
    assert body["summary"]["activated_within_sla"] == 1
    assert body["summary"]["activated_late"] == 1
    assert body["summary"]["still_waiting"] == 1
    assert body["summary"]["average_hours_to_activate"] == pytest.approx((6.0 + 60.0) / 2, abs=0.2)
    assert body["summary"]["activation_target_hours"] == get_settings().activation_sla_hours


# --- date handling ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-13-40", "to": "2026-11-30"},
        {"from": "2026-12-05", "to": "2026-12-01"},
        {"from": "2025-01-01", "to": "2026-11-30"},
    ],
)
def test_bad_report_dates_are_refused(db, params):
    assert _admin(db).get("/admin/reports/billing", params=params).status_code == 400


# --- billing filter on the user list (the overview numbers link here) ------------------------


def test_the_billing_filter_matches_each_overview_number(db):
    admin = _admin(db)
    paid = _contractor(db, "bill-paid@example.com", paid_until=NOW + timedelta(days=30))
    trial = _contractor(db, "bill-trial@example.com", trial_until=NOW + timedelta(days=7))
    waiting = _contractor(db, "bill-waiting@example.com", approved=False)
    overdue = _contractor(db, "bill-overdue@example.com", approved=False)
    _contractor(db, "bill-none@example.com")
    for user, due in ((waiting, NOW + timedelta(hours=20)), (overdue, NOW - timedelta(hours=2))):
        profile = db.get(ContractorProfile, user.id)
        profile.activation_due_at = due
    db.commit()

    def ids(billing):
        response = admin.get("/admin/users", params={"billing": billing, "limit": 100})
        assert response.status_code == 200
        return {item["id"] for item in response.json()["items"]}

    assert ids("paid") == {paid.id}
    assert ids("trial") == {trial.id}
    assert ids("waiting") == {waiting.id, overdue.id}
    assert ids("overdue") == {overdue.id}
    assert admin.get("/admin/users", params={"billing": "bogus"}).status_code == 400
