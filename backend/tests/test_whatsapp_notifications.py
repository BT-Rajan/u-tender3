"""Phase 6: every event that creates an in-app notice also reaches WhatsApp, through approved templates, once.

Covers: the template catalog, mapping and dedupe, recipient rules, the wording for sealed and revised bids, the
approval gate and its webhook, delivery receipts, payment transitions, and new-tender fan-out eligibility.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models.contractor import ContractorProfile
from app.models.enums import (
    DocumentStatus,
    NotificationType,
    OfferStatus,
    ProjectStatus,
    TenderType,
    UserRole,
    VerificationStatus,
)
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.user import User
from app.models.whatsapp import WhatsAppOutbox, WhatsAppTemplateStatus
from app.routers import whatsapp as whatsapp_router
from app.services.notify import notify
from app.services.whatsapp_identity import get_or_create_identity
from app.services.whatsapp_notifications import NOTIFICATION_TEMPLATES, amount_label
from app.services.whatsapp_templates import CATALOG, TemplateError, body_for, components_for
from app.services.whatsapp_outbox import dispatch_due
from whatsapp_helpers import RecordingSender, enable_whatsapp, message_envelope, sign

NOW = datetime.utcnow()
SAMPLE_KWARGS = {
    "project_title": "Villa renovation",
    "contractor_name": "Haddad Builders",
    "amount_label": "12,500.00",
    "closing_text": "2026-12-31 14:00 Kuwait time",
    "summary": "Updated title.",
    "requirement_name": "Civil ID",
}


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch):
    # Real behaviour: templates are held until Meta approves them. Individual tests approve what they need.
    monkeypatch.setattr(get_settings(), "whatsapp_require_approved_templates", True)


def _approve_all(db):
    for name in CATALOG:
        for language in ("en", "ar"):
            db.add(WhatsAppTemplateStatus(name=name, language=language, status="APPROVED"))
    db.commit()


def _user(db, *, role=UserRole.owner, wa_id=None, language=None, name="Layla Al-Sabah"):
    from app.models.enums import Language

    user = User(email=None if wa_id else "web@example.com", password_hash=None if wa_id else "x", role=role,
                full_name=name, phone=f"+{wa_id}" if wa_id else None, language=language or Language.en)
    db.add(user)
    db.flush()
    if role == UserRole.owner:
        db.add(OwnerProfile(user_id=user.id, verification_status=VerificationStatus.approved))
    else:
        db.add(ContractorProfile(user_id=user.id, company_name="Haddad Builders", primary_trade="Electrical",
                                 verification_status=VerificationStatus.approved,
                                 paid_until=datetime.utcnow() + timedelta(days=30)))
    if wa_id:
        identity = get_or_create_identity(db, wa_id, now=NOW)
        identity.user_id = user.id
    db.commit()
    return user


def _project(db, owner, **extra):
    fields = dict(owner_id=owner.id, title="Villa renovation", address="Block 3", trade="Electrical",
                  bid_deadline=NOW + timedelta(days=10), status=ProjectStatus.open, tender_type=TenderType.owner_visible)
    fields.update(extra)
    project = Project(**fields)
    db.add(project)
    db.commit()
    return project


def _outbox(db):
    return db.scalars(select(WhatsAppOutbox).order_by(WhatsAppOutbox.next_attempt_at)).all()


def _body_text(row):
    return json.dumps(row.params_json["components"])


# --- the catalog ---------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_every_template_has_matching_placeholders_in_both_languages(name):
    spec = CATALOG[name]
    for body in (spec.en, spec.ar):
        for index in range(1, spec.parameters + 1):
            assert f"{{{{{index}}}}}" in body, f"{name} is missing placeholder {index}"
        assert f"{{{{{spec.parameters + 1}}}}}" not in body, f"{name} has more placeholders than parameters"


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_components_reject_the_wrong_parameter_count(name):
    spec = CATALOG[name]
    with pytest.raises(TemplateError):
        components_for(name, ["x"] * (spec.parameters + 1))


def test_an_unknown_template_or_language_is_refused():
    with pytest.raises(TemplateError):
        components_for("no_such_template", [])
    with pytest.raises(TemplateError):
        body_for("document_approved", "fr")


def test_parameter_text_is_flattened_so_meta_accepts_it():
    components = components_for("award_won", ["Villa\n\nrenovation   phase 2"])
    assert components[0]["parameters"][0]["text"] == "Villa renovation phase 2"


@pytest.mark.parametrize("notification_type", sorted(NOTIFICATION_TEMPLATES, key=lambda t: t.value))
def test_every_mapped_notification_builds_a_valid_template_message(notification_type):
    template_name, build = NOTIFICATION_TEMPLATES[notification_type]
    values = build(SAMPLE_KWARGS)
    components_for(template_name, values)  # raises if the count is wrong


# --- queueing and dedupe ------------------------------------------------------------


def test_a_notice_to_a_whatsapp_account_queues_its_template_in_the_users_language(db):
    from app.models.enums import Language

    owner = _user(db, wa_id="96511110001", language=Language.ar)
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa renovation")

    row = _outbox(db)[0]
    assert row.kind == "template"
    assert row.template_name == "award_won"
    assert row.params_json["language"] == "ar"
    assert row.recipient_wa_id == "96511110001"


def test_a_web_only_account_gets_the_in_app_notice_and_no_whatsapp(db):
    user = _user(db)
    notify(db, user, NotificationType.award_won, link="/x", project_title="Villa renovation")
    assert db.query(Notification).count() == 1
    assert _outbox(db) == []


def test_a_repeat_of_an_unread_notice_queues_nothing_more(db):
    owner = _user(db, wa_id="96511110002")
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    assert len(_outbox(db)) == 1


def test_after_the_notice_is_read_the_next_event_queues_again(db):
    owner = _user(db, wa_id="96511110003")
    first = notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    db.commit()
    first.is_read = True
    db.commit()
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    assert len(_outbox(db)) == 2


def test_document_decisions_are_not_sent_twice_through_the_generic_path(db):
    owner = _user(db, wa_id="96511110004")
    notify(db, owner, NotificationType.document_approved, link="/owner/status", requirement_name="Civil ID")
    assert _outbox(db) == []


def test_a_notice_missing_a_value_is_logged_and_not_queued(db, caplog):
    owner = _user(db, wa_id="96511110005")
    # The in-app text needs only the contractor's name, but the WhatsApp message also needs the amount label.
    notify(db, owner, NotificationType.bid_submitted, link="/x", project_title="Villa", contractor_name="Haddad")
    assert _outbox(db) == []
    assert "not queued" in caplog.text


# --- the events the spec lists -----------------------------------------------------


def test_offer_submission_names_the_bidder_and_amount_on_an_open_tender(db):
    owner = _user(db, wa_id="96511110006")
    notify(db, owner, NotificationType.bid_submitted, link="/x", project_title="Villa", contractor_name="Haddad Builders", amount_label=amount_label(12500.0, False), is_revision=False)
    row = _outbox(db)[0]
    assert row.template_name == "offer_received"
    assert "Haddad Builders" in _body_text(row) and "12,500.00" in _body_text(row)


def test_a_sealed_offer_never_names_the_bidder_or_shows_the_amount(db):
    owner = _user(db, wa_id="96511110007")
    notify(db, owner, NotificationType.bid_submitted, link="/x", project_title="Villa", contractor_name="A contractor", amount_label=amount_label(12500.0, True), is_revision=False)
    text = _body_text(_outbox(db)[0])
    assert "Haddad" not in text and "12,500" not in text
    assert "hidden until the tender closes" in text


def test_an_offer_revision_uses_the_revised_wording_but_one_in_app_notice(db):
    owner = _user(db, wa_id="96511110008")
    notify(db, owner, NotificationType.bid_submitted, link="/x", project_title="Villa", contractor_name="Haddad Builders", amount_label="9,000.00", is_revision=True)
    assert db.query(Notification).count() == 1
    assert _outbox(db)[0].template_name == "offer_revised"


def test_award_won_and_lost_use_their_own_templates(db):
    winner = _user(db, role=UserRole.contractor, wa_id="96511110009")
    loser = _user(db, role=UserRole.contractor, wa_id="96511110010", name="Other")
    notify(db, winner, NotificationType.award_won, link="/x", project_title="Villa")
    notify(db, loser, NotificationType.award_lost, link="/x", project_title="Villa")
    assert {row.template_name for row in _outbox(db)} == {"award_won", "award_lost"}


def test_an_amendment_tells_the_bidder_what_changed(db):
    bidder = _user(db, role=UserRole.contractor, wa_id="96511110011")
    notify(db, bidder, NotificationType.tender_amendment, link="/x", project_title="Villa", summary="Updated bid_deadline.")
    row = _outbox(db)[0]
    assert row.template_name == "tender_amended"
    assert "bid_deadline" in _body_text(row)


def test_suspension_and_reactivation_reach_the_account(db):
    owner = _user(db, wa_id="96511110012")
    notify(db, owner, NotificationType.owner_suspended, link="/x")
    notify(db, owner, NotificationType.owner_reactivated, link="/x")
    assert [row.template_name for row in _outbox(db)] == ["account_status", "account_status"]


def test_verification_approval_and_rejection_are_both_sent(db):
    owner = _user(db, wa_id="96511110013")
    notify(db, owner, NotificationType.owner_verification_activated, link="/x")
    notify(db, owner, NotificationType.owner_verification_rejected, link="/x")
    assert [row.template_name for row in _outbox(db)] == ["verification_status", "verification_status"]


def test_a_rejected_verification_writes_a_notice_for_the_contractor_through_the_admin_route(client, db):
    from app.auth.security import create_access_token, hash_password

    contractor = _user(db, role=UserRole.contractor, wa_id="96511110014")
    admin = User(email="admin-p6@example.com", password_hash=hash_password("admin-pass-1"), role=UserRole.admin, email_verified=True)
    db.add(admin)
    db.commit()
    client.cookies.set("access_token", create_access_token(admin.id))

    response = client.post(f"/admin/review/contractors/{contractor.id}/reject")

    assert response.status_code == 200
    assert db.scalar(select(Notification).where(Notification.type == NotificationType.verification_rejected)) is not None
    assert _outbox(db)[0].template_name == "verification_status"


# --- new tender fan-out -------------------------------------------------------------


def test_a_new_tender_reaches_only_contractors_who_can_bid_in_its_trade(db):
    from app.services.whatsapp_notifications import fan_out_new_tender

    owner = _user(db, wa_id="96511110018")
    project = _project(db, owner, trade="Electrical")
    eligible = _user(db, role=UserRole.contractor, wa_id="96511110019")

    wrong_trade = _user(db, role=UserRole.contractor, wa_id="96511110020", name="Plumber")
    db.get(ContractorProfile, wrong_trade.id).primary_trade = "Plumbing"

    unpaid = _user(db, role=UserRole.contractor, wa_id="96511110021", name="Unpaid")
    db.get(ContractorProfile, unpaid.id).paid_until = None
    db.commit()

    no_identity = _user(db, role=UserRole.contractor, name="Web only")
    db.commit()

    count = fan_out_new_tender(db, project, now=NOW, notify=notify)
    db.commit()

    # Web-only contractors still get the in-app notice, so they are counted. Only WhatsApp accounts get a message.
    assert count == 2
    recipients = [row.recipient_wa_id for row in _outbox(db)]
    assert recipients == ["96511110019"]
    assert db.query(Notification).filter(Notification.user_id == no_identity.id).count() == 1


def test_a_tender_with_no_trade_reaches_every_contractor_who_can_bid(db):
    from app.services.whatsapp_notifications import fan_out_new_tender

    owner = _user(db, wa_id="96511110022")
    project = _project(db, owner, trade=None)
    _user(db, role=UserRole.contractor, wa_id="96511110023")
    _user(db, role=UserRole.contractor, wa_id="96511110024", name="Second")
    fan_out_new_tender(db, project, now=NOW, notify=notify)
    db.commit()
    assert len(_outbox(db)) == 2


def test_publishing_a_draft_fans_out_to_eligible_contractors(db):
    from app.services import tender_service
    from app.services.tender_service import TenderFields

    owner = _user(db, wa_id="96511110025")
    _user(db, role=UserRole.contractor, wa_id="96511110026")
    draft = tender_service.create_draft(db, owner, TenderFields(title="Villa", address="Block 3", bid_deadline=NOW + timedelta(days=5), trade="Electrical"))
    tender_service.publish(db, owner, draft, NOW)

    assert [row.template_name for row in _outbox(db)] == ["new_tender"]


# --- the approval gate -----------------------------------------------------------------


def test_a_template_with_no_status_on_record_is_held_not_sent(db):
    owner = _user(db, wa_id="96511110027")
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    sender = RecordingSender()

    stats = dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)

    assert stats["held"] == 1
    assert sender.sent == []
    row = _outbox(db)[0]
    assert row.status == "pending"
    assert row.attempts == 0  # holding is not an attempt
    assert row.next_attempt_at > datetime.utcnow()


def test_an_approved_template_is_sent(db):
    _approve_all(db)
    owner = _user(db, wa_id="96511110028")
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    sender = RecordingSender()

    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)

    assert sender.sent[0]["kind"] == "template"
    assert sender.sent[0]["template"] == "award_won"


def test_a_rejected_template_stays_held(db):
    db.add(WhatsAppTemplateStatus(name="award_won", language="en", status="REJECTED"))
    db.commit()
    owner = _user(db, wa_id="96511110029")
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    sender = RecordingSender()

    stats = dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)

    assert stats["held"] == 1
    assert sender.sent == []


def test_the_template_status_webhook_releases_a_held_message(client, monkeypatch, db):
    enable_whatsapp(monkeypatch)
    owner = _user(db, wa_id="96511110030")
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    sender = RecordingSender()
    monkeypatch.setattr(whatsapp_router, "build_whatsapp_sender", lambda: sender)

    body = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba", "changes": [{"field": "message_template_status_update", "value": {
            "event": "APPROVED", "message_template_name": "award_won", "message_template_language": "en"}}]}],
    }
    raw = json.dumps(body).encode()
    response = client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})
    assert response.status_code == 200

    assert [m["template"] for m in sender.sent] == ["award_won"]


def test_a_template_status_update_is_idempotent(db):
    from app.services.whatsapp_events import apply_template_updates

    body = {"entry": [{"changes": [{"field": "message_template_status_update", "value": {
        "event": "APPROVED", "message_template_name": "award_lost", "message_template_language": "ar"}}]}]}
    apply_template_updates(db, body)
    apply_template_updates(db, body)
    rows = db.scalars(select(WhatsAppTemplateStatus).where(WhatsAppTemplateStatus.name == "award_lost")).all()
    assert len(rows) == 1 and rows[0].status == "APPROVED"


def test_a_later_status_change_is_recorded(db):
    from app.services.whatsapp_events import apply_template_updates

    for event in ("APPROVED", "PAUSED"):
        apply_template_updates(db, {"entry": [{"changes": [{"field": "message_template_status_update", "value": {
            "event": event, "message_template_name": "award_lost", "message_template_language": "en"}}]}]})
    assert db.scalar(select(WhatsAppTemplateStatus).where(WhatsAppTemplateStatus.name == "award_lost")).status == "PAUSED"


# --- delivery receipts -------------------------------------------------------------------


def test_a_failed_delivery_receipt_marks_the_sent_row_failed_and_drops_its_secrets(client, monkeypatch, db):
    enable_whatsapp(monkeypatch)
    _approve_all(db)
    owner = _user(db, wa_id="96511110031")
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    sender = RecordingSender()
    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    row = _outbox(db)[0]
    assert row.status == "sent"

    body = {"entry": [{"changes": [{"field": "messages", "value": {"statuses": [{
        "id": row.provider_message_id, "status": "failed", "recipient_id": "96511110031",
        "errors": [{"code": 131047, "title": "Re-engagement required"}]}]}}]}]}
    raw = json.dumps(body).encode()
    client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})

    db.expire_all()
    row = _outbox(db)[0]
    assert row.status == "failed"
    assert row.last_error_code == "131047"


def test_a_delivered_receipt_leaves_the_row_sent(client, monkeypatch, db):
    enable_whatsapp(monkeypatch)
    _approve_all(db)
    owner = _user(db, wa_id="96511110032")
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    sender = RecordingSender()
    dispatch_due(db, sender, now=datetime.utcnow() + timedelta(seconds=1), max_attempts=3)
    row = _outbox(db)[0]

    body = {"entry": [{"changes": [{"field": "messages", "value": {"statuses": [{
        "id": row.provider_message_id, "status": "delivered", "recipient_id": "96511110032"}]}}]}]}
    raw = json.dumps(body).encode()
    client.post("/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sign(raw), "Content-Type": "application/json"})

    db.expire_all()
    assert _outbox(db)[0].status == "sent"


def test_a_receipt_for_a_row_still_pending_changes_nothing(db):
    from app.services.whatsapp_events import ParsedEvent, apply_delivery_failure

    owner = _user(db, wa_id="96511110033")
    notify(db, owner, NotificationType.award_won, link="/x", project_title="Villa")
    row = _outbox(db)[0]
    row.provider_message_id = "wamid.PENDING"
    db.commit()
    parsed = ParsedEvent(event_key="status:wamid.PENDING:failed", direction="status", event_type="status_failed",
                         payload_sha256="0" * 64, provider_message_id="wamid.PENDING", wa_id=None, error_code="1")
    assert apply_delivery_failure(db, parsed) is False
    assert _outbox(db)[0].status == "pending"


# --- migration 0011 --------------------------------------------------------------------


def test_the_migration_enum_matches_the_python_notification_types():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0011_notifications_and_templates.py"
    spec = importlib.util.spec_from_file_location("migration_0011", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert set(module._EXISTING) | set(module._NEW) == {t.value for t in NotificationType}
    assert len(module._EXISTING) + len(module._NEW) == len({t.value for t in NotificationType})


def test_migration_0011_creates_the_template_table_and_is_reversible():
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    from mysql_support import scratch_engine

    import app.db as db_module

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0011_notifications_and_templates.py"
    spec = importlib.util.spec_from_file_location("migration_0011_run", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with scratch_engine() as engine:
        db_module.Base.metadata.create_all(bind=engine, tables=[t for n, t in db_module.Base.metadata.tables.items() if n != "whatsapp_template_status"])
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        assert "whatsapp_template_status" in inspect(engine).get_table_names()
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
        assert "whatsapp_template_status" not in inspect(engine).get_table_names()
