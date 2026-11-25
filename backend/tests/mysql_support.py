"""MySQL/MariaDB databases for the test suite. There is no SQLite path.

TEST_DATABASE_ADMIN_URL must be set to a mysql+pymysql URL whose user can create and
drop databases. Each run uses its own scratch database, and it is dropped afterwards.
If the variable is missing or the server is unreachable, the tests fail with that
message. They never fall back to another database.
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

ADMIN_ENV = "TEST_DATABASE_ADMIN_URL"


class TestDatabaseUnavailable(RuntimeError):
    pass


def admin_url() -> str:
    url = os.environ.get(ADMIN_ENV, "").strip()
    if not url:
        raise TestDatabaseUnavailable(
            f"{ADMIN_ENV} is not set. The tests run only against MySQL/MariaDB. "
            "Set it to a mysql+pymysql:// URL whose user can create databases."
        )
    if not url.startswith("mysql+pymysql://"):
        raise TestDatabaseUnavailable(f"{ADMIN_ENV} must be a mysql+pymysql:// URL.")
    return url


def _admin_engine() -> Engine:
    return create_engine(admin_url(), isolation_level="AUTOCOMMIT", pool_pre_ping=True)


def create_scratch_database() -> Engine:
    """A new, empty database with a random name. The caller drops it with drop_scratch_database."""
    name = f"utender_test_{uuid.uuid4().hex[:16]}"
    admin = _admin_engine()
    try:
        with admin.connect() as conn:
            conn.execute(text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    finally:
        admin.dispose()
    return create_engine(make_url(admin_url()).set(database=name), pool_pre_ping=True, isolation_level="READ COMMITTED")


def drop_scratch_database(engine: Engine) -> None:
    name = engine.url.database
    engine.dispose()
    if not name or not name.startswith("utender_test_"):
        raise RuntimeError(f"Refusing to drop {name!r}: not a scratch test database.")
    admin = _admin_engine()
    try:
        with admin.connect() as conn:
            # Idle connections left by a finished test can hold metadata locks and stall the drop.
            # The scratch database is ours alone, so close its connections first.
            stale = conn.execute(
                text("SELECT id FROM information_schema.processlist WHERE db = :name AND id <> CONNECTION_ID()"),
                {"name": name},
            ).scalars().all()
            for connection_id in stale:
                conn.execute(text(f"KILL {int(connection_id)}"))
            conn.execute(text(f"DROP DATABASE IF EXISTS `{name}`"))
    finally:
        admin.dispose()


@contextmanager
def scratch_engine() -> Iterator[Engine]:
    engine = create_scratch_database()
    try:
        yield engine
    finally:
        drop_scratch_database(engine)
