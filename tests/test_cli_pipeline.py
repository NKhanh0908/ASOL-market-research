from __future__ import annotations

from pathlib import Path

from casual_scout import cli


def test_pipeline_analyzes_vietnam_after_a_partial_collection(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[object] = []

    class FakeCollector:
        def __init__(self, *args: object) -> None:
            pass

        def execute(self, run_id: str, *, enrich: bool = True) -> str:
            calls.append(("collect", run_id, enrich))
            return "partial"

    class FakeAnalysisService:
        def __init__(self, repository: object) -> None:
            calls.append(("analysis_service", repository))

        def analyze_date(self, date: str, countries: list[str]) -> dict[str, object]:
            calls.append(("analyze", date, countries))
            return {"markets": countries}

    monkeypatch.setattr(cli, "Collector", FakeCollector)
    monkeypatch.setattr(cli, "AnalysisService", FakeAnalysisService)

    exit_code = cli.main(
        ["pipeline", "--run-id", "run-123", "--data-dir", str(tmp_path / "data")]
    )

    assert exit_code == 0
    assert calls[0] == ("collect", "run-123", True)
    assert calls[-1][0] == "analyze"
    assert calls[-1][2] == ["vn"]


def test_pipeline_does_not_analyze_when_collection_fails(tmp_path: Path, monkeypatch) -> None:
    class FakeCollector:
        def __init__(self, *args: object) -> None:
            pass

        def execute(self, run_id: str, *, enrich: bool = True) -> str:
            return "failed"

    class UnexpectedAnalysisService:
        def __init__(self, repository: object) -> None:
            raise AssertionError("analysis must not run after a failed collection")

    monkeypatch.setattr(cli, "Collector", FakeCollector)
    monkeypatch.setattr(cli, "AnalysisService", UnexpectedAnalysisService)

    exit_code = cli.main(
        ["pipeline", "--run-id", "run-123", "--data-dir", str(tmp_path / "data")]
    )

    assert exit_code == 1
