"""Contractor onboarding and MyFatoorah subscriptions: the wizard, invoices, payment confirmation, activation,
the status endpoint, plans, sign-up with a WhatsApp code or invitation link, and password reset by code."""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.security import hash_password
from app.config import get_settings
from app.main import app
from app.models.contractor import ContractorProfile
from app.models.enums import UserRole, VerificationStatus
from app.models.onboarding import PaymentInvoice, PortalInvite, SubscriptionPlan
from app.models.user import User
from app.services import myfatoorah, payments
from app.services.onboarding import create_invite

NOW = datetime.utcnow()
PASSWORD = "contractor-pass-1"


# --- helpers ----------------------------------------------------------------------------


def _plan(db, *, activation="50", monthly="20", active=True, name="Standard"):
    plan = SubscriptionPlan(name=name, activation_fee=Decimal(activation), monthly_fee=Decimal(monthly), currency="KWD", is_active=active)
    db.add(plan)
    db.commit()
    return plan


def _contractor(db, *, email="haddad@example.com", phone="+96511110099", verification=VerificationStatus.incomplete, details=False, paid_until=None):
    user = User(email=email, password_hash=hash_password(PASSWORD), role=UserRole.contractor, full_name="Layla Haddad", phone=phone)
    db.add(user)
    db.flush()
    profile = ContractorProfile(
        user_id=user.id,
        company_name="Haddad Builders",
        verification_status=verification,
        paid_until=paid_until,
        onboarding_completed_at=NOW if details else None,
    )
    if details:
        profile.business_address = "Block 3, Salmiya"
        profile.business_email = "office@haddad.example"
        profile.business_registration_id = "CR-778812"
        profile.trades = ["Electrical"]
    db.add(profile)
    db.commit()
    return user


def _login(email, password=PASSWORD) -> TestClient:
    client = TestClient(app)
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client


def _admin(db):
    admin = User(email="admin-onboarding@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin")
    db.add(admin)
    db.commit()
    return _login("admin-onboarding@example.com", "adminpass123")


@pytest.fixture
def paid_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "myfatoorah_api_key", "test-token")
    return settings


def _fake_invoice(monkeypatch, invoice_id=501):
    calls = []

    def fake_send(**kwargs):
        calls.append(kwargs)
        return invoice_id, f"https://pay.example/{invoice_id}"

    monkeypatch.setattr(myfatoorah, "send_payment", fake_send)
    return calls


def _fake_status(monkeypatch, status):
    monkeypatch.setattr(myfatoorah, "get_payment_status", lambda invoice_id, **kwargs: status)


DETAILS = {
    "business_name": "Haddad Builders",
    "business_address": "Block 3, Salmiya",
    "website": "haddad.example",
    "business_email": "office@haddad.example",
    "business_registration_id": "CR-778812",
    "trades": ["Electrical", "Plumbing"],
}


# --- the wizard -------------------------------------------------------------------------


def test_the_details_wizard_saves_and_marks_the_profile_complete(db):
    user = _contractor(db)
    client = _login(user.email)

    response = client.put("/contractor/onboarding", json=DETAILS)

    assert response.status_code == 200
    body = response.json()
    assert body["complete"] is True
    assert body["website"] == "https://haddad.example"
    assert body["trades"] == ["Electrical", "Plumbing"]


def test_a_trade_outside_the_list_is_refused(db):
    user = _contractor(db)
    client = _login(user.email)

    response = client.put("/contractor/onboarding", json={**DETAILS, "trades": ["Astrology"]})

    assert response.status_code == 400
    assert "Astrology" in response.json()["detail"]


def test_a_missing_registration_id_is_refused(db):
    user = _contractor(db)
    client = _login(user.email)

    response = client.put("/contractor/onboarding", json={**DETAILS, "business_registration_id": ""})

    assert response.status_code == 422


# --- invoices and payment confirmation -------------------------------------------------


def test_subscribing_needs_the_details_first(db, paid_settings, monkeypatch):
    user = _contractor(db)
    plan = _plan(db)
    _fake_invoice(monkeypatch)
    client = _login(user.email)

    response = client.post("/billing/invoices", json={"plan_id": plan.id})

    assert response.status_code == 400
    assert "business details" in response.json()["detail"]


