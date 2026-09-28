import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
import test_backup
from ai_support import request

from casual_scout.ai.contracts import EvidenceRef
from casual_scout.ai.storage import EvaluationStore
from casual_scout.models import HttpResult
from casual_scout.operations.backup import create_backup, restore_backup
from casual_scout.providers.apple import parse_lookup
from casual_scout.storage import Repository


@pytest.fixture
def backup_repo_with_snapshot(tmp_path: Path, evidence_dir: Path) -> Repository:
    return test_backup.repo_with_snapshot.__wrapped__(tmp_path, evidence_dir)


def test_blocked_ai_history_survives_backup_restore(tmp_path: Path):
    repo = Repository(tmp_path / "data")
    repo.initialize()
    store = EvaluationStore(repo)
    run = store.create(request(), blocked_reason="provider_not_configured")

    manifest = create_backup(repo, tmp_path / "backup")
    restored = restore_backup(manifest, tmp_path / "restored")

    assert EvaluationStore(restored).get(run["id"]) == run
    assert EvaluationStore(restored).list_runs() == [run]


def test_ai_evidence_and_raw_files_survive_backup_restore(
    backup_repo_with_snapshot: Repository, evidence_dir: Path, tmp_path: Path
):
    repo = backup_repo_with_snapshot
    with repo._connect() as db:
        snapshot = db.execute(
            "SELECT snapshots.id, snapshots.raw_hash, entries.app_id "
            "FROM snapshots JOIN entries ON entries.snapshot_id = snapshots.id "
            "WHERE entries.rank = 1"
        ).fetchone()
    assert snapshot is not None

    body = (evidence_dir / "vn-lookup-casual-20.json").read_bytes()
    app_id = snapshot["app_id"]
    metadata = parse_lookup(body, [app_id])
    assert app_id in metadata
    lookup = HttpResult(
        url=f"https://itunes.apple.com/lookup?country=vn&id={app_id}",
        started_at=datetime.now(UTC),
        elapsed_ms=50,
        status=200,
        body=body,
        headers={"content-type": "application/json"},
        error=None,
    )
    metadata_id = repo.save_metadata("vn", metadata, lookup)[app_id]
    repo.bind_metadata(snapshot["id"], {app_id: metadata_id})

    evidence = EvidenceRef(
        "evidence-1", "2026-09-25", "vn", app_id,
        snapshot_id=snapshot["id"], metadata_version_id=metadata_id,
    )
    store = EvaluationStore(repo)
    run = store.create(replace(request(), evidence=(evidence,)))
    assert store.claim(run["id"], 1234, 1.0)
    finished = store.finish(
        run["id"], "succeeded",
        result={"schema_version": "1", "recommendations": []},
    )

    manifest_path = create_backup(repo, tmp_path / "backup")
    restored = restore_backup(manifest_path, tmp_path / "restored")

    assert EvaluationStore(restored).get(run["id"]) == finished
    assert finished["actual_cost_usd"] is None
    assert finished["cost_method"] is None
    with restored._connect() as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        restored_links = db.execute(
            "SELECT snapshot_id, metadata_version_id FROM ai_run_evidence "
            "WHERE run_id = ?", (run["id"],)
        ).fetchone()
        assert tuple(restored_links) == (snapshot["id"], metadata_id)
        metadata_hash = db.execute(
            "SELECT raw_hash FROM metadata_versions WHERE id = ?", (metadata_id,)
        ).fetchone()[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = {entry["hash"] for entry in manifest["raw_files"]}
    assert snapshot["raw_hash"] in hashes
    assert metadata_hash == sha256(body).hexdigest()
    assert metadata_hash in hashes
    for entry in manifest["raw_files"]:
        raw_path = restored.data_dir / entry["path"]
        assert sha256(raw_path.read_bytes()).hexdigest() == entry["hash"]
