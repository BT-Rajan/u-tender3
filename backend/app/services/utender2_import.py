"""One-time import of a utender2 database into a fresh u-tender3 database.

Reads the source read-only. Writes the target in one transaction. A dry run
does the same work and rolls it back.

What happens to each source table:
- Mapped tables are copied into their u-tender3 equivalent. Columns u-tender3 does
  not have are dropped, and the names of those columns appear in the report.
- Tables u-tender3 has no place for (organizations, agreements, milestones,
  variations, participations, offer documents, notifications and the rest) are
  copied verbatim into utender2_archive_<name> tables. Nothing is discarded.
- Sessions and one-time tokens (auth_tokens, revoked_tokens, email_change_requests)
  are never copied. Everyone signs in again afterwards.

Decisions this module makes:
- Role service_provider becomes contractor. Profiles follow the user.
- Offer status draft is not imported: drafts were never submitted and nobody else
  saw them. Status closed becomes rejected, because the requirement ended without an award.
- Deactivated accounts are imported with password_hash cleared, so they cannot sign
  in. u-tender3 has no deactivation flag, so an admin must suspend them again.
- Document files are copied from the utender2 storage root to the u-tender3 storage
  root under the same relative paths. Missing files are reported, not ignored.
"""

import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from sqlalchemy import Column, MetaData, Table, func, insert, inspect, select, text
from sqlalchemy.engine import Connection, Engine

from app.db import Base

EXPECTED_TARGET_REVISION = "0012"
BATCH_SIZE = 500

ROLE_MAP = {"owner": "owner", "service_provider": "contractor", "admin": "admin"}
OFFER_STATUS_MAP = {
    "submitted": "submitted",
    "approved": "approved",
    "rejected": "rejected",
    "withdrawn": "withdrawn",
    "closed": "rejected",
}
SKIPPED_OFFER_STATUSES = {"draft"}
FILE_COLUMNS = {"file_path", "previous_file_path"}

# A renamed column keeps its meaning under its u-tender3 name.
RENAMES = {"service_provider_id": "contractor_id"}

# Credentials and sessions are never moved.
NEVER_COPIED = {"auth_tokens", "revoked_tokens", "email_change_requests"}

# Source table -> u-tender3 table, in foreign-key order (parents first).
MAPPED_TABLES: list[tuple[str, str]] = [
    ("users", "users"),
    ("owner_profiles", "owner_profiles"),
    ("service_provider_profiles", "contractor_profiles"),
    ("document_requirements", "document_requirements"),
    ("service_provider_documents", "contractor_documents"),
    ("owner_documents", "owner_documents"),
    ("projects", "projects"),
    ("project_amendments", "project_amendments"),
    ("project_drawings", "project_drawings"),
    ("offers", "offers"),
    ("offer_revisions", "offer_revisions"),
    ("award_records", "award_records"),
    ("reviews", "reviews"),
    ("payment_overrides", "payment_overrides"),
    ("clarifications", "clarifications"),
    ("cms_content", "cms_content"),
    ("audit_logs", "audit_logs"),
]


class ImportRefused(Exception):
    """The target or source is not in a state the import can safely write to."""


@dataclass
class ImportReport:
    dry_run: bool
    copied: dict[str, int] = field(default_factory=dict)
    dropped_columns: dict[str, list[str]] = field(default_factory=dict)
    archived: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    deactivated_user_ids: list[str] = field(default_factory=list)
    files_copied: int = 0
    files_missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "copied": self.copied,
            "dropped_columns": self.dropped_columns,
            "archived": self.archived,
            "skipped": self.skipped,
            "deactivated_user_ids": self.deactivated_user_ids,
            "files_copied": self.files_copied,
            "files_missing": self.files_missing,
        }


@dataclass
class _State:
    kept_offer_ids: set[str] = field(default_factory=set)
    requirement_ids: dict[str, str] = field(default_factory=dict)
    target_requirements: dict[tuple[str, str], str] = field(default_factory=dict)
    file_paths: set[str] = field(default_factory=set)
    report: ImportReport | None = None

    def skip(self, table: str) -> None:
        assert self.report is not None
        self.report.skipped[table] = self.report.skipped.get(table, 0) + 1


