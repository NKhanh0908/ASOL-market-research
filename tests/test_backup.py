import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from casual_scout.models import Chart, HttpResult
from casual_scout.operations.backup import create_backup, restore_backup
from casual_scout.providers.apple import parse_chart
from casual_scout.storage import Repository


@pytest.fixture
def repo_with_snapshot(tmp_path: Path, evidence_dir: Path):
    repo = Repository(tmp_path / "data")
    repo.initialize()

    from casual_scout.collection.jobs import JobService

    jobs = JobService(repo)
    run_id = jobs.submit("manual", ["vn"], "req-backup-test")

    body = (evidence_dir / "vn-casual-100.json").read_bytes()
    parsed = parse_chart(body, Chart("vn"))
    http_res = HttpResult(
        url="https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json",
        started_at=datetime.now(UTC),
        elapsed_ms=50,
        status=200,
        body=body,
        headers={"content-type": "application/json"},
        error=None,
    )
    repo.save_snapshot(run_id, http_res, parsed)
    return repo


def test_backup_includes_all_referenced_raw(repo_with_snapshot: Repository, tmp_path: Path):
    backup_dest = tmp_path / "backups" / "backup-1"
    manifest_path = create_backup(repo_with_snapshot, backup_dest)
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["database"] == "casual-scout.sqlite3"
    assert len(manifest["raw_files"]) >= 1

    for raw in manifest["raw_files"]:
        raw_file = manifest_path.parent / raw["path"]
        assert raw_file.is_file()


def test_backup_rejects_destination_inside_data_dir(repo_with_snapshot: Repository):
    inside_dest = repo_with_snapshot.data_dir / "backups"
    with pytest.raises(ValueError, match="inside data_dir"):
        create_backup(repo_with_snapshot, inside_dest)


def test_restore_backup_integrity(repo_with_snapshot: Repository, tmp_path: Path):
    backup_dest = tmp_path / "backups" / "backup-restore"
    manifest_path = create_backup(repo_with_snapshot, backup_dest)

    restore_target = tmp_path / "restored_data"
    restored_repo = restore_backup(manifest_path, restore_target)

    # Verify SQLite foreign keys & integrity
    with sqlite3.connect(restored_repo.database_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        assert integrity == "ok"

        # Check snapshot exists
        snapshots = conn.execute("SELECT count(*) as count FROM snapshots").fetchone()
        assert snapshots["count"] >= 1


def test_backup_fails_if_referenced_raw_missing(repo_with_snapshot: Repository, tmp_path: Path):
    # Manually delete the raw file from source
    raw_dir = repo_with_snapshot.data_dir / "raw"
    for f in raw_dir.rglob("*"):
        if f.is_file():
            f.unlink()


    backup_dest = tmp_path / "backups" / "backup-missing"
    with pytest.raises(FileNotFoundError, match="Missing referenced raw file"):
        create_backup(repo_with_snapshot, backup_dest)




def test_restore_fails_on_hash_mismatch(repo_with_snapshot: Repository, tmp_path: Path):
    backup_dest = tmp_path / "backups" / "backup-tampered"
    manifest_path = create_backup(repo_with_snapshot, backup_dest)

    # Tamper with a raw file in the backup
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_raw = manifest["raw_files"][0]
    tampered_file = manifest_path.parent / first_raw["path"]
    tampered_file.write_bytes(b"tampered content")

    restore_target = tmp_path / "restored_tampered"
    with pytest.raises(ValueError, match="checksum"):
        restore_backup(manifest_path, restore_target)


