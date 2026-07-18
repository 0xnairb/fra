import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import httpx
from openpyxl import Workbook

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.documents.sec_edgar import SECEdgarAdapter
from fra.adapters.data_sources.economic.eia import EIAEnergyAdapter
from fra.adapters.data_sources.economic.fred import FREDVintageAdapter
from fra.adapters.data_sources.economic.pink_sheet import WorldBankPinkSheetAdapter
from fra.domain.documents import DocumentQuery
from fra.domain.economic import EconomicSeriesRequest

FIXTURES = Path(__file__).parents[2] / "fixtures" / "data_sources"
NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)
CUTOFF = datetime(2022, 2, 24, 23, 59, tzinfo=UTC)


def test_eia_v2_normalizes_physical_inventory_and_uses_bounded_pagination() -> None:
    fixture = (FIXTURES / "eia_petroleum_stocks.json").read_bytes()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=fixture)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as raw:
            adapter = EIAEnergyAdapter(HttpClient(raw), api_key="fixture-key", now=lambda: NOW)
            result = await adapter.observations(
                EconomicSeriesRequest("WCESTUS1", "US", "2022-02-01", "2022-02-25", 50)
            )
        assert result.value.observations[-1].value == Decimal("413.4")
        assert result.units == "million barrels"
        assert requests[0].url.params["api_key"] == "fixture-key"
        assert requests[0].url.params["offset"] == "0"
        assert requests[0].url.params["length"] == "50"
        assert requests[0].url.params["facets[series][]"] == "WCESTUS1"

    asyncio.run(scenario())


def test_world_bank_pink_sheet_reads_monthly_benchmarks_and_units_from_workbook() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Monthly Prices"
    sheet.append(["World Bank Commodity Price Data"])
    sheet.append(["Date", "Crude oil, average", "DAP"])
    sheet.append(["Unit", "$/bbl", "$/mt"])
    sheet.append([datetime(2022, 1, 1), 85.53, 607.5])
    sheet.append([datetime(2022, 2, 1), 93.95, 747.1])
    content = BytesIO()
    workbook.save(content)
    workbook.close()

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=content.getvalue())
            )
        ) as raw:
            adapter = WorldBankPinkSheetAdapter(HttpClient(raw), now=lambda: NOW)
            result = await adapter.observations(
                EconomicSeriesRequest("Crude oil, average", "GLOBAL", "2022-01", "2022-02")
            )
        assert [item.value for item in result.value.observations] == [
            Decimal("85.53"),
            Decimal("93.95"),
        ]
        assert result.units == "$/bbl"
        assert result.descriptor.point_in_time_support is False

    asyncio.run(scenario())


def test_fred_alfred_pins_realtime_vintage_to_historical_cutoff() -> None:
    fixture = (FIXTURES / "fred_alfred_oil_vintage.json").read_bytes()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=fixture)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as raw:
            adapter = FREDVintageAdapter(HttpClient(raw), api_key="fixture-key", now=lambda: NOW)
            result = await adapter.observations(
                EconomicSeriesRequest(
                    "DCOILWTICO",
                    "US",
                    "2022-02-01",
                    "2022-02-24",
                    point_in_time_at=CUTOFF,
                )
            )
        assert result.value.observations[-1].value == Decimal("92.14")
        assert result.vintage == "2022-02-24"
        assert result.historical_cutoff_at == CUTOFF
        assert requests[0].url.params["realtime_start"] == "2022-02-24"
        assert requests[0].url.params["realtime_end"] == "2022-02-24"

    asyncio.run(scenario())


def test_sec_edgar_declares_identity_and_filters_filings_and_facts_by_cutoff() -> None:
    submissions = json.loads((FIXTURES / "sec_submissions.json").read_text())
    facts = json.loads((FIXTURES / "sec_companyfacts.json").read_text())
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = facts if "companyfacts" in request.url.path else submissions
        return httpx.Response(200, json=payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as raw:
            adapter = SECEdgarAdapter(
                HttpClient(raw),
                user_agent="Fixture Research fixture@example.com",
                now=lambda: NOW,
            )
            filings = await adapter.search(DocumentQuery("1657853", point_in_time_at=CUTOFF))
            selected = await adapter.selected_facts(
                "1657853", ("CostOfRevenue",), point_in_time_at=CUTOFF
            )
        assert filings.value[0].title.startswith("10-K")
        assert selected[0].value == Decimal("780000000")
        assert selected[0].filed_at.date().isoformat() == "2022-02-18"
        assert all(
            request.headers["user-agent"] == "Fixture Research fixture@example.com"
            for request in requests
        )
        assert requests[0].url.path.endswith("CIK0001657853.json")

    asyncio.run(scenario())