Transform = Callable[[dict[str, Any], _State], dict[str, Any] | None]


def _map_role(value: str) -> str:
    if value not in ROLE_MAP:
        raise ImportRefused(f"Unknown role {value!r} in utender2 users.")
    return ROLE_MAP[value]


def _transform_user(row: dict[str, Any], state: _State) -> dict[str, Any]:
    row["role"] = _map_role(row["role"])
    if row.get("deactivated_at") is not None:
        row["password_hash"] = None
        assert state.report is not None
        state.report.deactivated_user_ids.append(row["id"])
    return row


def _transform_requirement(row: dict[str, Any], state: _State) -> dict[str, Any] | None:
    applies_to = _map_role(row["applies_to"]) if row.get("applies_to") else "owner"
    key = (row["name"], applies_to)
    row["applies_to"] = applies_to
    if key in state.target_requirements:
        state.requirement_ids[row["id"]] = state.target_requirements[key]
        state.skip("document_requirements")
        return None
    new_id = str(uuid.uuid4())
    state.requirement_ids[row["id"]] = new_id
    row["id"] = new_id
    return row


def _transform_document(row: dict[str, Any], state: _State) -> dict[str, Any] | None:
    requirement_id = state.requirement_ids.get(row["requirement_id"])
    if requirement_id is None:
        state.skip("contractor_documents" if "contractor_id" in row else "owner_documents")
        return None
    row["requirement_id"] = requirement_id
    return row


def _transform_offer(row: dict[str, Any], state: _State) -> dict[str, Any] | None:
    if row["status"] in SKIPPED_OFFER_STATUSES:
        state.skip("offers")
        return None
    if row.get("amount") is None:
        state.skip("offers")
        return None
    row["status"] = OFFER_STATUS_MAP[row["status"]]
    state.kept_offer_ids.add(row["id"])
    return row


def _transform_offer_child(row: dict[str, Any], state: _State) -> dict[str, Any] | None:
    if row.get("offer_id") not in state.kept_offer_ids:
        return None
    if row.get("status") in SKIPPED_OFFER_STATUSES:
        return None
    if "status" in row:
        row["status"] = OFFER_STATUS_MAP[row["status"]]
    return row


TRANSFORMS: dict[str, Transform] = {
    "users": _transform_user,
    "document_requirements": _transform_requirement,
    "service_provider_documents": _transform_document,
    "owner_documents": _transform_document,
    "offers": _transform_offer,
    "offer_revisions": _transform_offer_child,
    "award_records": _transform_offer_child,
}


def _rows(conn: Connection, table: Table):
    return conn.execute(select(table)).mappings()


def _copy_mapped(src: Connection, dst: Connection, src_meta: MetaData, dst_meta: MetaData, source: str, target: str, state: _State) -> None:
    assert state.report is not None
    src_table = src_meta.tables[source]
    dst_table = dst_meta.tables[target]
    named = {RENAMES.get(column.name, column.name): column.name for column in src_table.c}
    keep = [name for name in named if name in dst_table.c]
    state.report.dropped_columns[source] = sorted(named[name] for name in named if name not in dst_table.c)
    transform = TRANSFORMS.get(target, TRANSFORMS.get(source))

    batch: list[dict[str, Any]] = []
    copied = 0
    for source_row in _rows(src, src_table):
        full = {RENAMES.get(key, key): value for key, value in source_row.items()}
        out = transform(full, state) if transform else full
        if out is None:
            continue
        for name in FILE_COLUMNS & set(out):
            if out[name]:
                state.file_paths.add(str(out[name]))
        batch.append({name: out[name] for name in keep})
        if len(batch) >= BATCH_SIZE:
            dst.execute(insert(dst_table), batch)
            copied += len(batch)
            batch = []
    if batch:
        dst.execute(insert(dst_table), batch)
        copied += len(batch)
    state.report.copied[source] = copied


