"""Fixture-backed economic-series adapter."""

from datetime import UTC, date, datetime

from fra.domain.economic import EconomicSeries, EconomicSeriesCapabilities, EconomicSeriesRequest
from fra.domain.errors import CapabilityUnavailableError
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)
from fra.ports.economic_series import EconomicSeriesProvider


class FakeEconomicSeriesProvider(EconomicSeriesProvider):
    def __init__(
        self,
        *,
        series: tuple[tuple[str, DataEnvelope[EconomicSeries]], ...] = (),
        now: datetime = datetime(2000, 1, 1, tzinfo=UTC),
    ) -> None:
        self._series = dict(series)
        self._now = now

    def descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            provider_id="fake_economic_series",
            adapter_version="1.0.0",
            source_kinds=frozenset({SourceKind.ECONOMIC_SERIES}),
            authority_class=AuthorityClass.OFFICIAL,
            point_in_time_support=True,
            allowed_usage_profiles=frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
            raw_retention=RawRetentionPolicy.PERMITTED,
            terms_url="https://example.test/fake-economic/terms",
            terms_reviewed_at=date(2000, 1, 1),
            independence_group="fake-economic",
        )

    def capabilities(self) -> EconomicSeriesCapabilities:
        return EconomicSeriesCapabilities(observations=True, vintages=True)

    async def health(self) -> HealthStatus:
        return HealthStatus(HealthState.HEALTHY, self._now, "fake economic series ready")

    async def observations(self, request: EconomicSeriesRequest) -> DataEnvelope[EconomicSeries]:
        try:
            return self._series[request.series_id]
        except KeyError as error:
            raise CapabilityUnavailableError(
                f"no fake economic series {request.series_id}"
            ) from error
