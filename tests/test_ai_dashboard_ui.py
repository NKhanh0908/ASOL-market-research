"""Dashboard UI contracts; all requests use local test data, never a provider."""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from casual_scout.config import Settings
from casual_scout.storage import Repository
from casual_scout.web.app import create_app
from tests.ai_support import seed_ai_evidence


class NoopScheduler:
    def start(self):
        pass

    def stop(self):
        pass


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def by_id(self, identifier):
        return next(attrs for _, attrs in self.elements if attrs.get("id") == identifier)


@pytest.fixture
def dashboard_client(tmp_path):
    repo = Repository(tmp_path)
    repo.initialize()
    seed_ai_evidence(repo)
    app = create_app(Settings(tmp_path), scheduler_factory=lambda *_: NoopScheduler())
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        yield client


@pytest.mark.parametrize("market", ["vn", "all"])
def test_ios_action_inherits_selected_scope_and_csrf(dashboard_client, market):
    response = dashboard_client.get(f"/dashboard?date=2026-09-25&country={market}&platform=ios")
    markup = Markup(response.text)
    action = markup.by_id("ai-create")
    assert action["type"] == "button"
    assert action["data-date"] == "2026-09-25"
    assert action["data-market"] == market
    assert action["data-csrf"] == dashboard_client.cookies["csrftoken"]
    assert "Tạo gợi ý AI" in response.text
    assert any(tag == "a" and attrs.get("href") == "/recommendations" for tag, attrs in markup.elements)
    assert markup.by_id("ai-confirm")["aria-labelledby"] == "ai-confirm-title"
    assert markup.by_id("ai-warning")["aria-live"] == "polite"
    assert "disabled" in markup.by_id("ai-submit")
    assert markup.by_id("ai-unknown")["type"] == "checkbox"
    for asset in ("recommendations.js", "recommendations.css"):
        assert re.search(r"/static/" + re.escape(asset) + r"\?v=[^\"\s]+", response.text)


def test_android_has_no_ios_ai_action(dashboard_client):
    html = dashboard_client.get("/dashboard?platform=android").text
    assert 'id="ai-create"' not in html
    assert 'id="ai-confirm"' not in html
    assert "recommendations.js" not in html


def test_mock_demo_disables_ai_action(tmp_path):
    Repository(tmp_path).initialize()
    (tmp_path / "MOCK_DATA.json").write_text("{}", encoding="utf-8")
    with TestClient(create_app(Settings(tmp_path), scheduler_factory=lambda *_: NoopScheduler())) as client:
        action = Markup(client.get("/dashboard").text).by_id("ai-create")
        assert "disabled" in action


def test_dashboard_script_has_no_unsafe_html_or_automatic_requests():
    script = Path("src/casual_scout/web/static/recommendations.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script
    assert "insertAdjacentHTML" not in script
    assert "setInterval" not in script
    assert "setTimeout" not in script
    assert 'addEventListener("click"' in script
    assert 'addEventListener("cancel"' in script
    assert 'addEventListener("close"' in script
