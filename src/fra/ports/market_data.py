"""Normalized market-data capability port."""

from typing import Protocol

from fra.domain.instruments import InstrumentRef
from fra.domain.market_data import (
    HistoryRequest,
    InstrumentMatch,
    InstrumentQuery,
    MarketDataCapabilities,
    MarketQuote,
    MarketSeries,
)
from fra.domain.shared import HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor


class MarketDataProvider(Protocol):
    def descriptor(self) -> SourceDescriptor: ...

    def capabilities(self) -> MarketDataCapabilities: ...

    async def health(self) -> HealthStatus: ...

    async def resolve_instrument(self, query: InstrumentQuery) -> tuple[InstrumentMatch, ...]: ...

    async def quote(self, instrument: InstrumentRef) -> DataEnvelope[MarketQuote]: ...

    async def history(self, request: HistoryRequest) -> DataEnvelope[MarketSeries]: ...
