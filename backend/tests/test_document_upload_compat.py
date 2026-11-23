"""Phase 3 compatibility: migration 0009, and the existing web upload endpoints under the new validation rules."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select

import app.db as db_module
import app.models  # noqa: F401
from app.auth.security import create_access_token
from app.models.document import ContractorDocument, DocumentRequirement, OwnerDocument
from app.models.enums import DocumentStatus, UserRole
from app.models.owner import OwnerProfile
from app.models.user import User

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
PDF = b"%PDF-1.4\n%%EOF\n"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, migration, direction):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(migration, direction)()


@pytest.fixture
def pre_0009_engine():
    engine = create_engine("sqlite:///:memory:")
    base = [t for n, t in db_module.Base.metadata.tables.items() if n not in ("document_upload_links", "document_versions")]
    db_module.Base.metadata.create_all(bind=engine, tables=base)
    yield engine
    engine.dispose()


def test_0009_creates_the_two_tables_with_the_declared_columns(pre_0009_engine):
    _run(pre_0009_engine, _load("0009_document_uploads"), "upgrade")
    inspector = inspect(pre_0009_engine)
    for table in ("document_upload_links", "document_versions"):
        migrated = {c["name"] for c in inspector.get_columns(table)}
        declared = {c.name for c in db_module.Base.metadata.tables[table].columns}
        assert migrated == declared, f"{table} drifted from its model"


def test_0009_leaves_the_existing_document_tables_untouched(pre_0009_engine):
    before = {c["name"] for c in inspect(pre_0009_engine).get_columns("owner_documents")}
    _run(pre_0009_engine, _load("0009_document_uploads"), "upgrade")
    after = {c["name"] for c in inspect(pre_0009_engine).get_columns("owner_documents")}
    assert before == after


def test_0009_downgrade_removes_only_its_own_tables(pre_0009_engine):
    migration = _load("0009_document_uploads")
    before = set(inspect(pre_0009_engine).get_table_names())
    _run(pre_0009_engine, migration, "upgrade")
    _run(pre_0009_engine, migration, "downgrade")
    assert set(inspect(pre_0009_engine).get_table_names()) == before


def test_0009_chains_after_0008():
    migration = _load("0009_document_uploads")
    assert migration.revision == "0009" and migration.down_revision == "0008"


# --- existing web upload, now under the shared rules ---------------------------


def _owner_with_requirement(db):
    user = User(email="web-owner@example.com", password_hash="hash", role=UserRole.owner, email_verified=True)
    db.add(user)
    db.flush()
    db.add(OwnerProfile(user_id=user.id))
    requirement = DocumentRequirement(name="Civil ID", applies_to=UserRole.owner, is_active=True)
    db.add(requirement)
    db.flush()
    db.add(OwnerDocument(owner_id=user.id, requirement_id=requirement.id))
    db.commit()
    return user, requirement


def test_a_web_upload_of_a_real_pdf_still_succeeds_and_is_pending(client, db):
    user, requirement = _owner_with_requirement(db)
    client.cookies.set("access_token", create_access_token(user.id))

    response = client.post(
        f"/owner/documents/{requirement.id}/upload",
        files={"file": ("id.pdf", PDF, "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_a_web_upload_with_a_disguised_file_is_refused_with_a_400(client, db):
    user, requirement = _owner_with_requirement(db)
    client.cookies.set("access_token", create_access_token(user.id))

    response = client.post(
        f"/owner/documents/{requirement.id}/upload",
        files={"file": ("id.pdf", b"MZ\x90\x00 an executable named like a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert "not a PDF" in response.json()["detail"]
    doc = db.scalar(select(OwnerDocument).where(OwnerDocument.owner_id == user.id))
    assert doc.status == DocumentStatus.not_submitted
    assert doc.file_path is None


def test_a_web_contractor_upload_is_refused_for_a_wrong_extension(client, db):
    user = User(email="web-con@example.com", password_hash="hash", role=UserRole.contractor, email_verified=True)
    db.add(user)
    db.flush()
    from app.models.contractor import ContractorProfile

    db.add(ContractorProfile(user_id=user.id, company_name="Web Builders"))
    requirement = DocumentRequirement(name="Trade licence", applies_to=UserRole.contractor, is_active=True)
    db.add(requirement)
    db.flush()
    db.add(ContractorDocument(contractor_id=user.id, requirement_id=requirement.id))
    db.commit()
    client.cookies.set("access_token", create_access_token(user.id))

    response = client.post(
        f"/contractor/documents/{requirement.id}/upload",
        files={"file": ("licence.exe", PDF, "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Upload a PDF, PNG or JPEG" in response.json()["detail"]
