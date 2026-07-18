"""Fixture-backed normalized market-data adapter."""

from datetime import UTC, date, datetime

from fra.domain.errors import CapabilityUnavailableError
from fra.domain.instruments import InstrumentRef
from fra.domain.market_data import (
    HistoryRequest,
    InstrumentMatch,
    InstrumentQuery,
    MarketDataCapabilities,
    MarketQuote,
    MarketSeries,
)
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)
from fra.ports.market_data import MarketDataProvider


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        provider_id="fake_market",
        adapter_version="1.0.0",
        source_kinds=frozenset({SourceKind.MARKET_DATA}),
        authority_class=AuthorityClass.AGGREGATOR,
        point_in_time_support=True,
        allowed_usage_profiles=frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
        raw_retention=RawRetentionPolicy.PERMITTED,
        terms_url="https://example.test/fake-market/terms",
        terms_reviewed_at=date(2000, 1, 1),
        independence_group="fake-market",
    )


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        *,
        matches: tuple[InstrumentMatch, ...] = (),
        quotes: tuple[tuple[InstrumentRef, DataEnvelope[MarketQuote]], ...] = (),
        histories: tuple[tuple[InstrumentRef, DataEnvelope[MarketSeries]], ...] = (),
        now: datetime = datetime(2000, 1, 1, tzinfo=UTC),
    ) -> None:
        self._matches = matches
        self._quotes = {instrument.id: envelope for instrument, envelope in quotes}
        self._histories = {instrument.id: envelope for instrument, envelope in histories}
        self._now = now

    def descriptor(self) -> SourceDescriptor:
        return _descriptor()

    def capabilities(self) -> MarketDataCapabilities:
        return MarketDataCapabilities(quotes=True, history=True)

    async def health(self) -> HealthStatus:
        return HealthStatus(HealthState.HEALTHY, self._now, "fake market ready")

    async def resolve_instrument(self, query: InstrumentQuery) -> tuple[InstrumentMatch, ...]:
        text = query.text.casefold()
        matches = tuple(
            item
            for item in self._matches
            if text
            in {
                item.instrument.name.casefold(),
                (item.instrument.display_symbol or "").casefold(),
                *(alias.value.casefold() for alias in item.instrument.aliases),
            }
        )
        return matches

    async def quote(self, instrument: InstrumentRef) -> DataEnvelope[MarketQuote]:
        try:
            return self._quotes[instrument.id]
        except KeyError as error:
            raise CapabilityUnavailableError(f"no fake quote for {instrument.id}") from error

    async def history(self, request: HistoryRequest) -> DataEnvelope[MarketSeries]:
        try:
            return self._histories[request.instrument.id]
        except KeyError as error:
            raise CapabilityUnavailableError(
                f"no fake history for {request.instrument.id}"
            ) from error
