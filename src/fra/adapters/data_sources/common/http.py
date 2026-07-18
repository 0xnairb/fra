"""Shared bounded HTTP transport for source adapters."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from fra.domain.errors import (
    AdapterUnavailableError,
    AuthenticationRequiredError,
    ExternalDataInvalidError,
    ExternalRateLimitedError,
    ExternalTimeoutError,
    SourceQuotaExceededError,
)


def content_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def request_fingerprint(method: str, url: str, params: dict[str, str | int] | None = None) -> str:
    normalized = json.dumps(
        {
            "method": method.upper(),
            "url": url,
            "params": sorted((str(key), str(value)) for key, value in (params or {}).items()),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return content_hash(normalized)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    body: bytes
    content_type: str | None
    content_hash: str
    request_fingerprint: str
    headers: dict[str, str]

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExternalDataInvalidError("source returned malformed JSON") from error


class AsyncRateLimiter:
    """Small per-client limiter that never blocks a thread."""

    def __init__(self, requests_per_second: float) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self._interval = 1 / requests_per_second
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._interval - (now - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()


class HttpClient:
    """Wrap one lifecycle-managed HTTPX client and normalize transport failures."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        rate_limiter: AsyncRateLimiter | None = None,
    ) -> None:
        self._client = client
        self._rate_limiter = rate_limiter

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        fingerprint = request_fingerprint("GET", url, params)
        try:
            response = await self._client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as error:
            raise ExternalTimeoutError(f"source request timed out: {url}") from error
        except httpx.TransportError as error:
            raise AdapterUnavailableError(f"source transport unavailable: {url}") from error
        if response.status_code == 401 or response.status_code == 403:
            raise AuthenticationRequiredError("source authentication is required")
        if response.status_code == 429:
            if response.headers.get("x-quota-remaining") == "0":
                raise SourceQuotaExceededError("source quota is exhausted")
            raise ExternalRateLimitedError("source rate limit reached")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise AdapterUnavailableError(f"source returned HTTP {response.status_code}") from error
        body = response.content
        return HttpResponse(
            body=body,
            content_type=response.headers.get("content-type"),
            content_hash=content_hash(body),
            request_fingerprint=fingerprint,
            headers=dict(response.headers),
        )


def create_async_client() -> httpx.AsyncClient:
    """Create the single bounded client owned and closed by bootstrap."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        follow_redirects=True,
    )
