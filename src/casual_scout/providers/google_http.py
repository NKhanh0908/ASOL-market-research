"""HTTP transport for Google Play with retries, timeout, and evidence preservation."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Self

import httpx

from casual_scout.models import HttpResult

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
BACKOFF_DELAYS = (1, 2, 4)
DEFAULT_TIMEOUT = 15.0


class GoogleHttpClient:
    """Client for Google Play HTTP operations with bounded retries and attempt tracing."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._owned_client = client is None
        self.client = client or httpx.Client(
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self.sleep = sleep
        self.clock = clock

    def close(self) -> None:
        if self._owned_client:
            self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get(self, url: str, headers: dict[str, str] | None = None) -> HttpResult:
        return self._request("GET", url, content=None, headers=headers)

    def post(
        self,
        url: str,
        content: bytes | str | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResult:
        return self._request("POST", url, content=content, headers=headers)

    def _request(
        self,
        method: str,
        url: str,
        content: bytes | str | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResult:
        previous: list[HttpResult] = []

        index = 0
        while True:
            if index > 0:
                self.sleep(BACKOFF_DELAYS[index - 1])

            started = self.clock()
            tick = time.monotonic()

            try:
                if method == "POST":
                    response = self.client.post(
                        url, content=content, headers=headers, timeout=DEFAULT_TIMEOUT
                    )
                else:
                    response = self.client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
                status = response.status_code
                body = response.content
                resp_headers = dict(response.headers)
                error = None if 200 <= status < 300 else f"HTTP {status}"
                retryable = status in RETRYABLE_STATUS_CODES
            except httpx.TransportError as exc:
                status, body, resp_headers = None, None, {}
                error = str(exc)
                retryable = True

            elapsed_ms = int((time.monotonic() - tick) * 1000)
            item = HttpResult(
                url=url,
                started_at=started,
                elapsed_ms=elapsed_ms,
                status=status,
                body=body,
                headers=resp_headers,
                error=error,
            )

            if not retryable or index == 3:
                return dataclasses.replace(item, attempts=tuple(previous))

            previous.append(item)
            index += 1
