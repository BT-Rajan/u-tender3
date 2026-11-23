from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.models.whatsapp import WhatsAppFlowSession, WhatsAppIdentity
from app.services.whatsapp_identity import (
    complete_flow_session,
    create_flow_session,
    find_active_flow_session,
    get_or_create_identity,
    hash_flow_token,
    normalise_wa_id,
)

NOW = datetime(2026, 11, 23, 12, 0, 0)


@pytest.mark.parametrize("raw, expected", [("96512345678", "96512345678"), ("+965 1234 5678", "96512345678"), ("965-1234-5678", "96512345678")])
def test_wa_id_is_normalised_to_digits(raw, expected):
    assert normalise_wa_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "123", "1" * 16])
def test_invalid_numbers_are_refused(raw):
    with pytest.raises(ValueError):
        normalise_wa_id(raw)


def test_first_contact_creates_one_identity(db):
    identity = get_or_create_identity(db, "+96512345678", now=NOW)

    assert identity.wa_id == "96512345678"
    assert identity.phone_e164 == "+96512345678"
    assert identity.user_id is None
    assert db.query(WhatsAppIdentity).count() == 1


def test_repeat_contact_returns_the_same_identity_and_updates_last_seen(db):
    first = get_or_create_identity(db, "96512345678", now=NOW)
    later = NOW + timedelta(hours=3)
    second = get_or_create_identity(db, "96512345678", now=later)

    assert second.id == first.id
    assert db.query(WhatsAppIdentity).count() == 1
    assert second.last_seen_at == later


def test_a_database_refuses_a_second_identity_for_the_same_number(db):
    get_or_create_identity(db, "96512345678", now=NOW)
    db.add(WhatsAppIdentity(wa_id="96512345678", phone_e164="+96512345678"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_an_identity_can_be_linked_to_a_user(db):
    user = User(email="owner@example.com", password_hash="x", role="owner")
    db.add(user)
    db.commit()

    identity = get_or_create_identity(db, "96512345678", now=NOW)
    identity.user_id = user.id
    db.commit()

    assert db.scalar(select(WhatsAppIdentity).where(WhatsAppIdentity.user_id == user.id)).id == identity.id


def test_flow_token_is_returned_once_and_only_its_hash_is_stored(db):
    identity = get_or_create_identity(db, "96512345678", now=NOW)
    session, raw_token = create_flow_session(db, identity, flow_name="registration", now=NOW, screen="NAME")

    stored = db.get(WhatsAppFlowSession, session.id)
    assert stored.flow_token_hash == hash_flow_token(raw_token)
    assert stored.flow_token_hash != raw_token
    assert raw_token not in " ".join(str(getattr(stored, c.name)) for c in WhatsAppFlowSession.__table__.columns)


def test_a_live_session_is_found_by_its_token(db):
    identity = get_or_create_identity(db, "96512345678", now=NOW)
    session, raw_token = create_flow_session(db, identity, flow_name="registration", now=NOW)

    found = find_active_flow_session(db, raw_token, now=NOW + timedelta(minutes=1))
    assert found is not None
    assert found.id == session.id


def test_an_expired_session_is_not_found(db):
    identity = get_or_create_identity(db, "96512345678", now=NOW)
    _, raw_token = create_flow_session(db, identity, flow_name="registration", now=NOW, ttl=timedelta(hours=1))

    assert find_active_flow_session(db, raw_token, now=NOW + timedelta(hours=2)) is None


def test_a_completed_session_is_not_found_and_its_state_is_cleared(db):
    identity = get_or_create_identity(db, "96512345678", now=NOW)
    session, raw_token = create_flow_session(
        db, identity, flow_name="registration", now=NOW, screen="CONFIRM", state={"full_name": "Layla"}
    )

    complete_flow_session(db, session, now=NOW + timedelta(minutes=5))

    assert find_active_flow_session(db, raw_token, now=NOW + timedelta(minutes=6)) is None
    stored = db.get(WhatsAppFlowSession, session.id)
    assert stored.state_json is None
    assert stored.completed_at is not None


def test_an_unknown_or_empty_token_finds_nothing(db):
    assert find_active_flow_session(db, "", now=NOW) is None
    assert find_active_flow_session(db, "never-issued", now=NOW) is None


