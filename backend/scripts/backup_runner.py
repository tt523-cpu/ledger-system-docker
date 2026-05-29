import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.api.system import BACKUP_TABLES, _serialize_rows
from app.core.database import SessionLocal


def run_backup(output_dir: Path, keep: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        payload = {
            "meta": {"exported_at": datetime.utcnow().isoformat(), "exported_by": "scheduler"},
            "tables": {},
        }
        for table_name, model in BACKUP_TABLES:
            rows = db.execute(select(model)).scalars().all()
            payload["tables"][table_name] = _serialize_rows(rows, model)
    finally:
        db.close()

    name = f"accounting-backup-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
    target = output_dir / name
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    files = sorted(output_dir.glob("accounting-backup-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate JSON backup with retention")
    parser.add_argument("--output", default="./backups", help="backup output directory")
    parser.add_argument("--keep", type=int, default=30, help="files to keep")
    args = parser.parse_args()

    target = run_backup(Path(args.output), args.keep)
    print(target.as_posix())


if __name__ == "__main__":
    main()
