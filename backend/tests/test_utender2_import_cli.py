"""The import command: refuses bad targets with exit 2, writes a JSON report, and never writes in a dry run."""

import importlib.util
import json
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db import Base

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_utender2.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("import_utender2_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_file(tmp_path: Path) -> str:
    path = tmp_path / "utender2.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(255), password_hash VARCHAR(255), role VARCHAR(40), full_name VARCHAR(255), phone VARCHAR(50), language VARCHAR(4), email_verified BOOLEAN, created_at DATETIME, deactivated_at DATETIME, session_version INTEGER)"))
        conn.execute(text("INSERT INTO users VALUES ('u1', 'u1@example.com', 'hash', 'service_provider', 'N', NULL, 'en', 1, '2026-11-23 09:00:00', NULL, 0)"))
    engine.dispose()
    return f"sqlite:///{path}"


def _target_file(tmp_path: Path, revision: str = "0012") -> str:
    path = tmp_path / "u-tender3.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": revision})
    engine.dispose()
    return f"sqlite:///{path}"


def test_dry_run_reports_and_writes_nothing(tmp_path):
    cli = _load_cli()
    report_path = tmp_path / "report.json"
    storage = tmp_path / "source-storage"
    storage.mkdir()
    target_url = _target_file(tmp_path)

    code = cli.main([
        "--source", _source_file(tmp_path),
        "--target", target_url,
        "--storage-from", str(storage),
        "--storage-to", str(tmp_path / "out"),
        "--dry-run",
        "--report", str(report_path),
    ])

    assert code == 0
    report = json.loads(report_path.read_text())
    assert report["dry_run"] is True
    assert report["copied"]["users"] == 1
    target = create_engine(target_url)
    with target.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar() == 0


def test_a_refused_import_exits_with_2(tmp_path):
    cli = _load_cli()
    storage = tmp_path / "source-storage"
    storage.mkdir()

    code = cli.main([
        "--source", _source_file(tmp_path),
        "--target", _target_file(tmp_path, revision="0009"),
        "--storage-from", str(storage),
        "--storage-to", str(tmp_path / "out"),
    ])

    assert code == 2


def test_a_real_import_commits_the_rows(tmp_path):
    cli = _load_cli()
    storage = tmp_path / "source-storage"
    storage.mkdir()
    target_url = _target_file(tmp_path)

    code = cli.main([
        "--source", _source_file(tmp_path),
        "--target", target_url,
        "--storage-from", str(storage),
        "--storage-to", str(tmp_path / "out"),
    ])

    assert code == 0
    target = create_engine(target_url)
    with target.connect() as conn:
        assert conn.execute(text("SELECT role FROM users WHERE id = 'u1'")).scalar() == "contractor"
