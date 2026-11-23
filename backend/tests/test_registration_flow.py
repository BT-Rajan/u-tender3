from datetime import datetime, timedelta

import pytest

from app.services.whatsapp_routing import install_whatsapp_handlers
from sqlalchemy import select

from app.models.contractor import ContractorProfile
from app.models.document import ContractorDocument, DocumentRequirement, OwnerDocument
from app.models.enums import UserRole
from app.models.owner import OwnerProfile
from app.models.user import User
from app.models.whatsapp import WhatsAppFlowSession, WhatsAppIdentity
from app.services import registration as registration_module
from app.services.registration import RegistrationError, register_owner
from app.services.whatsapp_identity import create_flow_session, get_or_create_identity
from whatsapp_helpers import enable_whatsapp, flow_request


@pytest.fixture(autouse=True)
def _install_handlers():
    """These tests drive the real Flow endpoint and webhook, so the production handlers must be registered."""
    install_whatsapp_handlers()
    yield

WA_ID = "96512345678"


@pytest.fixture
def requirements(db):
    db.add_all(
        [
            DocumentRequirement(name="Civil ID", applies_to=UserRole.owner, is_active=True),
            DocumentRequirement(name="Trade licence", applies_to=UserRole.contractor, is_active=True),
        ]
    )
    db.commit()


def _new_session(db, wa_id: str = WA_ID, screen: str = "ROLE", state=None):
    identity = get_or_create_identity(db, wa_id, now=datetime.utcnow())
    session, token = create_flow_session(
        db, identity, flow_name="registration", now=datetime.utcnow(), screen=screen, state=state
    )
    return identity, session, token


def _user_for(db, wa_id: str = WA_ID) -> User | None:
    return db.scalar(select(User).where(User.phone == f"+{wa_id}"))


def test_owner_registration_creates_a_passwordless_emailless_owner(monkeypatch, client, db, requirements):
    _, public_pem = enable_whatsapp(monkeypatch)
    identity, _, token = _new_session(db)

    reply, _ = flow_request(client, public_pem, token=token, action="INIT")
    assert reply == {"screen": "ROLE", "data": {}}

    reply, _ = flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "owner", "language": "ar"})
    assert reply == {"screen": "OWNER_DETAILS", "data": {}}

    reply, _ = flow_request(client, public_pem, token=token, action="data_exchange", screen="OWNER_DETAILS", data={"full_name": "Layla Al-Sabah"})
    assert reply["screen"] == "SUCCESS"

    user = _user_for(db)
    assert user is not None
    assert user.role == UserRole.owner
    assert user.full_name == "Layla Al-Sabah"
    assert user.language.value == "ar"
    assert user.email is None
    assert user.password_hash is None
    assert user.email_verified is False
    assert db.get(OwnerProfile, user.id) is not None
    assert db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == user.id)) is not None


def test_owner_registration_links_the_identity_and_completes_the_session(monkeypatch, client, db, requirements):
    _, public_pem = enable_whatsapp(monkeypatch)
    identity, session, token = _new_session(db)

    flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "owner", "language": "en"})
    flow_request(client, public_pem, token=token, action="data_exchange", screen="OWNER_DETAILS", data={"full_name": "Omar Haddad"})

    db.refresh(identity)
    db.refresh(session)
    user = _user_for(db)
    assert identity.user_id == user.id
    assert identity.role == "owner"
    assert session.completed_at is not None
    assert session.state_json is None


def test_contractor_registration_stores_company_trade_and_contact(monkeypatch, client, db, requirements):
    _, public_pem = enable_whatsapp(monkeypatch)
    _, _, token = _new_session(db)

    flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "contractor", "language": "en"})
    reply, _ = flow_request(
        client,
        public_pem,
        token=token,
        action="data_exchange",
        screen="CONTRACTOR_DETAILS",
        data={"contact_name": "Omar Haddad", "company_name": "Haddad Builders", "primary_trade": "Electrical"},
    )

    assert reply["screen"] == "SUCCESS"
    user = _user_for(db)
    assert user.role == UserRole.contractor
    assert user.full_name == "Omar Haddad"
    assert user.email is None and user.password_hash is None
    profile = db.get(ContractorProfile, user.id)
    assert profile.company_name == "Haddad Builders"
    assert profile.primary_trade == "Electrical"
    assert db.scalar(select(ContractorDocument).where(ContractorDocument.contractor_id == user.id)) is not None


def test_an_invalid_name_keeps_the_user_on_the_same_screen_and_creates_nothing(monkeypatch, client, db, requirements):
    _, public_pem = enable_whatsapp(monkeypatch)
    _, _, token = _new_session(db)
    flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "owner", "language": "en"})

    reply, _ = flow_request(client, public_pem, token=token, action="data_exchange", screen="OWNER_DETAILS", data={"full_name": "A"})

    assert reply["screen"] == "OWNER_DETAILS"
    assert "error_message" in reply["data"]
    assert _user_for(db) is None


def test_an_unlisted_trade_is_refused(monkeypatch, client, db, requirements):
    _, public_pem = enable_whatsapp(monkeypatch)
    _, _, token = _new_session(db)
    flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "contractor", "language": "en"})

    reply, _ = flow_request(
        client,
        public_pem,
        token=token,
        action="data_exchange",
        screen="CONTRACTOR_DETAILS",
        data={"contact_name": "Omar", "company_name": "Haddad Builders", "primary_trade": "Astrology"},
    )

    assert reply["screen"] == "CONTRACTOR_DETAILS"
    assert "trade" in reply["data"]["error_message"].lower()
    assert _user_for(db) is None


