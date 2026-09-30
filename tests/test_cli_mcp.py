import pytest
from casual_scout.cli import main

def test_mcp_serve_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["mcp-serve", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--port" in captured.out
    assert "--data-dir" in captured.out
    assert "--host" in captured.out
