from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock
from time import sleep as real_sleep

import httpx

from casual_scout.config import Settings
from casual_scout.models import HttpResult

Clock = Callable[[], datetime]
ObservationCallback = Callable[[HttpResult], None]


@dataclass
class RequestGate:
    """Serialize Apple request starts and retain the last start in one process."""

    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _last_started_at: datetime | None = field(default=None, init=False, repr=False)

    @contextmanager
    def request_slot(
        self,
        request_interval: float,
        clock: Clock,
        sleep: Callable[[float], None],
    ):
        with self._lock:
            if self._last_started_at is not None:
                elapsed = (clock() - self._last_started_at).total_seconds()
                delay = request_interval - elapsed
                if delay > 0:
                    sleep(delay)
            started_at = clock()
            self._last_started_at = started_at
            yield started_at


_DEFAULT_APPLE_REQUEST_GATE = RequestGate()


class HttpClient:
    """Synchronous Apple HTTP client with a shared request-start interval."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = real_sleep,
        clock: Clock | None = None,
        on_observation: ObservationCallback | None = None,
        gate: RequestGate | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.timeout)
        self._sleep = sleep
        self._clock = clock or (lambda: datetime.now(UTC))
        self._on_observation = on_observation
        self._gate = gate or _DEFAULT_APPLE_REQUEST_GATE

    def get(self, url: str) -> HttpResult:
        observations: list[HttpResult] = []
        for attempt_index in range(self._settings.attempts):
            result = self._request(url)
            observations.append(result)
            if self._on_observation is not None:
                self._on_observation(result)

            retryable = self._is_retryable(result)
            retry_after = self._retry_after_seconds(result) if retryable else None
            if retry_after is not None and retry_after > 300:
                return replace(
                    result,
                    error="retry_after_pending",
                    attempts=tuple(observations),
                )
            if not retryable or attempt_index == self._settings.attempts - 1:
                return replace(result, attempts=tuple(observations))
            backoff_seconds = min(60.0, 2.0**attempt_index)
            self._sleep(max(backoff_seconds, retry_after or 0.0))

        raise RuntimeError("settings.attempts must be positive")

    def _request(self, url: str) -> HttpResult:
        with self._gate.request_slot(
            self._settings.request_interval, self._clock, self._sleep
        ) as started_at:
            try:
                response = self._client.get(url, timeout=self._settings.timeout)
            except httpx.TimeoutException:
                return HttpResult(
                    url=url,
                    started_at=started_at,
                    elapsed_ms=self._elapsed_ms(started_at),
                    status=None,
                    body=None,
                    headers={},
                    error="timeout",
                )
            except httpx.HTTPError as error:
                return HttpResult(
                    url=url,
                    started_at=started_at,
                    elapsed_ms=self._elapsed_ms(started_at),
                    status=None,
                    body=None,
                    headers={},
                    error=f"http_error: {error}",
                )

            return HttpResult(
                url=url,
                started_at=started_at,
                elapsed_ms=self._elapsed_ms(started_at),
                status=response.status_code,
                body=response.content,
                headers=dict(response.headers),
                error=None,
            )

    def _elapsed_ms(self, started_at: datetime) -> int:
        return max(0, int((self._clock() - started_at).total_seconds() * 1000))

    @staticmethod
    def _is_retryable(result: HttpResult) -> bool:
        return result.status in {429, 500, 502, 503, 504} or result.error == "timeout"

    def _retry_after_seconds(self, result: HttpResult) -> float | None:
        value = result.headers.get("retry-after") or result.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - self._clock()).total_seconds())