def test_the_first_invoice_is_the_activation_fee_plus_one_month(db, paid_settings, monkeypatch):
    user = _contractor(db, details=True)
    plan = _plan(db, activation="50", monthly="20")
    calls = _fake_invoice(monkeypatch)
    client = _login(user.email)

    response = client.post("/billing/invoices", json={"plan_id": plan.id})

    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "activation"
    assert body["amount"] == "70.000"
    assert body["payment_url"] == "https://pay.example/501"
    assert calls[0]["amount"] == Decimal("70")


def test_a_paid_invoice_extends_access_and_starts_the_48_hour_deadline(db, paid_settings, monkeypatch):
    user = _contractor(db, details=True)
    plan = _plan(db)
    _fake_invoice(monkeypatch)
    client = _login(user.email)
    invoice_id = client.post("/billing/invoices", json={"plan_id": plan.id}).json()["id"]
    _fake_status(monkeypatch, myfatoorah.PAID)

    response = client.post(f"/billing/invoices/{invoice_id}/refresh")

    assert response.status_code == 200
    assert response.json()["status"] == "paid"
    profile = db.get(ContractorProfile, user.id)
    db.refresh(profile)
    assert profile.is_payment_active is True
    assert profile.activation_due_at is not None
    assert timedelta(hours=47) < profile.activation_due_at - datetime.utcnow() <= timedelta(hours=48)


def test_a_payment_notifies_the_contractor_only_once(db, paid_settings, monkeypatch):
    from app.models.notification import Notification

    user = _contractor(db, details=True)
    plan = _plan(db)
    _fake_invoice(monkeypatch)
    client = _login(user.email)
    invoice_id = client.post("/billing/invoices", json={"plan_id": plan.id}).json()["id"]
    _fake_status(monkeypatch, myfatoorah.PAID)

    client.post(f"/billing/invoices/{invoice_id}/refresh")
    client.post(f"/billing/invoices/{invoice_id}/refresh")

    assert db.query(Notification).filter(Notification.user_id == user.id).count() == 1


def test_a_webhook_body_alone_never_marks_an_invoice_paid(db, paid_settings, monkeypatch):
    user = _contractor(db, details=True)
    plan = _plan(db)
    _fake_invoice(monkeypatch, invoice_id=777)
    client = _login(user.email)
    client.post("/billing/invoices", json={"plan_id": plan.id})
    _fake_status(monkeypatch, myfatoorah.PENDING)  # MyFatoorah itself still says pending

    body = {"Event": {"Code": 1}, "Data": {"Invoice": {"Id": 777, "Status": "PAID"}}}
    response = TestClient(app).post("/billing/webhook/myfatoorah", json=body)

    assert response.status_code == 200
    invoice = db.scalar(select(PaymentInvoice).where(PaymentInvoice.myfatoorah_invoice_id == 777))
    db.refresh(invoice)
    assert invoice.status == "pending"


def test_a_webhook_with_a_bad_signature_is_refused_when_a_secret_is_set(db, paid_settings, monkeypatch):
    user = _contractor(db, details=True)
    plan = _plan(db)
    _fake_invoice(monkeypatch, invoice_id=778)
    _login(user.email).post("/billing/invoices", json={"plan_id": plan.id})
    monkeypatch.setattr(paid_settings, "myfatoorah_webhook_secret", "hook-secret")

    body = {"Data": {"Invoice": {"Id": 778, "Status": "PAID"}}}
    response = TestClient(app).post("/billing/webhook/myfatoorah", json=body, headers={"myfatoorah-signature": "wrong"})

    assert response.status_code == 403


