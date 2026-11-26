"""Who may send offers: a paid subscription, an admin-set trial, or neither. Checked on the web and on WhatsApp.

Also: the admin's manual paid-until and trial-until dates, the MyFatoorah settings the admin enters in the app,
plan deletion, and a guard that Stripe is gone.
"""

import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.security import hash_password
from app.config import Settings, get_settings
from app.main import app
from app.models.app_setting import AppSetting
from app.models.audit_log import AuditLog
from app.models.contractor import ContractorProfile
from app.models.enums import ProjectStatus, TenderType, UserRole, VerificationStatus
from app.models.offer import Offer
from app.models.onboarding import PaymentInvoice, SubscriptionPlan
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.user import User
from app.routers import whatsapp as whatsapp_router
from app.services import myfatoorah
from app.services.app_settings import myfatoorah_config
from app.services.whatsapp_identity import get_or_create_identity
from app.services.whatsapp_routing import install_whatsapp_handlers
from flow_contract import check_reply
from whatsapp_helpers import RecordingSender, enable_whatsapp, flow_request, message_envelope, sign, text_message

NOW = datetime.utcnow()
FUTURE = NOW + timedelta(days=10)
PASSWORD = "billing-pass-1"


@pytest.fixture(autouse=True)
def _handlers():
    install_whatsapp_handlers()
    yield


# --- helpers ----------------------------------------------------------------------------


def _owner(db):
    user = User(email="owner-billing@example.com", password_hash=hash_password(PASSWORD), role=UserRole.owner, full_name="Layla", email_verified=True)
    db.add(user)
    db.flush()
    db.add(OwnerProfile(user_id=user.id, verification_status=VerificationStatus.approved))
    db.commit()
    return user


def _project(db, owner):
    project = Project(
        owner_id=owner.id, title="Villa renovation", address="Block 3, Salmiya", trade="Electrical", description="Ground floor",
        bid_deadline=FUTURE, status=ProjectStatus.open, tender_type=TenderType.owner_visible,
    )
    db.add(project)
    db.commit()
    return project


def _contractor(db, *, email, wa_id=None, paid_until=None, trial_until=None, approved=True, details=True):
    user = User(
        email=email, password_hash=hash_password(PASSWORD), role=UserRole.contractor, full_name="Omar Haddad",
        phone=f"+{wa_id}" if wa_id else None,
    )
    db.add(user)
    db.flush()
    db.add(
        ContractorProfile(
            user_id=user.id,
            company_name=f"{email} Co",
            primary_trade="Electrical",
            verification_status=VerificationStatus.approved if approved else VerificationStatus.incomplete,
            paid_until=paid_until,
            trial_until=trial_until,
            onboarding_completed_at=NOW if details else None,
        )
    )
    if wa_id:
        identity = get_or_create_identity(db, wa_id, now=NOW)
        identity.user_id = user.id
        identity.role = "contractor"
    db.commit()
    return user


def _login(email, password=PASSWORD) -> TestClient:
    client = TestClient(app)
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client


def _admin(db) -> TestClient:
    admin = User(email="admin-billing@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin")
    db.add(admin)
    db.commit()
    return _login("admin-billing@example.com", "adminpass123")


def _web_offer(email, project_id):
    return _login(email).post(f"/projects/{project_id}/offers", json={"amount": "4300.00"})


# WhatsApp: the contractor opens the dashboard and drives the Flow, as a real contractor does.


def _open_dashboard(client, monkeypatch, sender, wa_id, tag) -> str:
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)
    raw = json.dumps(message_envelope(text_message(f"wamid.BA{tag}", wa_id, "menu"))).encode()
    client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})
    return sender.flows()[-1]["flow_token"]


def _flow(client, pem, token, screen, data, action="data_exchange"):
    reply = flow_request(client, pem, token=token, action=action, screen=screen, data=data)[0]
    if reply is not None:
        check_reply("contractor_dashboard", reply)
    return reply


# --- offers on the web ----------------------------------------------------------------------


def test_a_paid_contractor_can_send_an_offer_on_the_web(db):
    project = _project(db, _owner(db))
    _contractor(db, email="paid@example.com", paid_until=NOW + timedelta(days=30))
    assert _web_offer("paid@example.com", project.id).status_code == 200


def test_a_contractor_on_trial_can_send_an_offer_without_a_subscription(db):
    project = _project(db, _owner(db))
    _contractor(db, email="trial@example.com", trial_until=NOW + timedelta(days=7))
    response = _web_offer("trial@example.com", project.id)
    assert response.status_code == 200, response.text


def test_an_expired_trial_is_refused_on_the_web(db):
    project = _project(db, _owner(db))
    _contractor(db, email="expired@example.com", trial_until=NOW - timedelta(days=1))
    response = _web_offer("expired@example.com", project.id)
    assert response.status_code == 403
    assert response.json()["detail"] == "payment_required"


