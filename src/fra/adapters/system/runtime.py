"""Production clock and collision-resistant local ID adapters."""

from datetime import UTC, datetime
from uuid import uuid4

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


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class RandomIdGenerator:
    @staticmethod
    def _value(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

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