def test_a_webhook_with_the_right_signature_is_checked_with_myfatoorah(db, paid_settings, monkeypatch):
    user = _contractor(db, details=True)
    plan = _plan(db)
    _fake_invoice(monkeypatch, invoice_id=779)
    _login(user.email).post("/billing/invoices", json={"plan_id": plan.id})
    monkeypatch.setattr(paid_settings, "myfatoorah_webhook_secret", "hook-secret")
    _fake_status(monkeypatch, myfatoorah.PAID)

    body = {"Data": {"Invoice": {"Id": 779, "Status": "PAID"}, "Transaction": {"Status": "SUCCESS", "PaymentId": "p1"}}}
    text = myfatoorah._signed_text(body["Data"])
    good = base64.b64encode(hmac.new(b"hook-secret", text.encode(), hashlib.sha256).digest()).decode()
    response = TestClient(app).post("/billing/webhook/myfatoorah", json=body, headers={"myfatoorah-signature": good})

    assert response.status_code == 200
    invoice = db.scalar(select(PaymentInvoice).where(PaymentInvoice.myfatoorah_invoice_id == 779))
    db.refresh(invoice)
    assert invoice.status == "paid"


def test_a_repeated_paid_result_does_not_extend_access_again(db, paid_settings, monkeypatch):
    user = _contractor(db, details=True)
    plan = _plan(db)
    _fake_invoice(monkeypatch)
    client = _login(user.email)
    invoice_id = client.post("/billing/invoices", json={"plan_id": plan.id}).json()["id"]
    _fake_status(monkeypatch, myfatoorah.PAID)
    client.post(f"/billing/invoices/{invoice_id}/refresh")
    profile = db.get(ContractorProfile, user.id)
    db.refresh(profile)
    first_until = profile.paid_until

    client.post(f"/billing/invoices/{invoice_id}/refresh")
    db.refresh(profile)

    assert profile.paid_until == first_until


# --- activation and the status endpoint --------------------------------------------------


def test_status_moves_from_details_to_subscribe_to_awaiting_to_active(db, paid_settings, monkeypatch):
    user = _contractor(db)
    client = _login(user.email)
    assert client.get("/contractor/status").json()["next_step"] == "details"

    client.put("/contractor/onboarding", json=DETAILS)
    assert client.get("/contractor/status").json()["next_step"] == "subscribe"

    plan = _plan(db)
    _fake_invoice(monkeypatch)
    invoice_id = client.post("/billing/invoices", json={"plan_id": plan.id}).json()["id"]
    _fake_status(monkeypatch, myfatoorah.PAID)
    client.post(f"/billing/invoices/{invoice_id}/refresh")
    awaiting = client.get("/contractor/status").json()
    assert awaiting["next_step"] == "awaiting_activation"
    assert awaiting["can_bid"] is False

    _admin(db).post(f"/admin/contractors/{user.id}/activate")
    active = client.get("/contractor/status").json()
    assert active["next_step"] == "active"
    assert active["can_bid"] is True


def test_the_admin_cannot_activate_an_unpaid_contractor(db):
    user = _contractor(db, details=True)
    admin = _admin(db)

    response = admin.post(f"/admin/contractors/{user.id}/activate")

    assert response.status_code == 400
    assert "not paid" in response.json()["detail"]


def test_the_activation_queue_shows_the_deadline_and_flags_overdue(db, paid_settings):
    user = _contractor(db, details=True, paid_until=NOW + timedelta(days=30))
    profile = db.get(ContractorProfile, user.id)
    profile.activation_due_at = NOW - timedelta(hours=1)
    db.commit()

    rows = _admin(db).get("/admin/activations").json()

    assert len(rows) == 1
    assert rows[0]["overdue"] is True
    assert rows[0]["contractor_id"] == user.id


# --- plans ----------------------------------------------------------------------------------


def test_admin_plans_and_only_active_plans_reach_the_contractor(db):
    user = _contractor(db, details=True)
    admin = _admin(db)
    created = admin.post("/admin/plans", json={"name": "Gold", "activation_fee": "30", "monthly_fee": "15", "currency": "kwd"})
    assert created.status_code == 201
    assert created.json()["currency"] == "KWD"
    hidden = admin.post("/admin/plans", json={"name": "Retired", "activation_fee": "0", "monthly_fee": "9", "is_active": False})
    assert hidden.status_code == 201

    shown = _login(user.email).get("/billing/plans").json()

    assert [plan["name"] for plan in shown] == ["Gold"]


# --- sign-up and password reset with codes or invitations ------------------------------


