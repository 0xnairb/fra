"""Common source policy and normalized provenance models."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from fra.domain.errors import DomainValidationError, LookAheadEvidenceError
from fra.domain.ids import InstrumentId
from fra.domain.time import as_utc


class SourceKind(StrEnum):
    MARKET_DATA = "market_data"
    DOCUMENT = "document"


class DataKind(StrEnum):
    MARKET_QUOTE = "market_quote"
    MARKET_SERIES = "market_series"
    DOCUMENT = "document"


class AuthorityClass(StrEnum):
    OFFICIAL = "official"
    REGULATED = "regulated"
    PRIMARY = "primary"
    AGGREGATOR = "aggregator"
    SECONDARY = "secondary"
    DISCOVERY = "discovery"


class UsageProfile(StrEnum):
    LOCAL_PERSONAL_RESEARCH = "local_personal_research"
    INTERNAL_RESEARCH = "internal_research"
    COMMERCIAL = "commercial"


class RawRetentionPolicy(StrEnum):
    PROHIBITED = "prohibited"
    METADATA_ONLY = "metadata_only"
    PERMITTED = "permitted"


class AuthenticationKind(StrEnum):
    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    CLI_MANAGED = "cli_managed"


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    """Machine-readable capability, policy, and operational source metadata."""

    provider_id: str
    adapter_version: str
    source_kinds: frozenset[SourceKind]
    authority_class: AuthorityClass
    point_in_time_support: bool
    allowed_usage_profiles: frozenset[UsageProfile]
    raw_retention: RawRetentionPolicy
    terms_url: str
    terms_reviewed_at: date
    independence_group: str
    geographies: frozenset[str] = frozenset()
    markets: frozenset[str] = frozenset()
    frequencies: frozenset[str] = frozenset()
    history_start: date | None = None
    authentication_kind: AuthenticationKind = AuthenticationKind.NONE
    credential_environment_names: tuple[str, ...] = ()
    quota_description: str | None = None
    normal_update_cadence: str | None = None
    required_attribution: str | None = None
    experimental: bool = False
    discovery_only: bool = False

    def __post_init__(self) -> None:
        required = {
            "provider_id": self.provider_id,
            "adapter_version": self.adapter_version,
            "terms_url": self.terms_url,
            "independence_group": self.independence_group,
        }
        for field, value in required.items():
            if not value.strip():
                raise DomainValidationError(f"source descriptor {field} must not be empty")
        if not self.source_kinds:
            raise DomainValidationError("source descriptor requires at least one source kind")
        if not self.allowed_usage_profiles:
            raise DomainValidationError("unknown source usage rights fail closed")


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    """Provider-neutral statement of evidence needed by a workflow."""

    data_kind: DataKind
    subject_ids: tuple[InstrumentId, ...]
    allowed_usage_profile: UsageProfile
    fields: tuple[str, ...] = ()
    units: tuple[str, ...] = ()
    geography_or_market: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    resolution: str | None = None
    maximum_age: timedelta | None = None
    point_in_time_at: datetime | None = None
    minimum_authority: AuthorityClass = AuthorityClass.SECONDARY
    minimum_independent_sources: int = 1
    raw_retention_required: bool = False

    def __post_init__(self) -> None:
        for field in ("start_at", "end_at", "point_in_time_at"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, as_utc(value, field=field))
        if self.start_at and self.end_at and self.start_at > self.end_at:
            raise DomainValidationError("evidence requirement start_at must not follow end_at")
        if self.maximum_age is not None and self.maximum_age <= timedelta(0):
            raise DomainValidationError("maximum_age must be positive")
        if self.minimum_independent_sources < 1:
            raise DomainValidationError("minimum_independent_sources must be positive")


@dataclass(frozen=True, slots=True)
class DataEnvelope[ValueT]:
    """An FRA-owned normalized value plus complete provenance metadata."""

    value: ValueT
    descriptor: SourceDescriptor
    provider_record_id: str
    source: str
    available_at: datetime
    retrieved_at: datetime
    historical_cutoff_at: datetime | None = None
    provider_subject_ids: tuple[str, ...] = ()
    fra_subject_ids: tuple[InstrumentId, ...] = ()
    observed_at: datetime | None = None
    event_time: datetime | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    published_at: datetime | None = None
    effective_at: datetime | None = None
    revised_at: datetime | None = None
    vintage: str | None = None
    timezone: str | None = None
    currency: str | None = None
    units: str | None = None
    classification_version: str | None = None
    is_stale: bool = False
    is_delayed: bool = False
    content_hash: str | None = None
    request_fingerprint: str | None = None
    usage_policy_id: str | None = None
    required_attribution: str | None = None
    warnings: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider_record_id.strip() or not self.source.strip():
            raise DomainValidationError("data provenance requires provider record and source")
        time_fields = (
            "available_at",
            "retrieved_at",
            "historical_cutoff_at",
            "observed_at",
            "event_time",
            "period_start",
            "period_end",
            "published_at",
            "effective_at",
            "revised_at",
        )
        for field in time_fields:
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, as_utc(value, field=field))
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise DomainValidationError("period_start must not follow period_end")
        if self.historical_cutoff_at and self.available_at > self.historical_cutoff_at:
            raise LookAheadEvidenceError(
                "available_at cannot occur after the historical evidence cutoff"
            )
