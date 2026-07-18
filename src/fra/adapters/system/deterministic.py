"""Deterministic clock and ID adapters for hermetic tests."""

from datetime import datetime, timedelta

from fra.domain.errors import DomainValidationError
from fra.domain.ids import (
    CalculationId,
    ClaimId,
    EvidenceId,
    ExposureGraphId,
    ForecastId,
    ForecastScoreId,
    MandateId,
    OutcomeId,
    PlanId,
    PortfolioId,
    ProfileId,
    ResearchRunId,
    ScenarioId,
    SignalId,
    StageId,
    VerificationId,
)
from fra.domain.time import as_utc


class FixedClock:
    def __init__(self, current: datetime) -> None:
        self._current = as_utc(current, field="current")

    def now(self) -> datetime:
        return self._current

    def advance(self, amount: timedelta) -> None:
        if amount < timedelta(0):
            raise DomainValidationError("fixed clock cannot move backwards")
        self._current += amount


class SequenceIdGenerator:
    """Generates predictable IDs without accepting symbols or provider identifiers."""

    def __init__(self, *, start: int = 1) -> None:
        if start < 0:
            raise DomainValidationError("ID sequence start must not be negative")
        self._next_value = start

    def _value(self, prefix: str) -> str:
        value = f"{prefix}_{self._next_value:04d}"
        self._next_value += 1
        return value

    def research_run_id(self) -> ResearchRunId:
        return ResearchRunId(self._value("run"))

    def mandate_id(self) -> MandateId:
        return MandateId(self._value("mandate"))

    def plan_id(self) -> PlanId:
        return PlanId(self._value("plan"))

    def evidence_id(self) -> EvidenceId:
        return EvidenceId(self._value("evidence"))

    def calculation_id(self) -> CalculationId:
        return CalculationId(self._value("calculation"))

    def claim_id(self) -> ClaimId:
        return ClaimId(self._value("claim"))

    def scenario_id(self) -> ScenarioId:
        return ScenarioId(self._value("scenario"))

    def verification_id(self) -> VerificationId:
        return VerificationId(self._value("verification"))

    def signal_id(self) -> SignalId:
        return SignalId(self._value("signal"))

    def forecast_id(self) -> ForecastId:
        return ForecastId(self._value("forecast"))

    def outcome_id(self) -> OutcomeId:
        return OutcomeId(self._value("outcome"))

    def forecast_score_id(self) -> ForecastScoreId:
        return ForecastScoreId(self._value("score"))

    def exposure_graph_id(self) -> ExposureGraphId:
        return ExposureGraphId(self._value("graph"))

    def profile_id(self) -> ProfileId:
        return ProfileId(self._value("profile"))

    def portfolio_id(self) -> PortfolioId:
        return PortfolioId(self._value("portfolio"))

    def stage_id(self) -> StageId:
        return StageId(self._value("stage"))
