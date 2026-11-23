"""Import a utender2 database into an empty u-tender3 database.

Run a dry run first. It does the whole import, reports what would happen, and rolls back.
Only run without --dry-run after reading the report and taking a verified backup of the target.

Usage (from the backend folder):

    python scripts/import_utender2.py \\
        --source 'mysql+pymysql://USER:PASSWORD@HOST/utender2' \\
        --storage-from /path/to/utender2/storage \\
        --dry-run --report /path/to/import-report.json

Passwords belong in the URL you type here, not in a file in the repository.
The target defaults to DATABASE_URL and the storage root to STORAGE_ROOT.
The module docstring in app/services/utender2_import.py lists every decision this import makes.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.services.utender2_import import ImportRefused, import_utender2  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Import a utender2 database into u-tender3.")
    parser.add_argument("--source", required=True, help="SQLAlchemy URL of the utender2 database (read only).")
    parser.add_argument("--target", default=settings.database_url, help="SQLAlchemy URL of an empty u-tender3 database.")
    parser.add_argument("--storage-from", required=True, type=Path, help="utender2 storage root that holds the document files.")
    parser.add_argument("--storage-to", default=Path(settings.storage_root), type=Path, help="u-tender3 storage root.")
    parser.add_argument("--dry-run", action="store_true", help="Do everything, then roll back. Writes no rows and no files.")
    parser.add_argument("--report", type=Path, help="Write the report as JSON to this path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = create_engine(args.source)
    target = create_engine(args.target)
    try:
        report = import_utender2(
            source,
            target,
            storage_from=args.storage_from,
            storage_to=args.storage_to,
            dry_run=args.dry_run,
        )
    except ImportRefused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2
    finally:
        source.dispose()
        target.dispose()

    summary = report.to_dict()
    if args.report:
        args.report.write_text(json.dumps(summary, indent=2, sort_keys=True))
    mode = "DRY RUN (rolled back)" if report.dry_run else "IMPORTED"
    print(f"{mode}")
    for table, count in sorted(report.copied.items()):
        print(f"  copied   {table}: {count}")
    for table, count in sorted(report.archived.items()):
        print(f"  archived {table}: {count}")
    for table, count in sorted(report.skipped.items()):
        print(f"  skipped  {table}: {count}")
    for table, columns in sorted(report.dropped_columns.items()):
        if columns:
            print(f"  dropped columns in {table}: {', '.join(columns)}")
    print(f"  deactivated accounts (password cleared): {len(report.deactivated_user_ids)}")
    print(f"  files copied: {report.files_copied}, missing: {len(report.files_missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
