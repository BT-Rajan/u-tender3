"""Timestamps keep microseconds on MySQL, so writes in the same second still order correctly."""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

import app.db as db_module
import app.models  # noqa: F401
from mysql_support import scratch_engine

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _datetime_precisions(engine):
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT TABLE_NAME, COLUMN_NAME, DATETIME_PRECISION FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND DATA_TYPE = 'datetime'"
            )
        ).all()
    return {(table, column): precision for table, column, precision in rows}


def test_every_timestamp_column_declared_by_the_models_keeps_microseconds(db):
    precisions = _datetime_precisions(db.get_bind())
    assert precisions, "the test schema has no datetime columns"
    assert set(precisions.values()) == {6}


def test_two_writes_in_the_same_second_keep_their_order(db):
    first = datetime(2026, 12, 1, 9, 0, 0, 100000)
    second = datetime(2026, 12, 1, 9, 0, 0, 900000)
    with db.get_bind().begin() as connection:
        connection.execute(text("INSERT INTO users (id, email, password_hash, role, language, email_verified, created_at) VALUES ('u1', 'a@example.com', 'h', 'owner', 'en', 0, :t)"), {"t": first})
        connection.execute(text("INSERT INTO users (id, email, password_hash, role, language, email_verified, created_at) VALUES ('u2', 'b@example.com', 'h', 'owner', 'en', 0, :t)"), {"t": second})
    order = [row[0] for row in db.get_bind().connect().execute(text("SELECT id FROM users ORDER BY created_at")).all()]
    assert order == ["u1", "u2"]


def test_0013_widens_every_datetime_column_and_downgrade_restores_whole_seconds():
    with scratch_engine() as engine:
        db_module.Base.metadata.create_all(bind=engine)
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)) as ops:
                # The models declare microseconds. Reset one column to whole seconds to prove the upgrade widens it.
                ops.execute("ALTER TABLE users MODIFY created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP")
        assert _datetime_precisions(engine)[("users", "created_at")] == 0

        migration = _load("0013_datetime_microseconds")
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        assert set(_datetime_precisions(engine).values()) == {6}

        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
        assert set(_datetime_precisions(engine).values()) == {0}
