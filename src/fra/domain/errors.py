"""Expected domain and boundary failures owned by FRA."""


class FRAExpectedError(Exception):
    """Base class for failures callers may handle without treating them as bugs."""


class DomainValidationError(FRAExpectedError, ValueError):
    """A domain value violates a declared invariant."""


class InvalidStateTransitionError(FRAExpectedError):
    """A research run cannot move between the requested states."""


class LookAheadEvidenceError(DomainValidationError):
    """Evidence was not available by a declared historical cutoff."""


class RepositoryError(FRAExpectedError):
    """Base class for normalized persistence failures."""


class RepositoryConflictError(RepositoryError):
    """A create or immutable write conflicts with an existing aggregate."""


class RepositoryNotFoundError(RepositoryError):
    """A requested aggregate does not exist."""


class RepositoryCorruptError(RepositoryError):
    """Repository data cannot be interpreted as a valid aggregate."""


class AdapterError(FRAExpectedError):
    """Base class for normalized external-boundary failures."""


class AdapterUnavailableError(AdapterError):
    """An adapter or its dependency is unavailable."""


class AuthenticationRequiredError(AdapterError):
    """An adapter requires authentication that is not currently available."""


class CapabilityUnsupportedError(AdapterError):
    """An adapter does not implement a requested capability."""


class CapabilityUnavailableError(AdapterError):
    """A normally supported capability is temporarily unavailable."""


class ExternalRateLimitedError(AdapterError):
    """An external dependency refused a call because of a rate limit."""


class SourceQuotaExceededError(AdapterError):
    """A configured source quota is exhausted."""


class ExternalTimeoutError(AdapterError):
    """An external operation exceeded its time budget."""


class ExternalDataInvalidError(AdapterError):
    """External data could not be normalized into an FRA-owned value."""


class UsagePolicyViolationError(AdapterError):
    """The requested source use is not permitted by policy."""


class PointInTimeUnavailableError(AdapterError):
    """A source cannot prove the requested point-in-time view."""


class SourceTermsReviewExpiredError(AdapterError):
    """A source's terms review is too old for permitted use."""


class StructuredOutputInvalidError(AdapterError):
    """Agent output failed structural validation."""


class ResearchNeedsInputError(FRAExpectedError):
    """Research cannot continue without a material user input."""


class ResearchIncompleteError(FRAExpectedError):
    """Research ended with a visible incomplete result."""
