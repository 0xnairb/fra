import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from fra.adapters.data_sources.common.files import load_file
from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.documents.manual import ManualDocumentAdapter
from fra.adapters.data_sources.documents.opendart import OpenDartAdapter
from fra.adapters.data_sources.documents.rss_atom import RssAtomDocumentAdapter
from fra.adapters.data_sources.economic.world_bank import WorldBankIndicatorsAdapter
from fra.adapters.data_sources.market.coingecko import CoinGeckoMarketDataAdapter
from fra.domain.documents import DocumentQuery
from fra.domain.economic import EconomicSeriesRequest
from fra.domain.errors import (
    ExternalDataInvalidError,
    ExternalRateLimitedError,
    ExternalTimeoutError,
    PointInTimeUnavailableError,
    SourceQuotaExceededError,
)

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def test_all_built_in_wp3_adapters_publish_the_shared_manifest_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=transport) as raw_client:
            client = HttpClient(raw_client)
            adapters = (
                ManualDocumentAdapter(documents=(), client=client, now=lambda: NOW),
                RssAtomDocumentAdapter(
                    feed_url="https://official.example/feed.xml",
                    client=client,
                    now=lambda: NOW,
                ),
                WorldBankIndicatorsAdapter(client, now=lambda: NOW),
                CoinGeckoMarketDataAdapter(client, now=lambda: NOW),
                OpenDartAdapter(client, api_key="fixture-key", now=lambda: NOW),
            )
            provider_ids: set[str] = set()
            for adapter in adapters:
                descriptor = adapter.descriptor()
                assert descriptor.provider_id not in provider_ids
                provider_ids.add(descriptor.provider_id)
                assert descriptor.source_kinds
                assert descriptor.allowed_usage_profiles
                assert descriptor.terms_url.startswith("https://")
                assert descriptor.terms_reviewed_at.isoformat()
                assert adapter.capabilities() is not None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(429), ExternalRateLimitedError),
        (
            httpx.Response(429, headers={"x-quota-remaining": "0"}),
            SourceQuotaExceededError,
        ),
    ],
)
def test_shared_http_classifies_rate_and_quota_failures(
    response: httpx.Response, expected: type[Exception]
) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: response)
        ) as raw_client:
            with pytest.raises(expected):
                await HttpClient(raw_client).get("https://source.example/data")

    asyncio.run(scenario())


def test_shared_http_classifies_timeout_without_exposing_request_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("redacted", request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as raw_client:
            with pytest.raises(ExternalTimeoutError) as captured:
                await HttpClient(raw_client).get(
                    "https://source.example/data",
                    params={"api_key": "must-not-appear"},
                )
        assert "must-not-appear" not in str(captured.value)

    asyncio.run(scenario())


def test_world_bank_rejects_a_malformed_fixture_page() -> None:
    malformed = json.dumps({"not": "the documented page shape"}).encode()

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=malformed))
        ) as raw_client:
            adapter = WorldBankIndicatorsAdapter(HttpClient(raw_client), now=lambda: NOW)
            with pytest.raises(ExternalDataInvalidError, match="page schema"):
                await adapter.observations(
                    EconomicSeriesRequest("NY.GDP.MKTP.CD", "US", "2024", "2025")
                )

    asyncio.run(scenario())


def test_adapters_fail_closed_when_historical_contents_cannot_be_proven() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
        ) as raw_client:
            client = HttpClient(raw_client)
            feed = RssAtomDocumentAdapter(
                feed_url="https://official.example/feed.xml",
                client=client,
                now=lambda: NOW,
            )
            world_bank = WorldBankIndicatorsAdapter(client, now=lambda: NOW)
            with pytest.raises(PointInTimeUnavailableError):
                await feed.search(DocumentQuery("policy", point_in_time_at=NOW))
            with pytest.raises(PointInTimeUnavailableError):
                await world_bank.observations(
                    EconomicSeriesRequest(
                        "NY.GDP.MKTP.CD",
                        "US",
                        "2024",
                        "2025",
                        point_in_time_at=NOW,
                    )
                )

    asyncio.run(scenario())


def test_file_utility_hashes_content_and_fingerprints_the_resolved_path(tmp_path: Path) -> None:
    path = tmp_path / "release.txt"
    path.write_text("official release")

    loaded = load_file(path)

    assert loaded.content == b"official release"
    assert loaded.content_hash.startswith("sha256:")
    assert loaded.request_fingerprint.startswith("sha256:")