def test_a_contractor_with_no_trial_and_no_subscription_is_refused(db):
    project = _project(db, _owner(db))
    _contractor(db, email="nothing@example.com")
    assert _web_offer("nothing@example.com", project.id).status_code == 403


def test_a_trial_does_not_skip_approval(db):
    project = _project(db, _owner(db))
    _contractor(db, email="unapproved@example.com", trial_until=NOW + timedelta(days=7), approved=False)
    assert _web_offer("unapproved@example.com", project.id).status_code == 403


# --- offers on WhatsApp ----------------------------------------------------------------------


def test_a_trial_contractor_can_submit_an_offer_on_whatsapp(client, monkeypatch, db):
    _, pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    project = _project(db, _owner(db))
    _contractor(db, email="wa-trial@example.com", wa_id="96533330001", trial_until=NOW + timedelta(days=7))
    token = _open_dashboard(client, monkeypatch, sender, "96533330001", "T")

    form = _flow(client, pem, token, "PROJECT_DETAILS", {"project_id": project.id, "action": "submit"})
    assert form["screen"] == "SUBMIT_OFFER"
    review = _flow(client, pem, token, "SUBMIT_OFFER", {"quotation": [{"file_name": "quotation.pdf", "cdn_url": "https://cdn.example/quote", "encryption_metadata": {}}], "project_id": project.id, "amount": "12500", "timeline": "6 months", "message": "Ready"})
    assert review["screen"] == "REVIEW_OFFER"
    done = _flow(client, pem, token, "REVIEW_OFFER", {"project_id": project.id, "amount": "12500", "timeline": "6 months", "message": "Ready", "decision": "submit"})

    assert done["screen"] == "DONE"
    offer = db.scalar(select(Offer).where(Offer.project_id == project.id))
    assert offer is not None and float(offer.amount) == 12500.0


def test_an_expired_trial_is_turned_back_on_whatsapp(client, monkeypatch, db):
    _, pem = enable_whatsapp(monkeypatch)
    sender = RecordingSender()
    project = _project(db, _owner(db))
    _contractor(db, email="wa-expired@example.com", wa_id="96533330002", trial_until=NOW - timedelta(days=1))
    token = _open_dashboard(client, monkeypatch, sender, "96533330002", "E")

    reply = _flow(client, pem, token, "PROJECT_DETAILS", {"project_id": project.id, "action": "submit"})

    assert reply["screen"] == "MENU"
    assert "subscription" in reply["data"]["error_message"].lower()
    assert db.scalar(select(Offer).where(Offer.project_id == project.id)) is None


# --- admin: manual paid-until and trial-until dates ---------------------------------------


