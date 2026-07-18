import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.documents.opendart import OpenDartAdapter
from fra.domain.documents import DocumentQuery
from fra.domain.errors import ExternalDataInvalidError, SourceQuotaExceededError

FIXTURE = Path(__file__).parents[2] / "fixtures/data_sources/opendart_disclosures.json"
NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)


def test_opendart_normalizes_korean_disclosures_and_enforces_cutoff() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=FIXTURE.read_bytes())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as raw:
            adapter = OpenDartAdapter(HttpClient(raw), api_key="fixture-key", now=lambda: NOW)
            result = await adapter.search(DocumentQuery("00126380", point_in_time_at=NOW))
        assert [item.provider_record_id for item in result.value] == ["20260318001234"]
        assert result.provider_subject_ids == ("00126380",)
        assert result.descriptor.geographies == frozenset({"KR"})
        assert requests[0].url.params["end_de"] == "20260719"
        assert requests[0].url.params["page_count"] == "100"

    asyncio.run(scenario())


def test_opendart_rejects_bad_identifiers_and_types_quota_status() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"status": "020", "message": "Call limit exceeded"}
                )
            )
        ) as raw:
            adapter = OpenDartAdapter(HttpClient(raw), api_key="fixture-key", now=lambda: NOW)
            with pytest.raises(ExternalDataInvalidError, match="eight digits"):
                await adapter.search(DocumentQuery("005930"))
            with pytest.raises(SourceQuotaExceededError):
                await adapter.search(DocumentQuery("00126380"))

    asyncio.run(scenario())
