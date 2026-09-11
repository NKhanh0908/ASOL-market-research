from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from threading import Event, Thread

import httpx

from casual_scout.config import Settings
from casual_scout.providers.http import HttpClient, RequestGate


class FakeClock:
    def __init__(self):
        self.current = datetime(2026, 9, 10, tzinfo=UTC)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


def test_429_is_retried_and_every_attempt_is_exposed(tmp_path):
    clock = FakeClock()
    request_times: list[datetime] = []
    observations = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_times.append(clock.now())
        if len(request_times) == 1:
            return httpx.Response(429, content=b"slow down", request=request)
        return httpx.Response(200, content=b"ok", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = HttpClient(
            Settings(data_dir=tmp_path), transport, sleep=clock.sleep, clock=clock.now,
            on_observation=observations.append, gate=RequestGate(),
        ).get("https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json")

    assert result.status == 200
    assert [item.status for item in result.attempts] == [429, 200]
    assert [item.status for item in observations] == [429, 200]
    assert request_times[1] - request_times[0] >= timedelta(seconds=4)


def test_timeout_exhausts_three_attempts_and_keeps_each_timeout(tmp_path):
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = HttpClient(
            Settings(data_dir=tmp_path), transport, sleep=clock.sleep, clock=clock.now,
            gate=RequestGate(),
        ).get(
            "https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json"
        )

    assert result.error == "timeout"
    assert len(result.attempts) == 3
    assert all(item.error == "timeout" for item in result.attempts)


def test_400_is_returned_without_a_retry(tmp_path):
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=b"bad request", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = HttpClient(
            Settings(data_dir=tmp_path), transport, sleep=clock.sleep, clock=clock.now,
            gate=RequestGate(),
        ).get(
            "https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json"
        )

    assert result.status == 400
    assert result.body == b"bad request"
    assert len(result.attempts) == 1


def test_long_retry_after_stops_without_retrying_early(tmp_path):
    clock = FakeClock()
    retry_after = format_datetime(clock.now() + timedelta(seconds=301), usegmt=True)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": retry_after}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = HttpClient(
            Settings(data_dir=tmp_path), transport, sleep=clock.sleep, clock=clock.now,
            gate=RequestGate(),
        ).get(
            "https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json"
        )

    assert result.error == "retry_after_pending"
    assert len(result.attempts) == 1
    assert clock.sleeps == []


def test_long_retry_after_on_the_final_attempt_is_recorded_as_pending(tmp_path):
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "301"}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        result = HttpClient(
            Settings(data_dir=tmp_path, attempts=1), transport, sleep=clock.sleep, clock=clock.now,
            gate=RequestGate(),
        ).get("https://itunes.apple.com/vn/rss/topfreeapplications/limit=100/genre=7003/json")

    assert result.error == "retry_after_pending"
    assert len(result.attempts) == 1


def test_default_clients_share_a_process_gate_for_serialized_request_starts(tmp_path):
    clock = FakeClock()
    first_started = Event()
    release_first = Event()
    second_entered = Event()
    request_times: list[datetime] = []

    def first_handler(request: httpx.Request) -> httpx.Response:
        request_times.append(clock.now())
        first_started.set()
        assert release_first.wait(timeout=1)
        return httpx.Response(200, request=request)

    def second_handler(request: httpx.Request) -> httpx.Response:
        request_times.append(clock.now())
        second_entered.set()
        return httpx.Response(200, request=request)

    settings = Settings(data_dir=tmp_path)
    with (
        httpx.Client(transport=httpx.MockTransport(first_handler)) as first_transport,
        httpx.Client(transport=httpx.MockTransport(second_handler)) as second_transport,
    ):
        first = HttpClient(settings, first_transport, sleep=clock.sleep, clock=clock.now)
        second = HttpClient(settings, second_transport, sleep=clock.sleep, clock=clock.now)
        first_thread = Thread(target=first.get, args=("https://itunes.apple.com/first",))
        second_thread = Thread(target=second.get, args=("https://itunes.apple.com/second",))
        first_thread.start()
        assert first_started.wait(timeout=1)
        second_thread.start()
        try:
            assert not second_entered.wait(timeout=0.1)
        finally:
            release_first.set()
            first_thread.join(timeout=1)
            second_thread.join(timeout=1)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert second_entered.is_set()
    assert request_times[1] - request_times[0] >= timedelta(seconds=4)
