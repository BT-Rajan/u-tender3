"""Migration 0012: bid amounts widen to DECIMAL(15,3) so imported KWD fils are kept. Widening loses no data."""

import importlib.util
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

import app.db as db_module
import app.models  # noqa: F401

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
TABLES = ("offers", "offer_revisions", "award_records")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, migration, direction):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(migration, direction)()


def _engine_before_0012():
    """The schema as it stood at 0011: amounts DECIMAL(12,2). create_all builds from the current model, so narrow them back."""
    engine = create_engine("sqlite:///:memory:")
    db_module.Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)) as ops:
            for table in TABLES:
                with ops.batch_alter_table(table) as batch:
                    batch.alter_column("amount", existing_type=sa.Numeric(15, 3), type_=sa.Numeric(12, 2), existing_nullable=False)
    return engine


def _amount_type(engine, table):
    column = next(c for c in inspect(engine).get_columns(table) if c["name"] == "amount")
    return column["type"]


def test_0012_widens_bid_amounts_to_three_decimals_and_keeps_existing_values():
    engine = _engine_before_0012()
    assert _amount_type(engine, "offers").scale == 2

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, password_hash, role, language, email_verified) VALUES ('o1', 'o@example.com', 'h', 'owner', 'en', 0)"
        )
        connection.exec_driver_sql(
            "INSERT INTO projects (id, owner_id, title, address, bid_deadline, status, tender_type, tender_type_locked, is_suspended, revision, deadline_reminder_sent) "
            "VALUES ('p1', 'o1', 'Villa', 'Block 3', '2026-12-31 11:00:00', 'open', 'owner_visible', 0, 0, 1, 0)"
        )
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, password_hash, role, language, email_verified) VALUES ('c1', 'c@example.com', 'h', 'contractor', 'en', 0)"
        )
        connection.exec_driver_sql(
            "INSERT INTO offers (id, project_id, contractor_id, amount, status, revision, is_suspended) "
            "VALUES ('of1', 'p1', 'c1', 1500.250, 'submitted', 1, 0)"
        )

    _run(engine, _load("0012_offer_amounts_three_decimals"), "upgrade")

    for table in TABLES:
        assert _amount_type(engine, table).scale == 3
    with engine.connect() as connection:
        amount = connection.exec_driver_sql("SELECT amount FROM offers WHERE id = 'of1'").scalar()
    assert Decimal(str(amount)) == Decimal("1500.250")


def test_0012_downgrade_narrows_back_to_two_decimals():
    engine = _engine_before_0012()
    _run(engine, _load("0012_offer_amounts_three_decimals"), "upgrade")
    assert _amount_type(engine, "offers").scale == 3

    _run(engine, _load("0012_offer_amounts_three_decimals"), "downgrade")

    for table in TABLES:
        assert _amount_type(engine, table).scale == 2
