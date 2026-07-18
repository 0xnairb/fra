"""Repository ports for initial research and signal aggregates."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fra.domain.analytics import Calculation
from fra.domain.forecasts import ExposureGraph, ForecastOutcome, ForecastScore, ForecastVersion
from fra.domain.ids import (
    CalculationId,
    ClaimId,
    EvidenceId,
    ExposureGraphId,
    ForecastId,
    OutcomeId,
    PlanId,
    PortfolioId,
    ProfileId,
    ResearchRunId,
    ScenarioId,
    SignalId,
)
from fra.domain.portfolio import InvestorProfile, Portfolio
from fra.domain.research import (
    Claim,
    Evidence,
    ResearchPlan,
    ResearchRun,
    ResearchRunState,
    ResearchScenario,
    VerificationResult,
)
from fra.domain.shared import ArtifactRef
from fra.domain.signals import Signal, SignalStatus
from fra.domain.sources import SourceCacheEntry, SourceStatusRecord


@dataclass(frozen=True, slots=True)
class ResearchRunQuery:
    states: frozenset[ResearchRunState] = frozenset()
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ResearchRunSummary:
    id: ResearchRunId
    question: str
    state: ResearchRunState
    created_at: datetime
    updated_at: datetime
    artifact: ArtifactRef | None = None


@dataclass(frozen=True, slots=True)
class ResearchReport:
    title: str
    body: str
    artifact: ArtifactRef | None = None


class ResearchRepository(Protocol):
    def create(self, run: ResearchRun) -> None: ...

    def get(self, run_id: ResearchRunId) -> ResearchRun: ...

    def save(self, run: ResearchRun) -> None: ...

    def save_plan(self, run_id: ResearchRunId, plan: ResearchPlan) -> None: ...

    def get_plan(self, run_id: ResearchRunId, plan_id: PlanId | None = None) -> ResearchPlan: ...

    def list(self, query: ResearchRunQuery | None = None) -> tuple[ResearchRunSummary, ...]: ...

    def add_evidence(self, run_id: ResearchRunId, item: Evidence[object]) -> None: ...

    def get_evidence(self, run_id: ResearchRunId, evidence_id: EvidenceId) -> Evidence[object]: ...

    def add_claim(self, run_id: ResearchRunId, claim: Claim) -> None: ...

    def get_claim(self, run_id: ResearchRunId, claim_id: ClaimId) -> Claim: ...

    def save_claim(self, run_id: ResearchRunId, claim: Claim) -> None: ...

    def add_scenario(self, run_id: ResearchRunId, scenario: ResearchScenario) -> None: ...

    def get_scenario(self, run_id: ResearchRunId, scenario_id: ScenarioId) -> ResearchScenario: ...

    def save_verification(
        self, run_id: ResearchRunId, verification: VerificationResult
    ) -> None: ...

    def get_verification(self, run_id: ResearchRunId) -> VerificationResult: ...

    def add_calculation(self, run_id: ResearchRunId, calculation: Calculation) -> None: ...

    def get_calculation(
        self, run_id: ResearchRunId, calculation_id: CalculationId
    ) -> Calculation: ...

    def save_report(self, run_id: ResearchRunId, report: ResearchReport) -> None: ...

    def save_limitation(self, run_id: ResearchRunId, report: ResearchReport) -> None: ...


class SignalRepository(Protocol):
    def save(self, signal: Signal) -> None: ...

    def get(self, signal_id: SignalId, version: int | None = None) -> Signal: ...

    def list(self, statuses: frozenset[SignalStatus] = frozenset()) -> tuple[Signal, ...]: ...


class SourceStatusRepository(Protocol):
    def save(self, status: SourceStatusRecord) -> None: ...

    def get(self, provider_id: str) -> SourceStatusRecord: ...

    def list(self) -> tuple[SourceStatusRecord, ...]: ...


class SourceCacheRepository(Protocol):
    def save(self, entry: SourceCacheEntry) -> None: ...

    def get(self, provider_id: str, request_fingerprint: str) -> SourceCacheEntry | None: ...


class ForecastRepository(Protocol):
    def save(self, forecast: ForecastVersion) -> None: ...

    def get(self, forecast_id: ForecastId, version: int | None = None) -> ForecastVersion: ...

    def list(self) -> tuple[ForecastVersion, ...]: ...


class OutcomeRepository(Protocol):
    def save(self, outcome: ForecastOutcome) -> None: ...

    def get(self, outcome_id: OutcomeId) -> ForecastOutcome: ...

    def list(self) -> tuple[ForecastOutcome, ...]: ...

    def save_score(self, score: ForecastScore) -> None: ...

    def get_score(self, outcome_id: OutcomeId) -> ForecastScore | None: ...


class ExposureGraphRepository(Protocol):
    def save(self, graph: ExposureGraph) -> None: ...

    def get(self, graph_id: ExposureGraphId, version: int | None = None) -> ExposureGraph: ...

    def list(self) -> tuple[ExposureGraph, ...]: ...


class ProfileRepository(Protocol):
    def save(self, profile: InvestorProfile) -> None: ...

    def get(self, profile_id: ProfileId) -> InvestorProfile: ...

    def list(self) -> tuple[InvestorProfile, ...]: ...


class PortfolioRepository(Protocol):
    def save(self, portfolio: Portfolio) -> None: ...

    def get(self, portfolio_id: PortfolioId, version: int | None = None) -> Portfolio: ...

    def list(self) -> tuple[Portfolio, ...]: ...