def test_an_admin_sets_a_trial_end_date_and_the_change_is_audited(db):
    user = _contractor(db, email="target@example.com")
    admin = _admin(db)
    end = (date.today() + timedelta(days=30)).isoformat()

    response = admin.patch(f"/admin/contractors/{user.id}/billing", json={"trial_until": end, "reason": "Trial agreed by phone"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["trial_active"] is True
    assert body["payment_active"] is True
    assert body["active"] is True
    row = db.query(AuditLog).filter_by(action="contractor.trial_until", target_id=user.id).one()
    assert row.reason == "Trial agreed by phone"


def test_an_admin_clears_a_trial_and_the_access_stops(db):
    user = _contractor(db, email="clear@example.com", trial_until=NOW + timedelta(days=7))
    response = _admin(db).patch(f"/admin/contractors/{user.id}/billing", json={"trial_until": None, "reason": "Trial ended early"})
    assert response.status_code == 200
    assert response.json()["trial_active"] is False
    assert response.json()["active"] is False


def test_a_billing_change_needs_a_reason(db):
    user = _contractor(db, email="noreason@example.com")
    response = _admin(db).patch(f"/admin/contractors/{user.id}/billing", json={"trial_until": "2031-01-01"})
    assert response.status_code == 422


def test_a_billing_change_with_no_dates_is_refused(db):
    user = _contractor(db, email="nodates@example.com")
    response = _admin(db).patch(f"/admin/contractors/{user.id}/billing", json={"reason": "Nothing to change"})
    assert response.status_code == 400


def test_a_contractor_cannot_change_their_own_billing(db):
    user = _contractor(db, email="self@example.com")
    response = _login("self@example.com").patch(f"/admin/contractors/{user.id}/billing", json={"trial_until": "2031-01-01", "reason": "Me"})
    assert response.status_code == 403


# --- admin: MyFatoorah settings entered in the app --------------------------------------


@pytest.fixture
def no_env_payment_keys(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "myfatoorah_api_key", None)
    monkeypatch.setattr(settings, "myfatoorah_webhook_secret", None)
    monkeypatch.setattr(settings, "myfatoorah_base_url", "https://apitest.myfatoorah.com")
    monkeypatch.setattr(settings, "whatsapp_otp_template", None)


def test_an_admin_enters_the_api_key_and_only_a_hint_is_shown(db, no_env_payment_keys):
    admin = _admin(db)
    response = admin.put("/admin/settings/billing", json={"myfatoorah_api_key": "KEY-ABCDEFGH1234"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["myfatoorah_api_key"] == {"configured": True, "hint": "...1234", "source": "admin"}
    assert body["payments_ready"] is True
    assert "KEY-ABCDEFGH1234" not in response.text
    assert "KEY-ABCDEFGH1234" not in admin.get("/admin/settings/billing").text


def test_the_saved_key_is_stored_encrypted_and_used(db, no_env_payment_keys):
    _admin(db).put("/admin/settings/billing", json={"myfatoorah_api_key": "KEY-SAVED-0001"})
    db.expire_all()
    stored = db.get(AppSetting, "myfatoorah_api_key")
    assert stored.value != "KEY-SAVED-0001"
    assert stored.is_secret is True
    assert myfatoorah_config(db).api_key == "KEY-SAVED-0001"


def test_the_secret_never_reaches_the_audit_log(db, no_env_payment_keys):
    _admin(db).put("/admin/settings/billing", json={"myfatoorah_api_key": "KEY-AUDIT-9999"})
    rows = db.query(AuditLog).filter_by(action="setting.update", target_id="myfatoorah_api_key").all()
    assert rows and all("KEY-AUDIT-9999" not in json.dumps({"p": r.previous_value, "n": r.new_value}) for r in rows)
    assert rows[-1].new_value == "set"


def test_an_invoice_is_created_with_the_key_the_admin_entered(db, monkeypatch, no_env_payment_keys):
    user = _contractor(db, email="invoice@example.com")
    plan = SubscriptionPlan(name="Standard", activation_fee=50, monthly_fee=20, currency="KWD", is_active=True)
    db.add(plan)
    db.commit()
    _admin(db).put("/admin/settings/billing", json={"myfatoorah_api_key": "KEY-INVOICE-5555"})
    seen = {}

    def fake_send(**kwargs):
        seen["key"] = kwargs["config"].api_key
        return 701, "https://pay.example/701"

    monkeypatch.setattr(myfatoorah, "send_payment", fake_send)
    response = _login("invoice@example.com").post("/billing/invoices", json={"plan_id": plan.id})

    assert response.status_code == 201, response.text
    assert seen["key"] == "KEY-INVOICE-5555"


def test_clearing_the_key_falls_back_to_the_env_value(db, no_env_payment_keys, monkeypatch):
    admin = _admin(db)
    admin.put("/admin/settings/billing", json={"myfatoorah_api_key": "KEY-TEMP-1111"})
    monkeypatch.setattr(get_settings(), "myfatoorah_api_key", "ENV-KEY-2222")

    response = admin.put("/admin/settings/billing", json={"myfatoorah_api_key": ""})

    assert response.json()["myfatoorah_api_key"]["source"] == "env"
    assert myfatoorah_config(db).api_key == "ENV-KEY-2222"


def test_the_base_address_must_be_https(db, no_env_payment_keys):
    response = _admin(db).put("/admin/settings/billing", json={"myfatoorah_base_url": "http://insecure.example"})
    assert response.status_code == 400


def test_a_contractor_cannot_read_the_payment_settings(db, no_env_payment_keys):
    _contractor(db, email="reader@example.com")
    assert _login("reader@example.com").get("/admin/settings/billing").status_code == 403


# --- admin: plans -------------------------------------------------------------------------


def test_an_admin_updates_then_deletes_a_plan_with_no_invoices(db):
    plan = SubscriptionPlan(name="Gold", activation_fee=30, monthly_fee=15, currency="KWD", is_active=True)
    db.add(plan)
    db.commit()
    plan_id = plan.id
    admin = _admin(db)

    updated = admin.patch(f"/admin/plans/{plan_id}", json={"monthly_fee": "25"})
    assert updated.status_code == 200
    assert float(updated.json()["monthly_fee"]) == 25.0

    assert admin.delete(f"/admin/plans/{plan_id}").status_code == 204
    db.expire_all()
    assert db.get(SubscriptionPlan, plan_id) is None


def test_a_plan_with_invoices_cannot_be_deleted(db):
    user = _contractor(db, email="billed@example.com")
    plan = SubscriptionPlan(name="Silver", activation_fee=10, monthly_fee=5, currency="KWD", is_active=True)
    db.add(plan)
    db.flush()
    db.add(PaymentInvoice(contractor_id=user.id, plan_id=plan.id, kind="activation", amount=15, currency="KWD", reference="UT-billed-1", status="pending"))
    db.commit()

    response = _admin(db).delete(f"/admin/plans/{plan.id}")

    assert response.status_code == 409
    assert "Hide it instead" in response.json()["detail"]


def test_deleting_an_unknown_plan_is_not_found(db):
    assert _admin(db).delete("/admin/plans/no-such-plan").status_code == 404


# --- Stripe is gone ------------------------------------------------------------------------


def test_no_stripe_setting_is_left():
    assert not [name for name in Settings.model_fields if "stripe" in name.lower()]
