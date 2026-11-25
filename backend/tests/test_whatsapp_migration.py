"""Checks that migration 0007 creates exactly the tables and columns the models declare.

The full alembic chain uses MySQL-only DDL in earlier revisions (ENUM widening),
so it can't run on SQLite. Instead this test builds the base schema from the
models and then runs only 0007's upgrade and downgrade against it.
"""

import importlib.util
from pathlib import Path

import pytest

from mysql_support import scratch_engine
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

import app.db as db_module
import app.models  # noqa: F401  registers every model on Base.metadata

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0007_whatsapp_foundation.py"
WHATSAPP_TABLES = ("whatsapp_identities", "whatsapp_message_events", "whatsapp_flow_sessions", "whatsapp_outbox")


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0007", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema_of(engine, tables):
    inspector = inspect(engine)
    return {
        table: (
            sorted(column["name"] for column in inspector.get_columns(table)),
            sorted(index["name"] for index in inspector.get_indexes(table)),
        )
        for table in tables
    }


@pytest.fixture
def base_engine():
    """SQLite schema with only the non-WhatsApp tables, so 0007 starts from the same place production would."""
    with scratch_engine() as engine:
        other_tables = [table for name, table in db_module.Base.metadata.tables.items() if not name.startswith("whatsapp_")]
        db_module.Base.metadata.create_all(bind=engine, tables=other_tables)
        yield engine


def _run(engine, migration, direction: str) -> None:
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            getattr(migration, direction)()


def test_upgrade_creates_the_four_tables_with_the_columns_the_models_declare(base_engine):
    migration = _load_migration()
    _run(base_engine, migration, "upgrade")

    inspector = inspect(base_engine)
    assert set(WHATSAPP_TABLES).issubset(set(inspector.get_table_names()))

    for table in WHATSAPP_TABLES:
        migrated_columns = {column["name"] for column in inspector.get_columns(table)}
        declared_columns = {column.name for column in db_module.Base.metadata.tables[table].columns}
        assert migrated_columns == declared_columns, f"{table} drifted from its model"


def test_upgrade_creates_the_indexes_the_models_declare(base_engine):
    migration = _load_migration()
    _run(base_engine, migration, "upgrade")

    inspector = inspect(base_engine)
    for table in WHATSAPP_TABLES:
        declared = {
            index.name
            for index in db_module.Base.metadata.tables[table].indexes
            if index.name
        }
        migrated = {index["name"] for index in inspector.get_indexes(table)}
        assert declared.issubset(migrated), f"{table} is missing indexes {declared - migrated}"


def test_unique_keys_that_make_idempotency_work_exist_after_upgrade(base_engine):
    migration = _load_migration()
    _run(base_engine, migration, "upgrade")

    inspector = inspect(base_engine)
    unique_columns = {}
    for table in WHATSAPP_TABLES:
        for constraint in inspector.get_unique_constraints(table):
            unique_columns.setdefault(table, []).append(tuple(constraint["column_names"]))
        for index in inspector.get_indexes(table):
            if index.get("unique"):
                unique_columns.setdefault(table, []).append(tuple(index["column_names"]))

    assert ("event_key",) in unique_columns["whatsapp_message_events"]
    assert ("dedupe_key",) in unique_columns["whatsapp_outbox"]
    assert ("flow_token_hash",) in unique_columns["whatsapp_flow_sessions"]
    assert ("phone_e164",) in unique_columns["whatsapp_identities"]
    assert ("wa_id",) in unique_columns["whatsapp_identities"]


def test_downgrade_removes_exactly_the_whatsapp_tables_and_nothing_else(base_engine):
    migration = _load_migration()
    before = set(inspect(base_engine).get_table_names())

    _run(base_engine, migration, "upgrade")
    _run(base_engine, migration, "downgrade")

    after = set(inspect(base_engine).get_table_names())
    assert after == before
    assert not any(table.startswith("whatsapp_") for table in after)


def test_the_migration_chains_after_0006():
    migration = _load_migration()
    assert migration.revision == "0007"
    assert migration.down_revision == "0006"
