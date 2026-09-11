from pathlib import Path
import pytest
from casual_scout.cli import main
from casual_scout.storage import Repository

def test_cli_stats_radar_help(capsys):
    with pytest.raises(SystemExit) as e:
        main(["stats", "radar", "--help"])
    assert e.value.code == 0
    captured = capsys.readouterr()
    assert "radar" in captured.out

def test_cli_stats_overview_help(capsys):
    with pytest.raises(SystemExit) as e:
        main(["stats", "overview", "--help"])
    assert e.value.code == 0
    captured = capsys.readouterr()
    assert "overview" in captured.out

def test_cli_shortlist_commands(tmp_path: Path, capsys):
    data_dir = tmp_path / "data"
    repo = Repository(data_dir)
    repo.initialize()

    # Add item via CLI
    code = main([
        "shortlist", "add", "1001",
        "--title", "Block Puzzle Pro",
        "--country", "vn",
        "--rank", "3",
        "--subgenre", "Puzzle",
        "--mechanic", "Block Puzzle",
        "--priority", "HIGH",
        "--notes", "Great mechanics",
        "--data-dir", str(data_dir)
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "Added/Updated shortlist" in captured.out

    # List items via CLI
    code_list = main(["shortlist", "list", "--data-dir", str(data_dir)])
    assert code_list == 0
    captured_list = capsys.readouterr()
    assert "Block Puzzle Pro" in captured_list.out
    assert "1001" in captured_list.out
