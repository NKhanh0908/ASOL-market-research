from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from casual_scout.config import Settings
from casual_scout.storage import Repository
from casual_scout.web.app import create_app


@pytest.fixture
def launcher_calls() -> list[tuple[str, Path]]:
    calls: list[tuple[str, Path]] = []
    return calls


@pytest.fixture
def fake_launcher(launcher_calls: list[tuple[str, Path]]) -> Callable[[str, Path], int]:
    def _launcher(run_id: str, data_dir: Path) -> int:
        launcher_calls.append((run_id, data_dir))
        return 12345

    return _launcher


@pytest.fixture
def client(tmp_path: Path, fake_launcher: Callable[[str, Path], int]) -> TestClient:
    settings = Settings(tmp_path)
    repo = Repository(tmp_path)
    repo.initialize()
    app = create_app(settings, launcher=fake_launcher)
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_bad_origin_cannot_start_collection(client: TestClient, launcher_calls: list):
    response = client.post(
        "/runs",
        headers={"Origin": "https://example.org"},
        data={"country": "vn", "request_key": "x"},
    )
    assert response.status_code == 403
    assert launcher_calls == []


def test_bad_host_rejected(client: TestClient):
    response = client.get("/", headers={"Host": "evil.com"})
    assert response.status_code in (400, 403)


def test_missing_csrf_token_rejected(client: TestClient, launcher_calls: list):
    response = client.post(
        "/runs",
        headers={"Origin": "http://127.0.0.1:8000"},
        data={"country": "vn", "request_key": "x"},
    )
    assert response.status_code == 403
    assert launcher_calls == []
