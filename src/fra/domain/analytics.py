"""Pure deterministic finance calculations used by research workflows."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from itertools import pairwise

from fra.domain.errors import DomainValidationError
from fra.domain.ids import CalculationId, EvidenceId, ResearchRunId
from fra.domain.market_data import MarketSeries
from fra.domain.time import as_utc


@dataclass(frozen=True, slots=True)
class Calculation:
    id: CalculationId
    run_id: ResearchRunId
    name: str
    formula_version: int
    input_evidence_ids: tuple[EvidenceId, ...]
    parameters: tuple[tuple[str, str], ...]
    results: tuple[tuple[str, Decimal], ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.name.strip() or self.formula_version < 1:
            raise DomainValidationError("calculation requires a name and positive formula version")
        if not self.input_evidence_ids or not self.results:
            raise DomainValidationError("calculation requires evidence inputs and results")
        if any(not value.is_finite() for _name, value in self.results):
            raise DomainValidationError("calculation results must be finite")
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))


@dataclass(frozen=True, slots=True)
class CryptoMarketMetrics:
    total_return: Decimal
    annualized_volatility: Decimal
    current_drawdown: Decimal
    maximum_drawdown: Decimal
    observation_count: int


def crypto_market_metrics(
    series: MarketSeries, *, annualization_periods: int = 365
) -> CryptoMarketMetrics:
    """Calculate total return, sample volatility, and peak-relative drawdowns."""
    prices = tuple(item.price for item in series.observations)
    if len(prices) < 2:
        raise DomainValidationError("crypto analytics require at least two observations")
    if any(price <= 0 for price in prices):
        raise DomainValidationError("crypto analytics require positive prices")
    if annualization_periods <= 0:
        raise DomainValidationError("annualization periods must be positive")

    with localcontext() as context:
        context.prec = 34
        returns = tuple((current / previous) - 1 for previous, current in pairwise(prices))
        mean = sum(returns, Decimal(0)) / Decimal(len(returns))
        if len(returns) == 1:
            volatility = Decimal(0)
        else:
            variance = sum((item - mean) ** 2 for item in returns) / Decimal(len(returns) - 1)
            volatility = variance.sqrt() * Decimal(annualization_periods).sqrt()

        peak = prices[0]
        drawdowns: list[Decimal] = []
        for price in prices:
            peak = max(peak, price)
            drawdowns.append((price / peak) - 1)
        return CryptoMarketMetrics(
            total_return=(prices[-1] / prices[0]) - 1,
            annualized_volatility=volatility,
            current_drawdown=drawdowns[-1],
            maximum_drawdown=min(drawdowns),
            observation_count=len(prices),
        )
