import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from fra.adapters.data_sources.market.yfinance import YFinanceMarketDataAdapter
from fra.domain.market_data import HistoryRequest, InstrumentQuery
from fra.domain.sources import UsageProfile

NOW = datetime(2026, 7, 19, tzinfo=UTC)


def test_yfinance_fixture_is_adjusted_personal_use_fallback_with_durable_ids() -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def download(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return [
            {"Date": "2026-07-17", "Close": "620.10", "Volume": "50000000"},
            {"Date": "2026-07-18", "Close": "625.40", "Volume": "51000000"},
        ]

    async def scenario() -> None:
        adapter = YFinanceMarketDataAdapter(download=download, now=lambda: NOW)
        matches = await adapter.resolve_instrument(InstrumentQuery("SPY"))
        instrument = matches[0].instrument
        envelope = await adapter.history(
            HistoryRequest(
                instrument,
                datetime(2026, 7, 17, tzinfo=UTC),
                datetime(2026, 7, 18, tzinfo=UTC),
                "daily",
            )
        )
        assert instrument.id.value == "fund:us:SPY"
        assert envelope.value.observations[-1].price == Decimal("625.40")
        assert envelope.descriptor.allowed_usage_profiles == frozenset(
            {UsageProfile.LOCAL_PERSONAL_RESEARCH}
        )
        assert "personal use" in " ".join(envelope.warnings)
        assert calls[0][1]["auto_adjust"] is True
        assert calls[0][1]["multi_level_index"] is False
        assert envelope.request_fingerprint is not None

    asyncio.run(scenario())
