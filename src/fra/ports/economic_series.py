"""Normalized economic-series capability port."""

from typing import Protocol

from fra.domain.economic import EconomicSeries, EconomicSeriesCapabilities, EconomicSeriesRequest
from fra.domain.shared import HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor


class EconomicSeriesProvider(Protocol):
    def descriptor(self) -> SourceDescriptor: ...

    def capabilities(self) -> EconomicSeriesCapabilities: ...

    async def health(self) -> HealthStatus: ...

    async def observations(
        self, request: EconomicSeriesRequest
    ) -> DataEnvelope[EconomicSeries]: ...
