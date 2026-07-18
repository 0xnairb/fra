"""Provider-independent ID generation boundary."""

from typing import Protocol

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


class IdGenerator(Protocol):
    def research_run_id(self) -> ResearchRunId: ...

    def mandate_id(self) -> MandateId: ...

    def plan_id(self) -> PlanId: ...

    def evidence_id(self) -> EvidenceId: ...

    def calculation_id(self) -> CalculationId: ...

    def claim_id(self) -> ClaimId: ...

    def scenario_id(self) -> ScenarioId: ...

    def verification_id(self) -> VerificationId: ...

    def signal_id(self) -> SignalId: ...

    def forecast_id(self) -> ForecastId: ...

    def outcome_id(self) -> OutcomeId: ...

    def forecast_score_id(self) -> ForecastScoreId: ...

    def exposure_graph_id(self) -> ExposureGraphId: ...

    def profile_id(self) -> ProfileId: ...

    def portfolio_id(self) -> PortfolioId: ...

    def stage_id(self) -> StageId: ...
