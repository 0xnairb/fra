"""Deterministic crisis events, transmission channels, and exposure analytics."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import StrEnum

from fra.domain.economic import EconomicSeries
from fra.domain.errors import DomainValidationError
from fra.domain.ids import EvidenceId
from fra.domain.time import as_utc


class EventEvidenceClass(StrEnum):
    OFFICIAL_FACT = "official_fact"
    DISCOVERY_SIGNAL = "discovery_signal"


@dataclass(frozen=True, slots=True)
class CrisisEvent:
    event_id: str
    title: str
    occurred_at: datetime
    available_at: datetime
    evidence_class: EventEvidenceClass
    evidence_ids: tuple[EvidenceId, ...]

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.title.strip() or not self.evidence_ids:
            raise DomainValidationError("crisis event requires identity and evidence")
        for field in ("occurred_at", "available_at"):
            object.__setattr__(self, field, as_utc(getattr(self, field), field=field))


@dataclass(frozen=True, slots=True)
class TransmissionChannel:
    name: str
    from_subject: str
    to_subject: str
    direction: str
    expected_lag: str
    confidence: Decimal
    evidence_ids: tuple[EvidenceId, ...]
    invalidation_condition: str

    def __post_init__(self) -> None:
        strings = (
            self.name,
            self.from_subject,
            self.to_subject,
            self.direction,
            self.expected_lag,
            self.invalidation_condition,
        )
        if any(not value.strip() for value in strings) or not self.evidence_ids:
            raise DomainValidationError("transmission channel requires complete evidence fields")
        if not Decimal(0) <= self.confidence <= Decimal(1):
            raise DomainValidationError("transmission confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class CrisisMetrics:
    oil_price_change: Decimal
    fertilizer_price_change: Decimal
    inventory_change: Decimal
    pressure_index: Decimal


@dataclass(frozen=True, slots=True)
class BusinessExposure:
    subject_id: str
    name: str
    industry: str
    jurisdiction: str
    input_exposure: Decimal
    pricing_power: Decimal
    evidence_coverage: Decimal
    confidence: Decimal
    stress_score: Decimal

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.subject_id, self.name, self.industry, self.jurisdiction)
        ):
            raise DomainValidationError("business exposure identity must not be empty")
        bounded = (
            self.input_exposure,
            self.pricing_power,
            self.evidence_coverage,
            self.confidence,
        )
        if any(not Decimal(0) <= value <= Decimal(1) for value in bounded):
            raise DomainValidationError("business exposure factors must be between zero and one")


def crisis_metrics(
    oil: EconomicSeries, fertilizer: EconomicSeries, inventory: EconomicSeries
) -> CrisisMetrics:
    oil_change = _series_change(oil)
    fertilizer_change = _series_change(fertilizer)
    inventory_change = _series_change(inventory)
    with localcontext() as context:
        context.prec = 34
        pressure = oil_change + fertilizer_change - inventory_change
    return CrisisMetrics(oil_change, fertilizer_change, inventory_change, pressure)


def rank_business_exposures(
    metrics: CrisisMetrics,
    profiles: tuple[tuple[str, str, str, str, Decimal, Decimal, Decimal], ...],
) -> tuple[BusinessExposure, ...]:
    results = []
    for (
        subject_id,
        name,
        industry,
        jurisdiction,
        input_exposure,
        pricing_power,
        coverage,
    ) in profiles:
        confidence = coverage * Decimal("0.8")
        stress = metrics.pressure_index * input_exposure * (Decimal(1) - pricing_power)
        results.append(
            BusinessExposure(
                subject_id,
                name,
                industry,
                jurisdiction,
                input_exposure,
                pricing_power,
                coverage,
                confidence,
                stress,
            )
        )
    return tuple(sorted(results, key=lambda item: (-item.stress_score, item.subject_id)))


def _series_change(series: EconomicSeries) -> Decimal:
    values = tuple(item.value for item in series.observations if item.value is not None)
    if len(values) < 2 or values[0] == 0:
        raise DomainValidationError(f"series {series.series_id} requires two non-zero observations")
    return values[-1] / values[0] - Decimal(1)