def test_sign_up_with_a_whatsapp_code(db, monkeypatch):
    sent = {}
    monkeypatch.setattr("app.auth.code_auth.send_code", lambda phone, code: sent.update(phone=phone, code=code))
    client = TestClient(app)

    assert client.post("/auth/contractor/code/request", json={"phone": "+965 9944 4463"}).status_code == 200
    wrong = client.post(
        "/auth/contractor/signup",
        json={"phone": "96599444463", "code": "000000", "email": "new@haddad.example", "password": "new-pass-123",
              "full_name": "Sara Haddad", "company_name": "Haddad Two"},
    )
    assert wrong.status_code == 400

    created = client.post(
        "/auth/contractor/signup",
        json={"phone": "96599444463", "code": sent["code"], "email": "new@haddad.example", "password": "new-pass-123",
              "full_name": "Sara Haddad", "company_name": "Haddad Two"},
    )

    assert created.status_code == 201
    user = db.scalar(select(User).where(User.email == "new@haddad.example"))
    assert user.role == UserRole.contractor
    assert user.phone == "+96599444463"


def test_a_code_is_locked_after_too_many_wrong_tries(db, monkeypatch):
    sent = {}
    monkeypatch.setattr("app.auth.code_auth.send_code", lambda phone, code: sent.update(code=code))
    client = TestClient(app)
    client.post("/auth/contractor/code/request", json={"phone": "96588887777"})
    for _ in range(get_settings().otp_max_attempts):
        client.post("/auth/contractor/signup", json={"phone": "96588887777", "code": "111111", "email": "x@haddad.example",
                                                       "password": "new-pass-123", "full_name": "Ali", "company_name": "Ali Co"})

    response = client.post("/auth/contractor/signup", json={"phone": "96588887777", "code": sent["code"], "email": "x@haddad.example",
                                                             "password": "new-pass-123", "full_name": "Ali", "company_name": "Ali Co"})

    assert response.status_code == 400


def test_the_invitation_link_works_once_and_adds_the_login(db):
    user = User(email=None, password_hash=None, role=UserRole.contractor, full_name="Wa Contractor", phone="+96566665555")
    db.add(user)
    db.flush()
    db.add(ContractorProfile(user_id=user.id, company_name="Wa Co"))
    db.commit()
    link = create_invite(db, user.id, now=NOW)
    db.commit()
    token = link.split("token=")[1]
    client = TestClient(app)

    first = client.post("/auth/contractor/complete-invite", json={"token": token, "email": "wa@haddad.example", "password": "new-pass-123"})
    second = client.post("/auth/contractor/complete-invite", json={"token": token, "email": "other@haddad.example", "password": "new-pass-123"})

    assert first.status_code == 200
    assert second.status_code == 400
    assert _login("wa@haddad.example", "new-pass-123").get("/auth/me").json()["role"] == "contractor"


def test_an_expired_invitation_is_refused(db):
    user = User(email=None, password_hash=None, role=UserRole.contractor, full_name="Late", phone="+96577776666")
    db.add(user)
    db.flush()
    db.add(ContractorProfile(user_id=user.id, company_name="Late Co"))
    db.commit()
    token = create_invite(db, user.id, now=NOW).split("token=")[1]
    invite = db.scalar(select(PortalInvite).where(PortalInvite.user_id == user.id))
    invite.expires_at = NOW - timedelta(minutes=1)
    db.commit()

    response = TestClient(app).post("/auth/contractor/complete-invite", json={"token": token, "email": "late@haddad.example", "password": "new-pass-123"})

    assert response.status_code == 400


def test_password_reset_by_code_and_the_same_answer_for_unknown_emails(db, monkeypatch):
    user = _contractor(db, email="reset@haddad.example", phone="+96544443333")
    sent = {}
    monkeypatch.setattr("app.auth.code_auth.send_code", lambda phone, code: sent.update(code=code))
    client = TestClient(app)

    known = client.post("/auth/password-reset/request", json={"email": "reset@haddad.example"})
    unknown = client.post("/auth/password-reset/request", json={"email": "nobody@haddad.example"})
    assert known.json() == unknown.json()

    confirmed = client.post("/auth/password-reset/confirm", json={"email": "reset@haddad.example", "code": sent["code"], "new_password": "brand-new-1"})

    assert confirmed.status_code == 200
    _login("reset@haddad.example", "brand-new-1")  # asserts the new password works
