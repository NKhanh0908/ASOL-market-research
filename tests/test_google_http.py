from datetime import UTC, datetime
import httpx
import pytest

from casual_scout.providers.google_http import GoogleHttpClient


def test_retry_exhaustion_keeps_four_attempts():
    waits = []
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(429, content=b'rate limited')))
    result = GoogleHttpClient(client, sleep=waits.append).get('https://play.google.com/test')
    assert waits == [1, 2, 4]
    assert result.status == 429
    assert result.error
    assert len(result.attempts) == 3
    assert all(x.body == b'rate limited' for x in result.attempts)


def test_first_attempt_success_no_retries():
    waits = []
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b'success payload')))
    result = GoogleHttpClient(client, sleep=waits.append).get('https://play.google.com/success')
    assert waits == []
    assert result.status == 200
    assert result.body == b'success payload'
    assert result.error is None
    assert len(result.attempts) == 0


def test_retry_then_success():
    calls = 0
    waits = []

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, content=b'unavailable')
        return httpx.Response(200, content=b'now ok')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = GoogleHttpClient(client, sleep=waits.append).get('https://play.google.com/recovered')
    assert waits == [1]
    assert result.status == 200
    assert result.body == b'now ok'
    assert len(result.attempts) == 1
    assert result.attempts[0].status == 503


def test_404_not_found_not_retried():
    waits = []
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(404, content=b'not found')))
    result = GoogleHttpClient(client, sleep=waits.append).get('https://play.google.com/notfound')
    assert waits == []
    assert result.status == 404
    assert result.error == 'HTTP 404'
    assert len(result.attempts) == 0


def test_network_transport_error_retried_and_exhausted():
    waits = []

    def handler(request):
        raise httpx.ConnectError('connection failed', request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = GoogleHttpClient(client, sleep=waits.append).get('https://play.google.com/down')
    assert waits == [1, 2, 4]
    assert result.status is None
    assert result.body is None
    assert 'connection failed' in (result.error or '')
    assert len(result.attempts) == 3


def test_post_support_with_retries():
    calls = 0
    waits = []

    def handler(request):
        nonlocal calls
        calls += 1
        assert request.method == 'POST'
        assert request.content == b'f.req=test'
        if calls < 3:
            return httpx.Response(500, content=b'server error')
        return httpx.Response(200, content=b'post success')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = GoogleHttpClient(client, sleep=waits.append).post(
        'https://play.google.com/_/PlayStoreUi/data/batchexecute',
        content=b'f.req=test',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    assert waits == [1, 2]
    assert result.status == 200
    assert result.body == b'post success'
    assert len(result.attempts) == 2


def test_context_manager_lifecycle():
    with GoogleHttpClient() as client:
        assert client.client is not None
    assert client.client.is_closed
