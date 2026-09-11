from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from casual_scout.storage import Repository


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def create_backup(repo: Repository, destination: Path) -> Path:
    dest_path = Path(destination).resolve()
    data_path = repo.data_dir.resolve()

    if data_path == dest_path or data_path in dest_path.parents:
        raise ValueError("destination cannot be inside data_dir")

    dest_path.mkdir(parents=True, exist_ok=True)
    db_name = repo.database_path.name
    target_db_path = dest_path / db_name

    # Atomic SQLite backup
    with closing(sqlite3.connect(repo.database_path)) as source_conn, closing(
        sqlite3.connect(target_db_path)
    ) as target_conn:
        source_conn.backup(target_conn)

    # Query referenced raw files from the backed-up database
    with closing(sqlite3.connect(target_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        raw_rows = conn.execute("SELECT hash, path FROM raw_responses").fetchall()


    raw_manifest = []
    for r in raw_rows:
        raw_hash = str(r["hash"])
        rel_path = str(r["path"])
        source_raw_file = repo.data_dir / rel_path

        if not source_raw_file.is_file():
            # Clean up target db on failure
            target_db_path.unlink(missing_ok=True)
            raise FileNotFoundError(f"Missing referenced raw file: {rel_path}")

        file_bytes = source_raw_file.read_bytes()
        actual_hash = _sha256(file_bytes)
        if actual_hash != raw_hash:
            target_db_path.unlink(missing_ok=True)
            raise ValueError(f"Corrupt raw file {rel_path}: expected hash {raw_hash}, got {actual_hash}")

        target_raw_file = dest_path / rel_path
        target_raw_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_raw_file, target_raw_file)

        raw_manifest.append({"hash": raw_hash, "path": rel_path})

    manifest = {
        "created_at": _utc_text(datetime.now(UTC)),
        "database": db_name,
        "raw_files": raw_manifest,
    }

    manifest_path = dest_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def restore_backup(manifest_path: Path, target_data_dir: Path) -> Repository:
    manifest_file = Path(manifest_path).resolve()
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Manifest not found at {manifest_file}")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    backup_dir = manifest_file.parent
    target_dir = Path(target_data_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    db_name = manifest["database"]
    source_db = backup_dir / db_name
    target_db = target_dir / db_name
    shutil.copy2(source_db, target_db)

    for raw in manifest.get("raw_files", []):
        rel_path = raw["path"]
        expected_hash = raw["hash"]
        source_raw = backup_dir / rel_path
        target_raw = target_dir / rel_path
        target_raw.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_raw, target_raw)

        restored_bytes = target_raw.read_bytes()
        if _sha256(restored_bytes) != expected_hash:
            raise ValueError(f"Restored raw file {rel_path} failed checksum verification")

    return Repository(target_dir)
