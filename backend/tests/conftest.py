"""Shared pytest fixtures for the backend test suite.

Every test gets a fresh, fully isolated in-memory SQLite database and a
fresh local-file storage root, even though `app.main` (and every router
module it pulls in) is only ever imported once for the whole pytest
session. This works because `app.db.get_db()` and
`app.services.storage.get_storage()` both resolve their session
factory / settings from their *module's current global* at call time
(not at import time), so reassigning `app.db.engine`/`SessionLocal` and
`app.services.storage.settings.storage_root` before each test takes
effect on every request that test makes.

Required settings (JWT_SECRET, STORAGE_SIGNING_SECRET, ...) are given
safe test defaults here, before anything under `app` is imported, so
`Settings()` never has to fall back to its `mysql://`-pointing
production default for `database_url` — not that it matters, since
every test replaces the engine directly regardless of what
`DATABASE_URL` resolved to at import time.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# One scratch MySQL database per run. Fails explicitly if TEST_DATABASE_ADMIN_URL is not set.
from mysql_support import create_scratch_database, drop_scratch_database  # noqa: E402

_TEST_ENGINE = create_scratch_database()

# Explicit test values for every required setting. Nothing here is a default for production.
os.environ["DATABASE_URL"] = _TEST_ENGINE.url.render_as_string(hide_password=False)
os.environ["JWT_SECRET"] = "test-jwt-secret-" + "x" * 32
os.environ["STORAGE_SIGNING_SECRET"] = "test-storage-secret-" + "x" * 32
os.environ["CRON_SECRET"] = "test-cron-secret-" + "x" * 32
os.environ["STORAGE_ROOT"] = tempfile.mkdtemp(prefix="utender-test-storage-")
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["S3_REGION"] = "us-east-1"

import pytest  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.db as db_module  # noqa: E402
import app.models  # noqa: F401,E402  registers every ORM model on Base.metadata
import app.services.storage as storage_module  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402  imported once for the whole session


def _clear_all_tables(engine) -> None:
    """Delete every row, children first. Keeps the schema, so tests stay fast on MySQL."""
    with engine.begin() as connection:
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        try:
            for table in reversed(db_module.Base.metadata.sorted_tables):
                connection.exec_driver_sql(f"DELETE FROM `{table.name}`")
        finally:
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")


def pytest_configure(config):
    db_module.Base.metadata.create_all(bind=_TEST_ENGINE)


def pytest_sessionfinish(session, exitstatus):
    drop_scratch_database(_TEST_ENGINE)
    shutil.rmtree(os.environ["STORAGE_ROOT"], ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_backend(tmp_path):
    """Before each test: empty tables and a fresh storage root. The app's session factory points at the scratch database."""
    db_module.engine = _TEST_ENGINE
    db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_TEST_ENGINE)
    _clear_all_tables(_TEST_ENGINE)

    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    storage_module.settings.storage_root = str(storage_root)
    storage_module.settings.storage_backend = "local"
    storage_module._storage_instance = None

    yield

    _clear_all_tables(_TEST_ENGINE)


@pytest.fixture(autouse=True)
def reset_whatsapp_hooks():
    """Handler registries are process-wide, so each test starts and ends with none registered."""
    from app.routers.whatsapp import clear_flow_handlers
    from app.services.whatsapp_events import clear_inbound_handlers

    clear_inbound_handlers()
    clear_flow_handlers()
    yield
    clear_inbound_handlers()
    clear_flow_handlers()


@pytest.fixture
def client():
    """A single anonymous TestClient. Most tests create their own
    per-actor clients directly (`TestClient(app)`) since each actor
    needs its own cookie jar — this fixture covers the simple cases."""
    return TestClient(fastapi_app)


@pytest.fixture
def db():
    """A raw DB session for setup/assertions that bypass the API
    (e.g. flipping a document straight to approved, or reading an
    AuditLog row the API doesn't expose)."""
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def approve_owner(db_session, owner_id: str) -> None:
    """Test-only shortcut mirroring how Alembic migration 0005 grandfathers
    every pre-existing owner in as approved: most tests just need "an
    owner who can post a project" and don't care about the document-upload
    path itself (that path has its own dedicated coverage in
    test_owner_verification_and_admin.py) — this avoids repeating the
    upload/submit/admin-approve dance in every test file that only needs
    a working owner as a precondition for something else."""
    from app.models.enums import VerificationStatus
    from app.models.owner import OwnerProfile

    profile = db_session.get(OwnerProfile, owner_id)
    profile.verification_status = VerificationStatus.approved
    db_session.commit()
