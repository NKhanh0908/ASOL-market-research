from pathlib import Path
from casual_scout.models import Chart
from casual_scout.providers.apple import AppleProvider, _chart_url
from casual_scout.config import Settings


def test_apple_provider_constructs_grossing_url(tmp_path: Path):
    settings = Settings(tmp_path / "data")
    provider = AppleProvider(settings)
    c_free = Chart("vn", feed_type="top-free")
    c_grossing = Chart("vn", feed_type="top-grossing")

    url_free = provider.chart_url(c_free)
    url_grossing = provider.chart_url(c_grossing)

    assert "topfreeapplications" in url_free or "top-free" in url_free
    assert "topgrossingapplications" in url_grossing or "top-grossing" in url_grossing


def test_apple_provider_chart_url_standalone():
    c_grossing = Chart("us", feed_type="top-grossing")
    url = _chart_url(c_grossing)
    assert "https://itunes.apple.com/us/rss/topgrossingapplications/limit=100/genre=7003/json" == url