def test_an_invalid_role_or_language_is_refused_on_the_first_screen(monkeypatch, client, db, requirements):
    _, public_pem = enable_whatsapp(monkeypatch)
    _, _, token = _new_session(db)

    reply, _ = flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "admin", "language": "en"})
    assert reply["screen"] == "ROLE"
    assert "error_message" in reply["data"]

    reply, _ = flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "owner", "language": "fr"})
    assert reply["screen"] == "ROLE"


def test_resume_returns_the_saved_screen_and_answers(monkeypatch, client, db, requirements):
    _, public_pem = enable_whatsapp(monkeypatch)
    _, _, token = _new_session(db)
    flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "owner", "language": "ar"})

    reply, _ = flow_request(client, public_pem, token=token, action="INIT")

    assert reply == {"screen": "OWNER_DETAILS", "data": {}}


def test_a_completed_session_token_no_longer_works(monkeypatch, client, db, requirements):
    _, public_pem = enable_whatsapp(monkeypatch)
    _, _, token = _new_session(db)
    flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "owner", "language": "en"})
    flow_request(client, public_pem, token=token, action="data_exchange", screen="OWNER_DETAILS", data={"full_name": "Omar Haddad"})

    reply, _ = flow_request(client, public_pem, token=token, action="INIT")

    assert reply == {"screen": "EXPIRED", "data": {}}


def test_an_unknown_token_gets_the_expired_screen(monkeypatch, client):
    _, public_pem = enable_whatsapp(monkeypatch)
    reply, _ = flow_request(client, public_pem, token="never-issued", action="INIT")
    assert reply == {"screen": "EXPIRED", "data": {}}


def test_an_expired_session_gets_the_expired_screen(monkeypatch, client, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    identity = get_or_create_identity(db, WA_ID, now=datetime.utcnow())
    _, token = create_flow_session(
        db, identity, flow_name="registration", now=datetime(2020, 1, 1), ttl=timedelta(hours=1)
    )

    reply, _ = flow_request(client, public_pem, token=token, action="INIT")

    assert reply == {"screen": "EXPIRED", "data": {}}


def test_back_returns_to_the_role_screen(monkeypatch, client, db):
    _, public_pem = enable_whatsapp(monkeypatch)
    _, _, token = _new_session(db)
    reply, _ = flow_request(client, public_pem, token=token, action="BACK", screen="OWNER_DETAILS")
    assert reply == {"screen": "ROLE", "data": {}}


def test_a_number_already_on_a_web_account_is_refused_without_linking(monkeypatch, client, db, requirements):
    _, public_pem = enable_whatsapp(monkeypatch)
    web_user = User(email="web@example.com", password_hash="hash", role=UserRole.owner, phone="+965 1234 5678")
    db.add(web_user)
    db.commit()
    identity, _, token = _new_session(db)

    flow_request(client, public_pem, token=token, action="data_exchange", screen="ROLE", data={"role": "owner", "language": "en"})
    reply, _ = flow_request(client, public_pem, token=token, action="data_exchange", screen="OWNER_DETAILS", data={"full_name": "Omar Haddad"})

    assert reply["screen"] == "NOT_COMPLETED"
    db.refresh(identity)
    assert identity.user_id is None
    assert db.query(User).count() == 1


def test_a_second_registration_from_the_same_number_is_refused(db, requirements):
    identity, session, _ = _new_session(db, screen="OWNER_DETAILS", state={"role": "owner", "language": "en"})
    register_owner(db, identity, session, full_name="Omar Haddad", language="en", now=datetime.utcnow())

    second_identity = get_or_create_identity(db, WA_ID, now=datetime.utcnow())
    second_session, _ = create_flow_session(db, second_identity, flow_name="registration", now=datetime.utcnow(), screen="OWNER_DETAILS", state={"role": "owner", "language": "en"})
    with pytest.raises(RegistrationError) as excinfo:
        register_owner(db, second_identity, second_session, full_name="Someone Else", language="en", now=datetime.utcnow())

    assert excinfo.value.code == "already_registered"
    assert db.query(User).filter(User.phone == f"+{WA_ID}").count() == 1


def test_a_failure_part_way_through_rolls_back_the_whole_account(db, requirements, monkeypatch):
    identity, session, _ = _new_session(db, screen="OWNER_DETAILS", state={"role": "owner", "language": "en"})

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure after the user row was written")

    monkeypatch.setattr(registration_module, "ensure_owner_document_rows", boom)

    with pytest.raises(RuntimeError):
        register_owner(db, identity, session, full_name="Omar Haddad", language="en", now=datetime.utcnow())

    assert _user_for(db) is None
    assert db.query(OwnerProfile).count() == 0
    db.refresh(identity)
    assert identity.user_id is None
    db.refresh(session)
    assert session.completed_at is None


def test_validation_rejects_blank_and_overlong_names(db, requirements):
    identity, session, _ = _new_session(db, screen="OWNER_DETAILS", state={"role": "owner", "language": "en"})
    for bad in ("", " ", "x", "y" * 121):
        with pytest.raises(RegistrationError) as excinfo:
            register_owner(db, identity, session, full_name=bad, language="en", now=datetime.utcnow())
        assert excinfo.value.code == "invalid"
    assert _user_for(db) is None


def test_names_are_whitespace_normalised(db, requirements):
    identity, session, _ = _new_session(db, screen="OWNER_DETAILS", state={"role": "owner", "language": "en"})
    user = register_owner(db, identity, session, full_name="  Omar    Haddad ", language="en", now=datetime.utcnow())
    assert user.full_name == "Omar Haddad"


def test_the_flow_session_belongs_to_the_identity_it_was_created_for(db):
    identity, session, _ = _new_session(db)
    assert db.get(WhatsAppIdentity, identity.id).id == session.identity_id
    assert db.scalar(select(WhatsAppFlowSession).where(WhatsAppFlowSession.identity_id == identity.id)) is not None
