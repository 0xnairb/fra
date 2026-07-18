"""Suitability profiles, portfolio artifacts, and deterministic allocation analytics."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import StrEnum

from fra.domain.errors import DomainValidationError
from fra.domain.ids import CalculationId, EvidenceId, InstrumentId, PortfolioId, ProfileId
from fra.domain.instruments import Currency
from fra.domain.time import as_utc


class RiskTolerance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class InvestorProfile:
    id: ProfileId
    horizon_years: int
    risk_tolerance: RiskTolerance
    investment_objective: str
    risk_capacity: RiskTolerance
    maximum_loss: Decimal
    liquidity_need: Decimal
    tax_jurisdiction: str
    base_currency: Currency
    maximum_asset_weight: Decimal
    minimum_cash_weight: Decimal
    restricted_instrument_ids: tuple[InstrumentId, ...]
    confirmed_at: datetime

    def __post_init__(self) -> None:
        if (
            self.horizon_years < 1
            or not self.investment_objective.strip()
            or not self.tax_jurisdiction.strip()
        ):
            raise DomainValidationError(
                "profile requires an objective, horizon, and tax jurisdiction"
            )
        bounded = (
            self.maximum_loss,
            self.liquidity_need,
            self.maximum_asset_weight,
            self.minimum_cash_weight,
        )
        if any(not Decimal(0) <= value <= Decimal(1) for value in bounded):
            raise DomainValidationError("profile weights and loss limits must be zero to one")
        if self.maximum_asset_weight <= 0:
            raise DomainValidationError("maximum asset weight must be positive")
        object.__setattr__(self, "confirmed_at", as_utc(self.confirmed_at, field="confirmed_at"))


class PortfolioKind(StrEnum):
    OBSERVED = "observed"
    PROPOSED = "proposed"


@dataclass(frozen=True, slots=True)
class PortfolioPosition:
    instrument_id: InstrumentId
    symbol: str
    weight: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not Decimal(0) <= self.weight <= Decimal(1):
            raise DomainValidationError("portfolio position requires symbol and valid weight")


@dataclass(frozen=True, slots=True)
class Portfolio:
    id: PortfolioId
    version: int
    kind: PortfolioKind
    profile_id: ProfileId
    positions: tuple[PortfolioPosition, ...]
    as_of: datetime
    evidence_ids: tuple[EvidenceId, ...]
    calculation_ids: tuple[CalculationId, ...]
    supersedes_version: int | None = None

    def __post_init__(self) -> None:
        if self.version < 1 or not self.positions:
            raise DomainValidationError("portfolio requires a positive version and positions")
        if sum((item.weight for item in self.positions), Decimal(0)) != Decimal(1):
            raise DomainValidationError("portfolio weights must sum exactly to one")
        if not self.evidence_ids or not self.calculation_ids:
            raise DomainValidationError("proposed portfolio requires evidence and calculations")
        if len({item.instrument_id for item in self.positions}) != len(self.positions):
            raise DomainValidationError("portfolio instruments must be unique")
        if self.version == 1 and self.supersedes_version is not None:
            raise DomainValidationError("first portfolio version cannot supersede another")
        if self.version > 1 and self.supersedes_version != self.version - 1:
            raise DomainValidationError("portfolio update must supersede its previous version")
        object.__setattr__(self, "as_of", as_utc(self.as_of, field="as_of"))


@dataclass(frozen=True, slots=True)
class AllocationCandidate:
    instrument_id: InstrumentId
    symbol: str
    currency: Currency
    risk_level: Decimal
    stress_loss: Decimal

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not Decimal(0) <= self.risk_level <= Decimal(1):
            raise DomainValidationError("allocation candidate risk must be zero to one")
        if not Decimal(-1) <= self.stress_loss <= Decimal(0):
            raise DomainValidationError("allocation stress loss must be between minus one and zero")


@dataclass(frozen=True, slots=True)
class AllocationResult:
    positions: tuple[PortfolioPosition, ...]
    concentration: Decimal
    stress_loss: Decimal


def propose_allocation(
    profile: InvestorProfile, candidates: tuple[AllocationCandidate, ...]
) -> AllocationResult:
    eligible = tuple(
        item for item in candidates if item.instrument_id not in profile.restricted_instrument_ids
    )
    if not eligible:
        raise DomainValidationError("allocation requires at least one eligible candidate")
    available = Decimal(1) - profile.minimum_cash_weight
    if available > profile.maximum_asset_weight * len(eligible):
        raise DomainValidationError("maximum asset weight makes the allocation infeasible")
    target = {
        RiskTolerance.LOW: Decimal("0.25"),
        RiskTolerance.MEDIUM: Decimal("0.50"),
        RiskTolerance.HIGH: Decimal("0.75"),
    }[profile.risk_tolerance]
    scores = tuple(
        Decimal(1) / (abs(item.risk_level - target) + Decimal("0.10")) for item in eligible
    )
    weights = _capped_weights(scores, available, profile.maximum_asset_weight)
    positions = (
        *(
            PortfolioPosition(item.instrument_id, item.symbol, weight, item.currency)
            for item, weight in zip(eligible, weights, strict=True)
        ),
        PortfolioPosition(
            InstrumentId("cash:base"),
            "CASH",
            profile.minimum_cash_weight,
            profile.base_currency,
        ),
    )
    concentration = sum((item.weight**2 for item in positions), Decimal(0))
    stress = sum(
        (weight * item.stress_loss for item, weight in zip(eligible, weights, strict=True)),
        Decimal(0),
    )
    return AllocationResult(positions, concentration, stress)


def _capped_weights(
    scores: tuple[Decimal, ...], total: Decimal, cap: Decimal
) -> tuple[Decimal, ...]:
    remaining = total
    active = set(range(len(scores)))
    weights = [Decimal(0)] * len(scores)
    with localcontext() as context:
        context.prec = 34
        while active:
            denominator = sum((scores[index] for index in active), Decimal(0))
            capped = {index for index in active if remaining * scores[index] / denominator > cap}
            if not capped:
                ordered = sorted(active)
                for index in ordered[:-1]:
                    weights[index] = remaining * scores[index] / denominator
                last = ordered[-1]
                weights[last] = remaining - sum(
                    (weights[index] for index in ordered[:-1]), Decimal(0)
                )
                break
            for index in capped:
                weights[index] = cap
                remaining -= cap
                active.remove(index)
    return tuple(weights)
