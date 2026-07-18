import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.market.coingecko import CoinGeckoMarketDataAdapter
from fra.domain.ids import InstrumentId
from fra.domain.instruments import AssetClass, Currency, InstrumentRef, ProviderAlias
from fra.domain.market_data import HistoryRequest, InstrumentQuery

FIXTURES = Path(__file__).parents[2] / "fixtures" / "data_sources"
NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)


def test_coingecko_resolves_only_durable_coin_ids_and_normalizes_range_data() -> None:
    fixture = (FIXTURES / "coingecko_bitcoin_range.json").read_bytes()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=fixture, headers={"content-type": "application/json"})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as raw_client:
            adapter = CoinGeckoMarketDataAdapter(
                HttpClient(raw_client), api_key="demo-secret", now=lambda: NOW
            )
            matches = await adapter.resolve_instrument(InstrumentQuery("BTC"))
            instrument = matches[0].instrument
            envelope = await adapter.history(
                HistoryRequest(
                    instrument=instrument,
                    start_at=datetime(2026, 7, 15, tzinfo=UTC),
                    end_at=datetime(2026, 7, 19, tzinfo=UTC),
                    resolution="daily",
                )
            )

        assert instrument.id == InstrumentId("crypto:bitcoin")
        assert instrument.alias_for("coingecko") == "bitcoin"
        assert envelope.provider_subject_ids == ("bitcoin",)
        assert envelope.fra_subject_ids == (InstrumentId("crypto:bitcoin"),)
        assert envelope.required_attribution == "Data provided by CoinGecko"
        assert envelope.currency == "USD"
        assert len(envelope.value.observations) == 4
        assert envelope.value.observations[-1].price == Decimal("118.8")
        assert envelope.value.observations[-1].market_cap == Decimal("2376000000")
        assert envelope.value.observations[-1].volume == Decimal("140000000")
        assert requests[0].url.path.endswith("/coins/bitcoin/market_chart/range")
        assert requests[0].url.params["vs_currency"] == "usd"
        assert requests[0].url.params["from"] == "1784073600"
        assert requests[0].url.params["to"] == "1784419200"
        assert requests[0].headers["x-cg-demo-api-key"] == "demo-secret"
        assert "demo-secret" not in str(requests[0].url)
        assert envelope.request_fingerprint is not None
        assert envelope.content_hash is not None

    asyncio.run(scenario())


def test_coingecko_rejects_an_instrument_without_its_provider_coin_id() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        ) as raw_client:
            adapter = CoinGeckoMarketDataAdapter(HttpClient(raw_client), now=lambda: NOW)
            instrument = InstrumentRef(
                id=InstrumentId("crypto:unknown"),
                asset_class=AssetClass.CRYPTO,
                name="Unknown",
                currency=Currency("USD"),
                aliases=(ProviderAlias("other", "UNKNOWN"),),
            )
            try:
                await adapter.history(
                    HistoryRequest(
                        instrument,
                        datetime(2026, 7, 15, tzinfo=UTC),
                        NOW,
                        "daily",
                    )
                )
            except Exception as error:
                assert "CoinGecko coin ID" in str(error)
            else:
                raise AssertionError("missing CoinGecko coin ID should fail")

    asyncio.run(scenario())
