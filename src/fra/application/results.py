"""Typed application outcomes for expected domain and adapter failures."""

from __future__ import annotations

from dataclasses import dataclass

from fra.domain.errors import (
    AdapterUnavailableError,
    AuthenticationRequiredError,
    CapabilityUnavailableError,
    CapabilityUnsupportedError,
    DomainValidationError,
    ExternalDataInvalidError,
    ExternalRateLimitedError,
    ExternalTimeoutError,
    FRAExpectedError,
    InvalidStateTransitionError,
    LookAheadEvidenceError,
    PointInTimeUnavailableError,
    RepositoryConflictError,
    RepositoryCorruptError,
    RepositoryNotFoundError,
    ResearchIncompleteError,
    ResearchNeedsInputError,
    SourceQuotaExceededError,
    SourceTermsReviewExpiredError,
    StructuredOutputInvalidError,
    UsagePolicyViolationError,
)
from fra.domain.shared import Failure, FailureKind


@dataclass(frozen=True, slots=True)
class ApplicationResult[ResultT]:
    value: ResultT | None = None
    failure: Failure | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.failure is None):
            raise ValueError("application result requires exactly one of value or failure")

    @property
    def ok(self) -> bool:
        return self.failure is None

    @classmethod
    def success(cls, value: ResultT) -> ApplicationResult[ResultT]:
        return cls(value=value)

    @classmethod
    def failed(cls, failure: Failure) -> ApplicationResult[ResultT]:
        return cls(failure=failure)


def failure_from_error(error: FRAExpectedError) -> Failure:
    """Translate only expected FRA errors; programming errors remain visible."""
    mapping: tuple[tuple[type[FRAExpectedError], FailureKind, bool], ...] = (
        (LookAheadEvidenceError, FailureKind.LOOK_AHEAD_EVIDENCE, False),
        (InvalidStateTransitionError, FailureKind.INVALID_STATE_TRANSITION, False),
        (RepositoryConflictError, FailureKind.REPOSITORY_CONFLICT, False),
        (RepositoryNotFoundError, FailureKind.REPOSITORY_NOT_FOUND, False),
        (RepositoryCorruptError, FailureKind.REPOSITORY_CORRUPT, False),
        (AdapterUnavailableError, FailureKind.ADAPTER_UNAVAILABLE, True),
        (AuthenticationRequiredError, FailureKind.AUTHENTICATION_REQUIRED, False),
        (CapabilityUnsupportedError, FailureKind.CAPABILITY_UNSUPPORTED, False),
        (CapabilityUnavailableError, FailureKind.CAPABILITY_UNAVAILABLE, True),
        (ExternalRateLimitedError, FailureKind.RATE_LIMITED, True),
        (SourceQuotaExceededError, FailureKind.QUOTA_EXCEEDED, True),
        (ExternalTimeoutError, FailureKind.TIMEOUT, True),
        (ExternalDataInvalidError, FailureKind.EXTERNAL_DATA_INVALID, False),
        (UsagePolicyViolationError, FailureKind.USAGE_POLICY_VIOLATION, False),
        (PointInTimeUnavailableError, FailureKind.POINT_IN_TIME_UNAVAILABLE, False),
        (SourceTermsReviewExpiredError, FailureKind.TERMS_REVIEW_EXPIRED, False),
        (StructuredOutputInvalidError, FailureKind.STRUCTURED_OUTPUT_INVALID, False),
        (ResearchNeedsInputError, FailureKind.NEEDS_USER_INPUT, False),
        (ResearchIncompleteError, FailureKind.INCOMPLETE, False),
        (DomainValidationError, FailureKind.INVALID_VALUE, False),
    )
    for error_type, kind, retryable in mapping:
        if isinstance(error, error_type):
            return Failure(kind=kind, message=str(error), retryable=retryable)
    raise TypeError(f"unmapped expected error type: {type(error).__name__}")
