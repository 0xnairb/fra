import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.documents.manual import ManualDocument, ManualDocumentAdapter
from fra.adapters.data_sources.documents.rss_atom import RssAtomDocumentAdapter
from fra.adapters.data_sources.economic.world_bank import WorldBankIndicatorsAdapter
from fra.domain.documents import DocumentQuery
from fra.domain.economic import EconomicSeriesRequest

FIXTURES = Path(__file__).parents[2] / "fixtures" / "data_sources"
NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def test_manual_and_rss_document_ingestion_are_normalized_and_deterministic() -> None:
    rss = (FIXTURES / "rss.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://official.example/feed.xml":
            return httpx.Response(200, content=rss, headers={"content-type": "application/rss+xml"})
        return httpx.Response(
            200,
            text="Official statement body",
            headers={"content-type": "text/plain; charset=utf-8"},
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as raw_client:
            client = HttpClient(raw_client)
            manual = ManualDocumentAdapter(
                documents=(
                    ManualDocument(
                        provider_record_id="manual-001",
                        title="Official statement",
                        url="https://official.example/statement",
                        published_at=NOW - timedelta(hours=2),
                        updated_at=NOW - timedelta(hours=1),
                        corrects_provider_record_id="manual-000",
                    ),
                ),
                client=client,
                now=lambda: NOW,
            )
            feed = RssAtomDocumentAdapter(
                feed_url="https://official.example/feed.xml",
                client=client,
                now=lambda: NOW,
            )

            manual_refs = await manual.search(DocumentQuery("statement"))
            document = await manual.fetch(manual_refs.value[0])
            feed_refs = await feed.search(DocumentQuery("policy"))
            feed_document = await feed.fetch(feed_refs.value[0])

        assert document.value.content == "Official statement body"
        assert (
            document.content_hash
            == "sha256:ec5b7b12c096662be53851c4ceaee22e223028cc4c3d67c1e685ae801ffbcc9d"
        )
        assert document.request_fingerprint is not None
        assert document.revised_at == NOW - timedelta(hours=1)
        assert document.value.corrects_provider_record_id == "manual-000"
        assert feed_document.value.content == "The committee kept its policy rate unchanged."
        assert feed_document.available_at == datetime(2026, 7, 17, 8, 30, tzinfo=UTC)

    asyncio.run(scenario())


def test_world_bank_ingestion_follows_pagination_and_normalizes_periods() -> None:
    page_1 = json.loads((FIXTURES / "world_bank_page_1.json").read_text())
    page_2 = json.loads((FIXTURES / "world_bank_page_2.json").read_text())
    requested_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_pages.append(request.url.params["page"])
        return httpx.Response(200, json=page_1 if request.url.params["page"] == "1" else page_2)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as raw_client:
            adapter = WorldBankIndicatorsAdapter(HttpClient(raw_client), now=lambda: NOW)
            envelope = await adapter.observations(
                EconomicSeriesRequest(
                    series_id="NY.GDP.MKTP.CD",
                    geography="US",
                    start_period="2024",
                    end_period="2025",
                    page_size=1,
                )
            )

        assert requested_pages == ["1", "2"]
        assert [item.period for item in envelope.value.observations] == ["2024", "2025"]
        assert envelope.value.observations[0].value == 29000000000000
        assert envelope.units == "US$"
        assert envelope.available_at == NOW
        assert envelope.request_fingerprint is not None
        assert envelope.content_hash is not None

    asyncio.run(scenario())
