"""Capability registry and policy-bound source routing."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fra.domain.documents import DocumentCapabilities
from fra.domain.economic import EconomicSeriesCapabilities
from fra.domain.errors import (
    CapabilityUnavailableError,
    DomainValidationError,
    FRAExpectedError,
    RepositoryNotFoundError,
)
from fra.domain.market_data import MarketDataCapabilities
from fra.domain.shared import FailureKind, HealthState
from fra.domain.sources import (
    AuthorityClass,
    DataKind,
    EvidenceRequirement,
    RawRetentionPolicy,
    RoutingCandidate,
    RoutingDecision,
    SourceDescriptor,
    SourceKind,
    SourceRole,
)
from fra.ports.repositories import SourceStatusRepository


@dataclass(frozen=True, slots=True)
class RegisteredSource:
    descriptor: SourceDescriptor
    capabilities: object
    roles: tuple[SourceRole, ...]
    adapter: object | None = None


@dataclass(frozen=True, slots=True)
class RoutedValue[ValueT]:
    provider_id: str
    role: SourceRole
    value: ValueT


@dataclass(frozen=True, slots=True)
class RoutedFailure:
    provider_id: str
    role: SourceRole
    message: str


@dataclass(frozen=True, slots=True)
class RoutingExecution[ValueT]:
    decision: RoutingDecision
    values: tuple[RoutedValue[ValueT], ...]
    failures: tuple[RoutedFailure, ...] = ()


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, RegisteredSource] = {}

    def register(self, adapter: object, *, roles: tuple[SourceRole, ...]) -> None:
        descriptor_method = getattr(adapter, "descriptor", None)
        capabilities_method = getattr(adapter, "capabilities", None)
        if not callable(descriptor_method) or not callable(capabilities_method):
            raise DomainValidationError("source adapter must expose descriptor and capabilities")
        self.register_descriptor(
            descriptor_method(),
            capabilities=capabilities_method(),
            roles=roles,
            adapter=adapter,
        )

    def register_descriptor(
        self,
        descriptor: SourceDescriptor,
        *,
        capabilities: object,
        roles: tuple[SourceRole, ...],
        adapter: object | None = None,
    ) -> None:
        if descriptor.provider_id in self._sources:
            raise DomainValidationError(f"duplicate source provider ID: {descriptor.provider_id}")
        if not roles:
            raise DomainValidationError("registered source requires at least one routing role")
        expected_capabilities = {
            SourceKind.DOCUMENT: DocumentCapabilities,
            SourceKind.ECONOMIC_SERIES: EconomicSeriesCapabilities,
            SourceKind.MARKET_DATA: MarketDataCapabilities,
        }
        for kind in descriptor.source_kinds:
            if not isinstance(capabilities, expected_capabilities[kind]):
                raise DomainValidationError(
                    f"source {descriptor.provider_id} does not expose its declared "
                    f"{kind.value} capability"
                )
        self._sources[descriptor.provider_id] = RegisteredSource(
            descriptor=descriptor,
            capabilities=capabilities,
            roles=roles,
            adapter=adapter,
        )

    def list(self) -> tuple[RegisteredSource, ...]:
        return tuple(self._sources[key] for key in sorted(self._sources))

    def get(self, provider_id: str) -> RegisteredSource:
        try:
            return self._sources[provider_id]
        except KeyError as error:
            raise RepositoryNotFoundError(f"unknown source provider: {provider_id}") from error


_AUTHORITY = {
    AuthorityClass.DISCOVERY: 0,
    AuthorityClass.SECONDARY: 1,
    AuthorityClass.AGGREGATOR: 2,
    AuthorityClass.PRIMARY: 3,
    AuthorityClass.REGULATED: 4,
    AuthorityClass.OFFICIAL: 5,
}


class SourceRouter:
    def __init__(
        self,
        registry: SourceRegistry,
        *,
        policy_version: str,
        statuses: SourceStatusRepository | None = None,
    ) -> None:
        self._registry = registry
        self._policy_version = policy_version
        self._statuses = statuses

    def route(self, requirement: EvidenceRequirement) -> RoutingDecision:
        eligible: list[RegisteredSource] = []
        candidates: list[RoutingCandidate] = []
        statuses = (
            {item.provider_id: item for item in self._statuses.list()}
            if self._statuses is not None
            else {}
        )
        required_kind = _source_kind(requirement.data_kind)
        for registered in self._registry.list():
            descriptor = registered.descriptor
            exclusions: list[str] = []
            if required_kind not in descriptor.source_kinds:
                exclusions.append("capability_unsupported")
            if requirement.allowed_usage_profile not in descriptor.allowed_usage_profiles:
                exclusions.append("usage_profile_incompatible")
            if (
                requirement.raw_retention_required
                and descriptor.raw_retention is not RawRetentionPolicy.PERMITTED
            ):
                exclusions.append("raw_retention_incompatible")
            if requirement.point_in_time_at is not None and not descriptor.point_in_time_support:
                exclusions.append("point_in_time_unavailable")
            if _AUTHORITY[descriptor.authority_class] < _AUTHORITY[requirement.minimum_authority]:
                exclusions.append("authority_insufficient")
            scope = requirement.geography_or_market
            supported_scopes = descriptor.geographies | descriptor.markets
            if (
                scope
                and supported_scopes
                and scope not in supported_scopes
                and "GLOBAL" not in supported_scopes
            ):
                exclusions.append("scope_unsupported")
            if (
                requirement.resolution
                and descriptor.frequencies
                and requirement.resolution not in descriptor.frequencies
            ):
                exclusions.append("resolution_unsupported")
            if (
                requirement.start_at is not None
                and descriptor.history_start is not None
                and requirement.start_at.date() < descriptor.history_start
            ):
                exclusions.append("history_insufficient")
            if (
                requirement.maximum_age is not None
                and descriptor.maximum_expected_age is not None
                and descriptor.maximum_expected_age > requirement.maximum_age
            ):
                exclusions.append("freshness_insufficient")
            if (
                requirement.fields
                and descriptor.fields
                and not set(requirement.fields) <= descriptor.fields
            ):
                exclusions.append("fields_unsupported")
            status = statuses.get(descriptor.provider_id)
            if status is not None:
                if (
                    status.health.failure is not None
                    and status.health.failure.kind is FailureKind.QUOTA_EXCEEDED
                ):
                    exclusions.append("quota_unavailable")
                elif status.health.state is HealthState.UNAVAILABLE:
                    exclusions.append("health_unavailable")
            if exclusions:
                candidates.append(
                    RoutingCandidate(descriptor.provider_id, exclusions=tuple(exclusions))
                )
            else:
                eligible.append(registered)

        eligible.sort(
            key=lambda item: (
                -_AUTHORITY[item.descriptor.authority_class],
                item.descriptor.provider_id,
            )
        )
        selected_groups: set[str] = set()
        for index, registered in enumerate(eligible):
            role = _role_for(registered, index, selected_groups)
            if role is None:
                candidates.append(
                    RoutingCandidate(
                        registered.descriptor.provider_id,
                        exclusions=("not_selected_by_policy",),
                    )
                )
                continue
            selected_groups.add(registered.descriptor.independence_group)
            candidates.append(RoutingCandidate(registered.descriptor.provider_id, role))
        candidates.sort(key=lambda item: item.provider_id)
        independent_groups = {
            source.descriptor.independence_group
            for source in eligible
            if not source.descriptor.discovery_only
        }
        warnings: tuple[str, ...] = ()
        if len(independent_groups) < requirement.minimum_independent_sources:
            warnings = (
                f"minimum independent sources unmet: required "
                f"{requirement.minimum_independent_sources}, found {len(independent_groups)}",
            )
        return RoutingDecision(
            requirement,
            self._policy_version,
            tuple(candidates),
            warnings=warnings,
        )

    async def execute[ValueT](
        self,
        requirement: EvidenceRequirement,
        operation: Callable[[object], Awaitable[ValueT]],
    ) -> RoutingExecution[ValueT]:
        """Execute only policy-selected adapters, with bounded fallback semantics."""
        decision = self.route(requirement)
        selected = sorted(decision.selected, key=lambda item: _execution_order(item.selected_role))
        regular = tuple(item for item in selected if item.selected_role is not SourceRole.FALLBACK)
        fallbacks = tuple(item for item in selected if item.selected_role is SourceRole.FALLBACK)
        values: list[RoutedValue[ValueT]] = []
        failures: list[RoutedFailure] = []
        errors: list[FRAExpectedError] = []

        for candidate in regular:
            await self._execute_candidate(candidate, operation, values, failures, errors)

        primary_succeeded = any(item.role is SourceRole.PRIMARY for item in values)
        if not primary_succeeded:
            for candidate in fallbacks:
                value_count = len(values)
                await self._execute_candidate(candidate, operation, values, failures, errors)
                if len(values) > value_count:
                    break

        if not values:
            if errors:
                raise errors[0]
            detail = (
                "; ".join(f"{item.provider_id}: {item.message}" for item in failures)
                or "no policy-compatible source was selected"
            )
            raise CapabilityUnavailableError(f"source routing produced no evidence: {detail}")
        return RoutingExecution(decision, tuple(values), tuple(failures))

    async def _execute_candidate[ValueT](
        self,
        candidate: RoutingCandidate,
        operation: Callable[[object], Awaitable[ValueT]],
        values: list[RoutedValue[ValueT]],
        failures: list[RoutedFailure],
        errors: list[FRAExpectedError],
    ) -> None:
        role = candidate.selected_role
        if role is None:
            raise DomainValidationError("cannot execute a policy-excluded source")
        adapter = self._registry.get(candidate.provider_id).adapter
        if adapter is None:
            failures.append(
                RoutedFailure(candidate.provider_id, role, "source adapter is not constructed")
            )
            return
        try:
            value = await operation(adapter)
        except FRAExpectedError as error:
            failures.append(RoutedFailure(candidate.provider_id, role, str(error)))
            errors.append(error)
            return
        values.append(RoutedValue(candidate.provider_id, role, value))


def _source_kind(data_kind: DataKind) -> SourceKind:
    if data_kind in {DataKind.MARKET_QUOTE, DataKind.MARKET_SERIES}:
        return SourceKind.MARKET_DATA
    if data_kind is DataKind.DOCUMENT:
        return SourceKind.DOCUMENT
    return SourceKind.ECONOMIC_SERIES


def _role_for(source: RegisteredSource, index: int, selected_groups: set[str]) -> SourceRole | None:
    if source.descriptor.discovery_only or SourceRole.DISCOVERY in source.roles:
        return SourceRole.DISCOVERY
    if index == 0 and SourceRole.PRIMARY in source.roles:
        return SourceRole.PRIMARY
    if (
        source.descriptor.independence_group not in selected_groups
        and SourceRole.CROSS_CHECK in source.roles
    ):
        return SourceRole.CROSS_CHECK
    if SourceRole.FALLBACK in source.roles:
        return SourceRole.FALLBACK
    return None


def _execution_order(role: SourceRole | None) -> int:
    return {
        SourceRole.PRIMARY: 0,
        SourceRole.CROSS_CHECK: 1,
        SourceRole.DISCOVERY: 2,
        SourceRole.FALLBACK: 3,
        None: 4,
    }[role]
