"""Web authentication must keep working alongside WhatsApp-only accounts, and a WhatsApp-only account must never
reach password verification."""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

from mysql_support import scratch_engine
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

import app.db as db_module
import app.models  # noqa: F401
from app.auth.security import create_access_token, hash_password
from app.config import get_settings
from app.models.enums import Language, UserRole
from app.models.user import User
from app.schemas.user import UserOut
from app.services import email as email_module

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _web_owner(db, email="web@example.com", password="correct-horse"):
    user = User(email=email, password_hash=hash_password(password), role=UserRole.owner, email_verified=True)
    db.add(user)
    db.commit()
    return user


def _whatsapp_only(db, phone="+96511112222"):
    user = User(email=None, password_hash=None, role=UserRole.owner, full_name="Layla", phone=phone)
    db.add(user)
    db.commit()
    return user


def test_an_existing_web_account_still_logs_in_with_its_password(client, db):
    _web_owner(db)
    response = client.post("/auth/login", json={"email": "web@example.com", "password": "correct-horse"})
    assert response.status_code == 200
    assert response.json()["email"] == "web@example.com"


def test_a_wrong_password_for_a_web_account_is_still_refused(client, db):
    _web_owner(db)
    response = client.post("/auth/login", json={"email": "web@example.com", "password": "wrong"})
    assert response.status_code == 401


def test_an_account_with_no_password_hash_gets_the_same_generic_refusal(client, db):
    # Such an account can't be made by signup, but a row like this must never reach password verification.
    user = User(email="orphan@example.com", password_hash=None, role=UserRole.owner)
    db.add(user)
    db.commit()

    response = client.post("/auth/login", json={"email": "orphan@example.com", "password": "anything"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_change_password_is_refused_cleanly_for_a_passwordless_account(client, db):
    user = _whatsapp_only(db)
    client.cookies.set("access_token", create_access_token(user.id))

    response = client.post("/auth/change-password", json={"current_password": "x", "new_password": "a-new-password-1"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Current password is incorrect."
    db.refresh(user)
    assert user.password_hash is None


def test_user_output_accepts_an_account_with_no_email():
    user = User(
        id="u1",
        email=None,
        password_hash=None,
        role=UserRole.contractor,
        full_name="Omar",
        phone="+96511112222",
        language=Language.en,
        email_verified=False,
        created_at=datetime(2026, 11, 23),
    )
    out = UserOut.model_validate(user)
    assert out.email is None


def test_email_to_a_missing_address_is_skipped_without_a_send(monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test")
    calls = []

    class FakeResend:
        class Emails:
            @staticmethod
            def send(payload):
                calls.append(payload)

    import sys

    monkeypatch.setitem(sys.modules, "resend", FakeResend)

    email_module._send(None, "Subject", "<p>body</p>")

    assert calls == []


def test_email_to_a_real_address_still_sends(monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test")
    calls = []

    class FakeResend:
        class Emails:
            @staticmethod
            def send(payload):
                calls.append(payload)

    import sys

    monkeypatch.setitem(sys.modules, "resend", FakeResend)

    email_module._send("owner@example.com", "Subject", "<p>body</p>")

    assert calls and calls[0]["to"] == "owner@example.com"


# --- migration 0008 ---------------------------------------------------------


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, migration, direction):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(migration, direction)()


@pytest.fixture
def pre_0008_engine():
    """Schema as it stands after 0007: all current tables, then 0007's WhatsApp tables."""
    with scratch_engine() as engine:
        non_whatsapp = [t for n, t in db_module.Base.metadata.tables.items() if not n.startswith("whatsapp_")]
        db_module.Base.metadata.create_all(bind=engine, tables=non_whatsapp)
        _run(engine, _load("0007_whatsapp_foundation"), "upgrade")
        yield engine


def test_0008_makes_email_and_password_nullable(pre_0008_engine):
    _run(pre_0008_engine, _load("0008_whatsapp_registration"), "upgrade")

    columns = {column["name"]: column for column in inspect(pre_0008_engine).get_columns("users")}
    assert columns["email"]["nullable"] is True
    assert columns["password_hash"]["nullable"] is True


def test_0008_keeps_existing_web_accounts_intact(pre_0008_engine):
    with pre_0008_engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, password_hash, role, language, email_verified) "
            "VALUES ('u1', 'web@example.com', 'hash', 'owner', 'en', 0)"
        )
    _run(pre_0008_engine, _load("0008_whatsapp_registration"), "upgrade")

    with pre_0008_engine.connect() as connection:
        row = connection.exec_driver_sql("SELECT email, password_hash FROM users WHERE id = 'u1'").one()
    assert tuple(row) == ("web@example.com", "hash")


def test_0008_makes_the_identity_user_link_unique(pre_0008_engine):
    _run(pre_0008_engine, _load("0008_whatsapp_registration"), "upgrade")

    indexes = {index["name"]: index for index in inspect(pre_0008_engine).get_indexes("whatsapp_identities")}
    assert indexes["ix_whatsapp_identities_user_id"]["unique"] == 1


def test_0008_downgrade_restores_the_previous_shape(pre_0008_engine):
    migration = _load("0008_whatsapp_registration")
    _run(pre_0008_engine, migration, "upgrade")
    _run(pre_0008_engine, migration, "downgrade")

    columns = {column["name"]: column for column in inspect(pre_0008_engine).get_columns("users")}
    assert columns["email"]["nullable"] is False
    indexes = {index["name"]: index for index in inspect(pre_0008_engine).get_indexes("whatsapp_identities")}
    assert not indexes["ix_whatsapp_identities_user_id"]["unique"]
