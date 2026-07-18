"""Provider-independent economic-series values."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from fra.domain.errors import DomainValidationError
from fra.domain.time import as_utc


@dataclass(frozen=True, slots=True)
class EconomicSeriesRequest:
    series_id: str
    geography: str
    start_period: str
    end_period: str
    page_size: int = 1000
    point_in_time_at: datetime | None = None

    def __post_init__(self) -> None:
        for field in ("series_id", "geography", "start_period", "end_period"):
            if not getattr(self, field).strip():
                raise DomainValidationError(f"economic request {field} must not be empty")
        if self.start_period > self.end_period:
            raise DomainValidationError("economic request start period must not follow end period")
        if self.page_size < 1:
            raise DomainValidationError("economic request page size must be positive")
        if self.point_in_time_at is not None:
            object.__setattr__(
                self,
                "point_in_time_at",
                as_utc(self.point_in_time_at, field="point_in_time_at"),
            )


@dataclass(frozen=True, slots=True)
class EconomicObservation:
    series_id: str
    geography: str
    period: str
    value: Decimal | None
    units: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class EconomicSeries:
    series_id: str
    geography: str
    title: str
    observations: tuple[EconomicObservation, ...]


@dataclass(frozen=True, slots=True)
class EconomicSeriesCapabilities:
    observations: bool
    vintages: bool
    frequencies: frozenset[str] = frozenset()
