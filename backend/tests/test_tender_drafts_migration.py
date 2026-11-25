"""Migration 0010: tender drafts may have no bid deadline. Existing data is untouched and the downgrade is safe."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

import app.db as db_module

from mysql_support import scratch_engine
import app.models  # noqa: F401

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, migration, direction):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(migration, direction)()


def _deadline_nullable(engine):
    column = next(c for c in inspect(engine).get_columns("projects") if c["name"] == "bid_deadline")
    return column["nullable"]


@pytest.fixture
def engine_before_0010():
    """The schema as it stood before 0010: projects.bid_deadline NOT NULL. create_all builds from the current model, so reset it."""
    import sqlalchemy as sa

    with scratch_engine() as engine:
        db_module.Base.metadata.create_all(bind=engine)
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)) as ops:
                with ops.batch_alter_table("projects") as batch:
                    batch.alter_column("bid_deadline", existing_type=sa.DateTime(), nullable=False)
        yield engine


def test_0010_makes_the_deadline_nullable_and_keeps_existing_rows(engine_before_0010):
    engine = engine_before_0010
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, password_hash, role, language, email_verified) VALUES ('o1', 'o@example.com', 'h', 'owner', 'en', 0)"
        )
        connection.exec_driver_sql(
            "INSERT INTO projects (id, owner_id, title, address, bid_deadline, status, tender_type, tender_type_locked, is_suspended, revision, deadline_reminder_sent) "
            "VALUES ('p1', 'o1', 'Villa', 'Block 3', '2026-12-31 11:00:00', 'open', 'owner_visible', 0, 0, 1, 0)"
        )
    assert _deadline_nullable(engine) is False

    _run(engine, _load("0010_tender_drafts"), "upgrade")

    assert _deadline_nullable(engine) is True
    with engine.connect() as connection:
        row = connection.exec_driver_sql("SELECT bid_deadline FROM projects WHERE id = 'p1'").one()
    assert str(row[0]).startswith("2026-12-31")


def test_0010_downgrade_restores_not_null_when_every_row_has_a_deadline(engine_before_0010):
    engine = engine_before_0010
    migration = _load("0010_tender_drafts")
    _run(engine, migration, "upgrade")
    _run(engine, migration, "downgrade")
    assert _deadline_nullable(engine) is False


def test_0010_chains_after_0009():
    migration = _load("0010_tender_drafts")
    assert migration.revision == "0010" and migration.down_revision == "0009"
