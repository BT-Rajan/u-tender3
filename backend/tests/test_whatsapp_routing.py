from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.enums import UserRole
from app.models.owner import OwnerProfile
from app.models.user import User
from app.models.whatsapp import WhatsAppFlowSession, WhatsAppIdentity, WhatsAppOutbox
from app.services.whatsapp_events import record_events
from app.services.whatsapp_identity import get_or_create_identity
from app.services.whatsapp_routing import install_whatsapp_handlers
from whatsapp_helpers import enable_whatsapp, message_envelope, text_message

NOW = datetime.utcnow()
WA_ID = "96512345678"


def _deliver(db, *messages):
    """Run a batch of inbound messages through the real intake path, the same way the webhook does."""
    install_whatsapp_handlers()
    return record_events(db, message_envelope(*messages), now=NOW)


def _outbox(db):
    return db.scalars(select(WhatsAppOutbox).order_by(WhatsAppOutbox.next_attempt_at)).all()


def _sessions(db):
    return db.scalars(select(WhatsAppFlowSession).order_by(WhatsAppFlowSession.expires_at)).all()


def _account(db, role: UserRole, wa_id: str = WA_ID, full_name: str = "Layla Al-Sabah") -> User:
    user = User(email=None, password_hash=None, role=role, full_name=full_name, phone=f"+{wa_id}")
    db.add(user)
    db.flush()
    if role == UserRole.owner:
        db.add(OwnerProfile(user_id=user.id))
    identity = get_or_create_identity(db, wa_id, now=NOW)
    identity.user_id = user.id
    identity.role = role.value
    db.commit()
    return user


def test_a_new_number_is_sent_the_registration_flow(monkeypatch, db):
    enable_whatsapp(monkeypatch)

    _deliver(db, text_message("wamid.NEW1", WA_ID, "hi"))

    queued = _outbox(db)
    assert len(queued) == 1
    row = queued[0]
    assert row.kind == "flow"
    assert row.params_json["screen"] == "WELCOME"
    assert row.params_json["flow_id"] == "flow-registration"
    assert row.params_json["flow_token"]
    session = _sessions(db)[0]
    assert session.flow_name == "registration"
    assert session.completed_at is None


def test_the_flow_token_in_the_outbox_matches_only_the_stored_hash(monkeypatch, db):
    from app.services.whatsapp_identity import hash_flow_token

    enable_whatsapp(monkeypatch)
    _deliver(db, text_message("wamid.NEW2", WA_ID, "hi"))

    token = _outbox(db)[0].params_json["flow_token"]
    assert _sessions(db)[0].flow_token_hash == hash_flow_token(token)


