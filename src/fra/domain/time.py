"""UTC time validation used by domain values."""

from datetime import UTC, datetime

from fra.domain.errors import DomainValidationError


def as_utc(value: datetime, *, field: str = "datetime") -> datetime:
    """Reject naive timestamps and normalize aware timestamps to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)
