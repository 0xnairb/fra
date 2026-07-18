"""Shared boundary values that contain no vendor or transport details."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath

from fra.domain.errors import DomainValidationError
from fra.domain.time import as_utc


class ArtifactKind(StrEnum):
    RESEARCH_RUN = "research_run"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    SIGNAL = "signal"
    REPORT = "report"
    SOURCE_STATUS = "source_status"
    SOURCE_CACHE = "source_cache"
    CALCULATION = "calculation"
    FORECAST = "forecast"
    OUTCOME = "outcome"
    EXPOSURE_GRAPH = "exposure_graph"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Stable workspace-relative reference; not a filesystem object."""

    kind: ArtifactKind
    location: str

    def __post_init__(self) -> None:
        path = PurePosixPath(self.location)
        if path.is_absolute() or not self.location or ".." in path.parts:
            raise DomainValidationError("artifact location must be a contained relative path")
        normalized = path.as_posix()
        if normalized in {".", ""}:
            raise DomainValidationError("artifact location must identify an artifact")
        object.__setattr__(self, "location", normalized)


class FailureKind(StrEnum):
    INVALID_VALUE = "invalid_value"
    INVALID_STATE_TRANSITION = "invalid_state_transition"
    LOOK_AHEAD_EVIDENCE = "look_ahead_evidence"
    REPOSITORY_CONFLICT = "repository_conflict"
    REPOSITORY_NOT_FOUND = "repository_not_found"
    REPOSITORY_CORRUPT = "repository_corrupt"
    ADAPTER_UNAVAILABLE = "adapter_unavailable"
    AUTHENTICATION_REQUIRED = "authentication_required"
    CAPABILITY_UNSUPPORTED = "capability_unsupported"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    TIMEOUT = "timeout"
    EXTERNAL_DATA_INVALID = "external_data_invalid"
    USAGE_POLICY_VIOLATION = "usage_policy_violation"
    POINT_IN_TIME_UNAVAILABLE = "point_in_time_unavailable"
    TERMS_REVIEW_EXPIRED = "terms_review_expired"
    STRUCTURED_OUTPUT_INVALID = "structured_output_invalid"
    CANCELLED = "cancelled"
    NEEDS_USER_INPUT = "needs_user_input"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class Failure:
    """A typed expected failure safe to return across application boundaries."""

    kind: FailureKind
    message: str
    retryable: bool = False
    provider_id: str | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise DomainValidationError("failure message must not be empty")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise DomainValidationError("retry_after_seconds must not be negative")


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HealthStatus:
    state: HealthState
    checked_at: datetime
    summary: str
    failure: Failure | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", as_utc(self.checked_at, field="checked_at"))
        if not self.summary.strip():
            raise DomainValidationError("health summary must not be empty")
        if self.state is HealthState.HEALTHY and self.failure is not None:
            raise DomainValidationError("healthy status cannot carry a failure")

    @property
    def ok(self) -> bool:
        return self.state is HealthState.HEALTHY
