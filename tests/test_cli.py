import subprocess
import sys
from pathlib import Path


def test_cli_init(tmp_path: Path):
    cmd = [
        sys.executable,
        "-m",
        "casual_scout",
        "init",
        "--data-dir",
        str(tmp_path.resolve()),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert (tmp_path / "casual-scout.sqlite3").is_file()


def test_cli_collect_invalid_country(tmp_path: Path):
    cmd = [
        sys.executable,
        "-m",
        "casual_scout",
        "collect",
        "--countries",
        "invalid_country",
        "--data-dir",
        str(tmp_path.resolve()),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "unknown country" in result.stderr.lower() or "invalid" in result.stderr.lower()
