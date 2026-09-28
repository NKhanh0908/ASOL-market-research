from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Lock
import httpx
import pytest

from casual_scout.models import Chart, HttpResult, ParsedChart
from casual_scout.providers.google import LOCALES, GooglePlayProvider
from casual_scout.providers.google_http import GoogleHttpClient


def test_locale_contract():
    assert LOCALES == {
        'vn': 'vi',
        'th': 'th',
        'id': 'id',
        'my': 'en',
        'ph': 'en',
        'sg': 'en',
        'la': 'en',
        'kh': 'en',
        'us': 'en',
    }


def test_empty_batch_does_not_call_network():
    class NoNetwork:
        def get(self, url, headers=None):
            raise AssertionError(url)
        def post(self, url, content=None, headers=None):
            raise AssertionError(url)

    provider = GooglePlayProvider(NoNetwork())
    assert provider.fetch_metadata('vn', []) == []


def test_fetch_chart_calls_post_and_parses():
    captured = {}

    def handler(request: httpx.Request):
        captured['url'] = str(request.url)
        captured['method'] = request.method
        captured['content'] = request.content
        fixture_path = Path(__file__).parent / "fixtures" / "google_play" / "vn_top_free.bin"
        return httpx.Response(200, content=fixture_path.read_bytes())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GooglePlayProvider(GoogleHttpClient(client))

    chart = Chart('vn', provider='google', platform='android', feed_type='top-free')
    http_result, parsed = provider.fetch_chart(chart)

    assert captured['method'] == 'POST'
    assert 'hl=vi' in captured['url']
    assert 'gl=VN' in captured['url']
    assert 'topselling_free' in captured['content'].decode()
    assert http_result.status == 200
    assert len(parsed.entries) == 100
    assert parsed.entries[0].app_id == 'com.fashion.dress.up'


def test_fetch_metadata_concurrency_and_deduplication():
    lock = Lock()
    active_workers = 0
    max_active_workers = 0
    requested_urls = []

    def handler(request: httpx.Request):
        nonlocal active_workers, max_active_workers
        with lock:
            active_workers += 1
            if active_workers > max_active_workers:
                max_active_workers = active_workers
            requested_urls.append(str(request.url))

        # Simulate small work
        import time
        time.sleep(0.01)

        with lock:
            active_workers -= 1

        mock_ds5 = [
            None,
            [
                None,
                None,
                [
                    ["Test App"],
                    None, None, None, None, None, None, None, None, None, None, None, None,
                    ["10,000+", 10000]
                ]
            ]
        ]
        html_body = f"<html><script>AF_initDataCallback({{key: 'ds:5', data: {json.dumps(mock_ds5)}, sideChannel: {{}}}});</script></html>"
        return httpx.Response(200, content=html_body.encode("utf-8"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GooglePlayProvider(GoogleHttpClient(client))

    # Send duplicates
    packages = [f'com.game.{i}' for i in range(15)] + ['com.game.0', 'com.game.1']
    results = provider.fetch_metadata('vn', packages)

    # Deduped to 15 unique
    assert len(results) == 15
    assert len(requested_urls) == 15
    assert max_active_workers <= 10
    assert max_active_workers > 1

    for http_res, meta_dict in results:
        assert http_res.status == 200
        pkg = list(meta_dict.keys())[0]
        assert meta_dict[pkg]['name'] == 'Test App'
        assert meta_dict[pkg]['min_installs'] == 10000


def test_fetch_metadata_error_retains_partial_status():
    def handler(request: httpx.Request):
        return httpx.Response(404, content=b"Not found")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GooglePlayProvider(GoogleHttpClient(client))

    results = provider.fetch_metadata('vn', ['com.removed.game'])
    assert len(results) == 1
    http_res, meta_dict = results[0]
    assert http_res.status == 404
    assert meta_dict['com.removed.game']['status'] == 'partial'
    assert '404' in meta_dict['com.removed.game']['error']
