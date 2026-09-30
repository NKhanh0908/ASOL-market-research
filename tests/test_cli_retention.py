from pathlib import Path
import sqlite3
import pytest

from casual_scout.cli import main


def test_cli_retention_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["retention", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    assert "--apply" in captured.out


def test_cli_retention_dry_run_output(tmp_path: Path, capsys):
    db_file = tmp_path / "casual-scout.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT, raw_hash TEXT)")
    conn.commit()
    conn.close()

    exit_code = main(["retention", "--dry-run", "--data-dir", str(tmp_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Cutoff (UTC):" in captured.out
    assert "Expired snapshots:" in captured.out
    assert "Reclaimable bytes:" in captured.out


def test_cli_retention_apply_output(tmp_path: Path, capsys):
    db_file = tmp_path / "casual-scout.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE snapshots (id TEXT PRIMARY KEY, observed_at TEXT, raw_hash TEXT)")
    conn.commit()
    conn.close()

    exit_code = main(["retention", "--apply", "--data-dir", str(tmp_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Retention applied:" in captured.out
