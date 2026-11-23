"""Import of a utender2 database into a fresh u-tender3 database.

The source is a small SQLite database that has utender2's table and column names.
The target is built from u-tender3's own models at revision 0012.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, Numeric, String, Table, create_engine, insert, select, text, inspect
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  registers every target model on Base.metadata
from app.db import Base
from app.services.utender2_import import ImportRefused, import_utender2

NOW = datetime(2026, 11, 23, 9, 0)


def _source():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    meta = MetaData()
    Table(
        "users", meta,
        Column("id", String(36), primary_key=True), Column("email", String(255)), Column("password_hash", String(255)),
        Column("role", String(40)), Column("full_name", String(255)), Column("phone", String(50)), Column("language", String(4)),
        Column("email_verified", Boolean), Column("created_at", DateTime), Column("deactivated_at", DateTime, nullable=True),
        Column("session_version", Integer),
    )
    Table(
        "service_provider_profiles", meta,
        Column("user_id", String(36), primary_key=True), Column("company_name", String(255)),
        Column("organization_id", String(36), nullable=True), Column("verification_status", String(30)),
        Column("is_suspended", Boolean), Column("avg_rating", Numeric(2, 1)), Column("review_count", Integer),
        Column("subscription_status", String(30), nullable=True), Column("payment_override_active", Boolean),
        Column("created_at", DateTime),
    )
    Table(
        "owner_profiles", meta,
        Column("user_id", String(36), primary_key=True), Column("verification_status", String(30)),
        Column("is_suspended", Boolean), Column("organization_id", String(36), nullable=True), Column("created_at", DateTime),
    )
    Table(
        "document_requirements", meta,
        Column("id", String(36), primary_key=True), Column("name", String(255)), Column("description", String(500), nullable=True),
        Column("is_required", Boolean), Column("is_active", Boolean), Column("applies_to", String(40)),
        Column("applies_to_stakeholder", String(40), nullable=True), Column("requires_expiry", Boolean),
        Column("effective_from", DateTime), Column("created_at", DateTime),
    )
    Table(
        "service_provider_documents", meta,
        Column("id", String(36), primary_key=True), Column("service_provider_id", String(36)), Column("requirement_id", String(36)),
        Column("file_path", String(500), nullable=True), Column("status", String(30)), Column("submitted_at", DateTime, nullable=True),
    )
    Table(
        "projects", meta,
        Column("id", String(36), primary_key=True), Column("owner_id", String(36)), Column("organization_id", String(36), nullable=True),
        Column("title", String(255)), Column("address", String(500)), Column("bid_deadline", DateTime), Column("status", String(30)),
        Column("tender_type", String(30)), Column("tender_type_locked", Boolean), Column("is_suspended", Boolean),
        Column("revision", Integer), Column("created_at", DateTime),
    )
    Table(
        "offers", meta,
        Column("id", String(36), primary_key=True), Column("project_id", String(36)), Column("service_provider_id", String(36)),
        Column("organization_id", String(36), nullable=True), Column("amount", Numeric(15, 3), nullable=True),
        Column("status", String(30)), Column("revision", Integer), Column("is_suspended", Boolean), Column("created_at", DateTime),
    )
    Table(
        "offer_revisions", meta,
        Column("id", String(36), primary_key=True), Column("offer_id", String(36)), Column("revision_number", Integer),
        Column("amount", Numeric(15, 3)), Column("status", String(30)), Column("recorded_at", DateTime),
    )
    Table("organizations", meta, Column("id", String(36), primary_key=True), Column("name", String(255)))
    Table("auth_tokens", meta, Column("id", String(36), primary_key=True), Column("user_id", String(36)), Column("token_hash", String(64)))
    meta.create_all(engine)
    return engine, meta


def _target(revision: str = "0012"):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:version)"), {"version": revision})
    return engine


def _insert(engine, meta, table: str, *rows: dict) -> None:
    with engine.begin() as conn:
        conn.execute(insert(meta.tables[table]), list(rows))


def _user(user_id: str, role: str, **extra) -> dict:
    return {
        "id": user_id, "email": f"{user_id}@example.com", "password_hash": f"hash-{user_id}", "role": role,
        "full_name": "Name", "phone": None, "language": "en", "email_verified": True, "created_at": NOW,
        "deactivated_at": None, "session_version": 0, **extra,
    }


def _run(source, target, storage_from: Path, storage_to: Path, *, dry_run: bool = False):
    return import_utender2(source, target, storage_from=storage_from, storage_to=storage_to, dry_run=dry_run)


def _scalar_rows(engine, sql: str, **params):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params).mappings()]


@pytest.fixture
def storage(tmp_path):
    source_root = tmp_path / "utender2-storage"
    target_root = tmp_path / "u-tender3-storage"
    source_root.mkdir()
    target_root.mkdir()
    return source_root, target_root


def test_users_keep_their_password_and_service_providers_become_contractors(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-owner", "owner"), _user("u-sp", "service_provider"), _user("u-admin", "admin"))

    _run(source, target, *storage)

    rows = {row["id"]: row for row in _scalar_rows(target, "SELECT id, role, password_hash FROM users")}
    assert rows["u-sp"]["role"] == "contractor"
    assert rows["u-owner"]["role"] == "owner"
    assert rows["u-admin"]["role"] == "admin"
    assert rows["u-sp"]["password_hash"] == "hash-u-sp"


def test_service_provider_profile_becomes_a_contractor_profile_without_organisation_columns(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-sp", "service_provider"))
    _insert(
        source, meta, "service_provider_profiles",
        {
            "user_id": "u-sp", "company_name": "Gulf Builders", "organization_id": "org-1",
            "verification_status": "approved", "is_suspended": False, "avg_rating": Decimal("4.5"),
            "review_count": 3, "subscription_status": "active", "payment_override_active": False, "created_at": NOW,
        },
    )

    report = _run(source, target, *storage)

    profile = _scalar_rows(target, "SELECT user_id, company_name, verification_status FROM contractor_profiles")
    assert profile == [{"user_id": "u-sp", "company_name": "Gulf Builders", "verification_status": "approved"}]
    assert "organization_id" in report.dropped_columns["service_provider_profiles"]


def test_draft_offers_are_not_imported_and_closed_offers_become_rejected(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-owner", "owner"), _user("u-sp", "service_provider"))
    _insert(source, meta, "projects", {
        "id": "p1", "owner_id": "u-owner", "organization_id": None, "title": "Tower", "address": "Block 1",
        "bid_deadline": NOW, "status": "open", "tender_type": "sealed", "tender_type_locked": False,
        "is_suspended": False, "revision": 1, "created_at": NOW,
    })
    _insert(
        source, meta, "offers",
        {"id": "o-draft", "project_id": "p1", "service_provider_id": "u-sp", "organization_id": None, "amount": None, "status": "draft", "revision": 1, "is_suspended": False, "created_at": NOW},
        {"id": "o-closed", "project_id": "p1", "service_provider_id": "u-sp", "organization_id": None, "amount": Decimal("100.000"), "status": "closed", "revision": 1, "is_suspended": False, "created_at": NOW},
    )
    _insert(source, meta, "offer_revisions",
        {"id": "r-draft", "offer_id": "o-draft", "revision_number": 1, "amount": Decimal("1.000"), "status": "draft", "recorded_at": NOW},
        {"id": "r-closed", "offer_id": "o-closed", "revision_number": 1, "amount": Decimal("100.000"), "status": "closed", "recorded_at": NOW},
    )

    report = _run(source, target, *storage)

    offers = _scalar_rows(target, "SELECT id, contractor_id, status FROM offers")
    assert offers == [{"id": "o-closed", "contractor_id": "u-sp", "status": "rejected"}]
    assert _scalar_rows(target, "SELECT id FROM offer_revisions") == [{"id": "r-closed"}]
    assert report.skipped["offers"] == 1


def test_bid_amounts_keep_three_decimal_places(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-owner", "owner"), _user("u-sp", "service_provider"))
    _insert(source, meta, "projects", {
        "id": "p1", "owner_id": "u-owner", "organization_id": None, "title": "T", "address": "A", "bid_deadline": NOW,
        "status": "open", "tender_type": "owner_visible", "tender_type_locked": True, "is_suspended": False, "revision": 1, "created_at": NOW,
    })
    _insert(source, meta, "offers", {
        "id": "o1", "project_id": "p1", "service_provider_id": "u-sp", "organization_id": None, "amount": Decimal("12345.678"),
        "status": "submitted", "revision": 1, "is_suspended": False, "created_at": NOW,
    })

    _run(source, target, *storage)

    assert _scalar_rows(target, "SELECT amount FROM offers")[0]["amount"] in (Decimal("12345.678"), 12345.678, "12345.678")


def test_deactivated_accounts_are_imported_without_a_password(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-gone", "owner", deactivated_at=NOW))

    report = _run(source, target, *storage)

    row = _scalar_rows(target, "SELECT password_hash FROM users WHERE id = 'u-gone'")[0]
    assert row["password_hash"] is None
    assert report.deactivated_user_ids == ["u-gone"]


def test_requirements_map_onto_the_seeded_rows_by_name_and_role(storage):
    source, meta = _source()
    target = _target()
    with target.begin() as conn:
        conn.execute(text(
            "INSERT INTO document_requirements (id, name, is_required, is_active, applies_to, effective_from, created_at) "
            "VALUES ('seeded-trade', 'Trade Licence', 1, 1, 'contractor', :now, :now)"
        ), {"now": NOW})
    _insert(source, meta, "users", _user("u-sp", "service_provider"))
    _insert(source, meta, "document_requirements", {
        "id": "src-trade", "name": "Trade Licence", "description": None, "is_required": True, "is_active": True,
        "applies_to": "service_provider", "applies_to_stakeholder": None, "requires_expiry": False, "effective_from": NOW, "created_at": NOW,
    })
    _insert(source, meta, "service_provider_documents", {
        "id": "d1", "service_provider_id": "u-sp", "requirement_id": "src-trade", "file_path": "u-sp/licence.pdf", "status": "approved", "submitted_at": NOW,
    })
    (storage[0] / "u-sp").mkdir()
    (storage[0] / "u-sp" / "licence.pdf").write_bytes(b"%PDF-1.4 test")

    report = _run(source, target, *storage)

    assert _scalar_rows(target, "SELECT id FROM document_requirements WHERE name = 'Trade Licence'") == [{"id": "seeded-trade"}]
    document = _scalar_rows(target, "SELECT contractor_id, requirement_id, file_path FROM contractor_documents")[0]
    assert document == {"contractor_id": "u-sp", "requirement_id": "seeded-trade", "file_path": "u-sp/licence.pdf"}
    assert (storage[1] / "u-sp" / "licence.pdf").read_bytes() == b"%PDF-1.4 test"
    assert report.files_copied == 1
    assert report.files_missing == []


def test_missing_and_unsafe_file_paths_are_reported_not_read(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-sp", "service_provider"))
    _insert(source, meta, "document_requirements", {
        "id": "r1", "name": "Certificate", "description": None, "is_required": True, "is_active": True, "applies_to": "service_provider",
        "applies_to_stakeholder": None, "requires_expiry": False, "effective_from": NOW, "created_at": NOW,
    })
    _insert(source, meta, "service_provider_documents",
        {"id": "d1", "service_provider_id": "u-sp", "requirement_id": "r1", "file_path": "u-sp/gone.pdf", "status": "pending", "submitted_at": NOW},
        {"id": "d2", "service_provider_id": "u-sp", "requirement_id": "r2", "file_path": "../../etc/passwd", "status": "pending", "submitted_at": NOW},
    )
    _insert(source, meta, "document_requirements", {
        "id": "r2", "name": "Insurance", "description": None, "is_required": True, "is_active": True, "applies_to": "service_provider",
        "applies_to_stakeholder": None, "requires_expiry": False, "effective_from": NOW, "created_at": NOW,
    })

    report = _run(source, target, *storage)

    assert sorted(report.files_missing) == ["../../etc/passwd", "u-sp/gone.pdf"]
    assert report.files_copied == 0


def test_tables_with_no_place_in_u_tender3_are_archived_verbatim(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "organizations", {"id": "org-1", "name": "Karkathar Welfare Trust"})

    report = _run(source, target, *storage)

    assert _scalar_rows(target, "SELECT id, name FROM utender2_archive_organizations") == [
        {"id": "org-1", "name": "Karkathar Welfare Trust"}
    ]
    assert report.archived["organizations"] == 1


def test_sessions_and_tokens_are_never_copied_or_archived(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-owner", "owner"))
    _insert(source, meta, "auth_tokens", {"id": "t1", "user_id": "u-owner", "token_hash": "abc"})

    report = _run(source, target, *storage)

    tables = set(inspect(target).get_table_names())
    assert "utender2_archive_auth_tokens" not in tables
    assert "auth_tokens" not in report.archived


def test_dry_run_reports_counts_and_leaves_the_target_empty(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-owner", "owner"), _user("u-sp", "service_provider"))
    _insert(source, meta, "organizations", {"id": "org-1", "name": "Trust"})

    report = _run(source, target, *storage, dry_run=True)

    assert report.dry_run is True
    assert report.copied["users"] == 2
    assert _scalar_rows(target, "SELECT COUNT(*) AS n FROM users") == [{"n": 0}]
    assert "utender2_archive_organizations" not in set(inspect(target).get_table_names())


def test_refuses_a_target_that_is_not_at_the_expected_revision(storage):
    source, meta = _source()
    target = _target(revision="0011")
    _insert(source, meta, "users", _user("u-owner", "owner"))

    with pytest.raises(ImportRefused, match="expected '0012'"):
        _run(source, target, *storage)


def test_refuses_a_target_that_already_has_rows(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-owner", "owner"))
    with target.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, email, password_hash, role, language, email_verified, created_at) "
            "VALUES ('existing', 'x@example.com', 'h', 'owner', 'en', 1, :now)"
        ), {"now": NOW})

    with pytest.raises(ImportRefused, match="already has rows"):
        _run(source, target, *storage)
    assert _scalar_rows(target, "SELECT COUNT(*) AS n FROM users") == [{"n": 1}]


def test_refuses_a_source_that_is_not_utender2(storage):
    source = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with source.begin() as conn:
        conn.execute(text("CREATE TABLE something_else (id INTEGER)"))

    with pytest.raises(ImportRefused, match="users table"):
        _run(source, _target(), *storage)


def test_projects_drop_organisation_columns_and_keep_the_owner(storage):
    source, meta = _source()
    target = _target()
    _insert(source, meta, "users", _user("u-owner", "owner"))
    _insert(source, meta, "projects", {
        "id": "p1", "owner_id": "u-owner", "organization_id": "org-9", "title": "Tower", "address": "Block 1",
        "bid_deadline": NOW, "status": "open", "tender_type": "sealed", "tender_type_locked": False,
        "is_suspended": False, "revision": 1, "created_at": NOW,
    })

    report = _run(source, target, *storage)

    assert _scalar_rows(target, "SELECT id, owner_id, title FROM projects") == [{"id": "p1", "owner_id": "u-owner", "title": "Tower"}]
    assert report.dropped_columns["projects"] == ["organization_id"]