def test_a_new_number_creates_one_identity_with_no_account(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    _deliver(db, text_message("wamid.NEW3", WA_ID, "hi"))

    identity = db.scalar(select(WhatsAppIdentity).where(WhatsAppIdentity.wa_id == WA_ID))
    assert identity.user_id is None
    assert db.query(User).count() == 0


def test_an_owner_gets_the_owner_dashboard(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    _account(db, UserRole.owner)

    _deliver(db, text_message("wamid.OWN1", WA_ID, "hi"))

    row = _outbox(db)[0]
    assert row.kind == "flow"
    assert row.params_json["flow_id"] == "flow-owner"
    assert row.params_json["screen"] == "MENU"
    assert _sessions(db)[0].flow_name == "owner_dashboard"


def test_a_contractor_gets_the_contractor_dashboard(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    _account(db, UserRole.contractor)

    _deliver(db, text_message("wamid.CON1", WA_ID, "hi"))

    row = _outbox(db)[0]
    assert row.params_json["flow_id"] == "flow-contractor"
    assert _sessions(db)[0].flow_name == "contractor_dashboard"


def test_an_admin_is_pointed_to_the_web_dashboard_in_text(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    _account(db, UserRole.admin)

    _deliver(db, text_message("wamid.ADM1", WA_ID, "hi"))

    row = _outbox(db)[0]
    assert row.kind == "text"
    assert "web dashboard" in row.params_json["body"]
    assert _sessions(db) == []


def test_an_unfinished_registration_resumes_on_the_same_screen_with_its_answers(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    _deliver(db, text_message("wamid.RES1", WA_ID, "hi"))
    first = _sessions(db)[0]
    first.screen = "OWNER_DETAILS"
    first.state_json = {"role": "owner", "language": "ar"}
    db.commit()

    later = get_or_create_identity(db, WA_ID, now=NOW)  # same identity, still no account
    assert later.user_id is None
    _deliver(db, text_message("wamid.RES2", WA_ID, "are you there"))

    db.refresh(first)
    newest = _sessions(db)[-1]
    assert newest.id != first.id
    assert newest.screen == "OWNER_DETAILS"
    assert newest.state_json == {"role": "owner", "language": "ar"}
    assert first.completed_at is not None
    assert first.state_json is None


def test_resuming_sends_a_fresh_token_so_the_old_one_stops_working(monkeypatch, db):
    from app.services.whatsapp_identity import hash_flow_token

    enable_whatsapp(monkeypatch)
    _deliver(db, text_message("wamid.RES3", WA_ID, "hi"))
    old_token = _outbox(db)[0].params_json["flow_token"]
    _deliver(db, text_message("wamid.RES4", WA_ID, "hi again"))

    new_token = next(row.params_json["flow_token"] for row in _outbox(db) if row.params_json.get("flow_token") != old_token)
    assert new_token != old_token
    old_session = db.scalar(select(WhatsAppFlowSession).where(WhatsAppFlowSession.flow_token_hash == hash_flow_token(old_token)))
    assert old_session.completed_at is not None


def test_an_expired_unfinished_registration_starts_again_at_the_role_screen(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    _deliver(db, text_message("wamid.EXP1", WA_ID, "hi"))
    stale = _sessions(db)[0]
    stale.screen = "CONTRACTOR_DETAILS"
    stale.state_json = {"role": "contractor", "language": "en"}
    stale.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    _deliver(db, text_message("wamid.EXP2", WA_ID, "hi"))

    assert _sessions(db)[-1].screen == "WELCOME"
    assert _sessions(db)[-1].state_json is None


def test_a_completed_flow_message_is_not_answered_by_the_router(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    nfm_reply = {
        "from": WA_ID,
        "id": "wamid.NFM1",
        "timestamp": "1700000000",
        "type": "interactive",
        "interactive": {"type": "nfm_reply", "nfm_reply": {"response_json": "{}", "name": "flow"}},
    }
    _deliver(db, nfm_reply)

    assert _outbox(db) == []


def test_without_a_configured_flow_id_the_number_gets_a_text_instead(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "whatsapp_flow_id_registration", None)
    _deliver(db, text_message("wamid.NOFLOW", WA_ID, "hi"))

    row = _outbox(db)[0]
    assert row.kind == "text"
    assert "being set up" in row.params_json["body"]


def test_a_repeated_delivery_of_the_same_message_queues_nothing_more(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    message = text_message("wamid.DUP9", WA_ID, "hi")
    _deliver(db, message)
    _deliver(db, message)

    assert len(_outbox(db)) == 1
    assert len(_sessions(db)) == 1


def _button_reply(message_id: str, wa_id: str, button_id: str) -> dict:
    return {
        "from": wa_id,
        "id": message_id,
        "timestamp": "1700000000",
        "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": button_id, "title": "x"}},
    }


def test_the_yes_button_opens_the_owner_dashboard(monkeypatch, db):
    enable_whatsapp(monkeypatch)
    _account(db, UserRole.owner)

    _deliver(db, _button_reply("wamid.YES1", WA_ID, "continue_yes"))

    row = _outbox(db)[-1]
    assert row.kind == "flow"
    assert row.params_json["flow_id"] == "flow-owner"
    assert _sessions(db)[-1].flow_name == "owner_dashboard"


def test_the_no_button_sends_a_text_and_no_dashboard(monkeypatch, db):
    from app.services.whatsapp_routing import ACCOUNT_NO_TEXT

    enable_whatsapp(monkeypatch)
    _account(db, UserRole.owner)

    _deliver(db, _button_reply("wamid.NO1", WA_ID, "continue_no"))

    rows = _outbox(db)
    assert [row.kind for row in rows] == ["text"]
    assert rows[0].params_json["body"] == ACCOUNT_NO_TEXT["en"]


def test_the_account_created_message_has_yes_and_no_buttons_and_is_sent(monkeypatch, db):
    from app.services.whatsapp_flows import ACCOUNT_CREATED, _queue_account_created
    from app.services.whatsapp_outbox import dispatch_due
    from whatsapp_helpers import RecordingSender

    enable_whatsapp(monkeypatch)
    _account(db, UserRole.owner)
    identity = get_or_create_identity(db, WA_ID, now=NOW)

    _queue_account_created(db, identity, "en", now=NOW)
    sender = RecordingSender()
    dispatch_due(db, sender, now=NOW, max_attempts=3)

    body, yes, no = ACCOUNT_CREATED["en"]
    assert sender.sent[-1]["kind"] == "buttons"
    assert sender.sent[-1]["body"] == body
    assert [button["title"] for button in sender.sent[-1]["buttons"]] == [yes, no]
    assert [button["id"] for button in sender.sent[-1]["buttons"]] == ["continue_yes", "continue_no"]


def test_the_dashboard_menu_always_sends_the_error_field_it_shows(monkeypatch, db):
    from app.services.whatsapp_flows import _menu_data

    enable_whatsapp(monkeypatch)
    user = _account(db, UserRole.owner)

    menu = _menu_data(db, user, True)
    assert menu["error_message"] == ""
    assert menu["greeting"].startswith("Hello ")
