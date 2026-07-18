"""Read and explicitly check registered sources."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fra.application.results import failure_from_error
from fra.application.source_platform import RegisteredSource, SourceRegistry
from fra.domain.errors import FRAExpectedError, RepositoryNotFoundError
from fra.domain.shared import FailureKind, HealthState, HealthStatus
from fra.domain.sources import SourceRole, SourceStatusRecord
from fra.ports.repositories import SourceStatusRepository


@dataclass(frozen=True, slots=True)
class SourceSummary:
    provider_id: str
    roles: tuple[SourceRole, ...]
    authority: str
    health: str
    freshness: str
    quota_warning: str | None


@dataclass(frozen=True, slots=True)
class SourceDescription:
    provider_id: str
    adapter_version: str
    roles: tuple[SourceRole, ...]
    source_kinds: tuple[str, ...]
    authority: str
    point_in_time_support: bool
    allowed_usage_profiles: tuple[str, ...]
    raw_retention: str
    terms_url: str
    terms_reviewed_at: str
    credential_environment_names: tuple[str, ...]
    required_attribution: str | None


class SourceService:
    def __init__(
        self,
        registry: SourceRegistry,
        statuses: SourceStatusRepository,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._registry = registry
        self._statuses = statuses
        self._now = now

    def list(self) -> tuple[SourceSummary, ...]:
        persisted = {item.provider_id: item for item in self._statuses.list()}
        return tuple(
            self._summary(item, persisted.get(item.descriptor.provider_id))
            for item in self._registry.list()
        )

    def describe(self, provider_id: str) -> SourceDescription:
        source = self._registry.get(provider_id)
        descriptor = source.descriptor
        return SourceDescription(
            provider_id=descriptor.provider_id,
            adapter_version=descriptor.adapter_version,
            roles=source.roles,
            source_kinds=tuple(sorted(item.value for item in descriptor.source_kinds)),
            authority=descriptor.authority_class.value,
            point_in_time_support=descriptor.point_in_time_support,
            allowed_usage_profiles=tuple(
                sorted(item.value for item in descriptor.allowed_usage_profiles)
            ),
            raw_retention=descriptor.raw_retention.value,
            terms_url=descriptor.terms_url,
            terms_reviewed_at=descriptor.terms_reviewed_at.isoformat(),
            credential_environment_names=descriptor.credential_environment_names,
            required_attribution=descriptor.required_attribution,
        )

    async def check(self, provider_id: str | None = None) -> tuple[SourceStatusRecord, ...]:
        sources = (self._registry.get(provider_id),) if provider_id else self._registry.list()
        results: list[SourceStatusRecord] = []
        for source in sources:
            if source.adapter is None:
                raise RepositoryNotFoundError(
                    f"source adapter {source.descriptor.provider_id} is not constructed"
                )
            health_method = getattr(source.adapter, "health", None)
            if not callable(health_method):
                raise RepositoryNotFoundError(
                    f"source adapter {source.descriptor.provider_id} has no health check"
                )
            try:
                health = await health_method()
            except FRAExpectedError as error:
                failure = failure_from_error(error)
                health = HealthStatus(
                    HealthState.UNAVAILABLE,
                    self._now(),
                    failure.message,
                    failure=failure,
                )
            record = SourceStatusRecord(
                provider_id=source.descriptor.provider_id,
                checked_at=health.checked_at,
                health=health,
                roles=source.roles,
                capability_warnings=_capability_warnings(source),
                quota_warning=(
                    health.failure.message
                    if health.failure is not None
                    and health.failure.kind
                    in {FailureKind.QUOTA_EXCEEDED, FailureKind.RATE_LIMITED}
                    else None
                ),
            )
            self._statuses.save(record)
            results.append(record)
        return tuple(results)

    @staticmethod
    def _summary(source: RegisteredSource, status: SourceStatusRecord | None) -> SourceSummary:
        descriptor = source.descriptor
        return SourceSummary(
            provider_id=descriptor.provider_id,
            roles=source.roles,
            authority=descriptor.authority_class.value,
            health=status.health.state.value if status else "unknown",
            freshness=descriptor.normal_update_cadence or "unknown",
            quota_warning=status.quota_warning if status else None,
        )


def _capability_warnings(source: RegisteredSource) -> tuple[str, ...]:
    descriptor = source.descriptor
    capabilities = source.capabilities
    reported = getattr(capabilities, "point_in_time", None)
    if reported is None:
        reported = getattr(capabilities, "vintages", None)
    if descriptor.point_in_time_support and reported is False:
        return ("manifest declares point-in-time support but the typed capability does not",)
    return ()
