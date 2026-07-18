"""Normalized market-data values returned by provider ports."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from fra.domain.errors import DomainValidationError
from fra.domain.ids import InstrumentId
from fra.domain.instruments import Currency, InstrumentRef
from fra.domain.time import as_utc


@dataclass(frozen=True, slots=True)
class InstrumentQuery:
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise DomainValidationError("instrument query must not be empty")


@dataclass(frozen=True, slots=True)
class InstrumentMatch:
    instrument: InstrumentRef
    score: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.score <= Decimal("1"):
            raise DomainValidationError("instrument match score must be between zero and one")


@dataclass(frozen=True, slots=True)
class MarketQuote:
    instrument_id: InstrumentId
    price: Decimal
    currency: Currency
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.price.is_finite() or self.price < 0:
            raise DomainValidationError("market quote price must be finite and non-negative")
        object.__setattr__(self, "observed_at", as_utc(self.observed_at, field="observed_at"))


@dataclass(frozen=True, slots=True)
class MarketBar:
    instrument_id: InstrumentId
    started_at: datetime
    ended_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    currency: Currency

    def __post_init__(self) -> None:
        object.__setattr__(self, "started_at", as_utc(self.started_at, field="started_at"))
        object.__setattr__(self, "ended_at", as_utc(self.ended_at, field="ended_at"))
        if self.started_at >= self.ended_at:
            raise DomainValidationError("market bar must end after it starts")
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close, self.high
        ):
            raise DomainValidationError("market bar high/low values are inconsistent")


@dataclass(frozen=True, slots=True)
class MarketSeries:
    instrument_id: InstrumentId
    bars: tuple[MarketBar, ...]
    currency: Currency


@dataclass(frozen=True, slots=True)
class HistoryRequest:
    instrument: InstrumentRef
    start_at: datetime
    end_at: datetime
    resolution: str
    point_in_time_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_at", as_utc(self.start_at, field="start_at"))
        object.__setattr__(self, "end_at", as_utc(self.end_at, field="end_at"))
        if self.point_in_time_at is not None:
            object.__setattr__(
                self,
                "point_in_time_at",
                as_utc(self.point_in_time_at, field="point_in_time_at"),
            )
        if self.start_at >= self.end_at:
            raise DomainValidationError("history request must end after it starts")
        if not self.resolution.strip():
            raise DomainValidationError("history resolution must not be empty")


@dataclass(frozen=True, slots=True)
class MarketDataCapabilities:
    quotes: bool
    history: bool
    resolutions: frozenset[str] = frozenset()