def _archive(src: Connection, dst: Connection | None, src_meta: MetaData, source: str, state: _State, *, dry_run: bool) -> None:
    assert state.report is not None
    src_table = src_meta.tables[source]
    archive_name = f"utender2_archive_{source}"
    rows = [dict(row) for row in _rows(src, src_table)]
    state.report.archived[source] = len(rows)
    for row in rows:
        for name in FILE_COLUMNS & set(row):
            if row[name]:
                state.file_paths.add(str(row[name]))
    if dry_run or dst is None:
        return
    archive = Table(archive_name, MetaData(), *[Column(column.name, column.type) for column in src_table.c])
    archive.create(dst)
    for start in range(0, len(rows), BATCH_SIZE):
        dst.execute(insert(archive), rows[start : start + BATCH_SIZE])


def _check_target(dst: Connection, dst_meta: MetaData, archive_names: list[str]) -> None:
    inspector = inspect(dst)
    if not inspector.has_table("alembic_version"):
        raise ImportRefused("Target has no alembic_version table. Run `alembic upgrade head` on the target first.")
    revision = dst.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if revision != EXPECTED_TARGET_REVISION:
        raise ImportRefused(f"Target is at revision {revision!r}; expected {EXPECTED_TARGET_REVISION!r}.")
    for _, target in MAPPED_TABLES:
        if target == "document_requirements":
            continue
        if not inspector.has_table(target):
            raise ImportRefused(f"Target table {target!r} is missing.")
        if dst.execute(select(func.count()).select_from(dst_meta.tables[target])).scalar():
            raise ImportRefused(f"Target table {target!r} already has rows. Import needs an empty target.")
    for name in archive_names:
        if inspector.has_table(name):
            raise ImportRefused(f"Archive table {name!r} already exists in the target.")


def _safe_relative(path: str) -> PurePosixPath | None:
    candidate = PurePosixPath(path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        return None
    return candidate


def _copy_files(state: _State, storage_from: Path, storage_to: Path, *, dry_run: bool) -> None:
    assert state.report is not None
    for raw in sorted(state.file_paths):
        relative = _safe_relative(raw)
        if relative is None:
            state.report.files_missing.append(raw)
            continue
        source_file = storage_from / relative
        if not source_file.is_file():
            state.report.files_missing.append(raw)
            continue
        if dry_run:
            state.report.files_copied += 1
            continue
        destination = storage_to / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source_file, destination)
        state.report.files_copied += 1


def _load_target_requirements(dst: Connection, dst_meta: MetaData, state: _State) -> None:
    table = dst_meta.tables["document_requirements"]
    for row in dst.execute(select(table.c.id, table.c.name, table.c.applies_to)).mappings():
        applies_to = getattr(row["applies_to"], "value", row["applies_to"])
        state.target_requirements[(row["name"], applies_to)] = row["id"]


def import_utender2(
    source: Engine,
    target: Engine,
    *,
    storage_from: Path,
    storage_to: Path,
    dry_run: bool = False,
) -> ImportReport:
    """Copy a utender2 database into an empty u-tender3 database. Returns what happened."""
    report = ImportReport(dry_run=dry_run)
    state = _State(report=report)
    src_meta = MetaData()
    archive_sources = []

    with source.connect() as src:
        src_meta.reflect(bind=src)
        if "users" not in src_meta.tables:
            raise ImportRefused("Source has no users table. Is this a utender2 database?")
        archive_sources = sorted(
            name
            for name in src_meta.tables
            if name not in {source_name for source_name, _ in MAPPED_TABLES} and name not in NEVER_COPIED
        )
        archive_names = [f"utender2_archive_{name}" for name in archive_sources]

        with target.connect() as dst:
            transaction = dst.begin()
            try:
                # The ORM metadata, not a reflection of the target: it carries the Python-side
                # defaults for NOT NULL columns that the source does not have.
                dst_meta = Base.metadata
                _check_target(dst, dst_meta, archive_names)
                _load_target_requirements(dst, dst_meta, state)

                for source_name, target_name in MAPPED_TABLES:
                    if source_name in src_meta.tables:
                        _copy_mapped(src, dst, src_meta, dst_meta, source_name, target_name, state)

                for name in archive_sources:
                    _archive(src, dst, src_meta, name, state, dry_run=dry_run)

                _copy_files(state, storage_from, storage_to, dry_run=dry_run)
            except Exception:
                transaction.rollback()
                raise
            if dry_run:
                transaction.rollback()
            else:
                transaction.commit()
    return report
