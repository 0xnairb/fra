"""Hermetic repository implementations with production-like conflict semantics."""

from fra.domain.analytics import Calculation
from fra.domain.errors import RepositoryConflictError, RepositoryNotFoundError
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
    ResearchScenario,
    VerificationResult,
)
from fra.domain.signals import Signal, SignalStatus
from fra.domain.sources import SourceCacheEntry, SourceStatusRecord
from fra.ports.repositories import (
    ResearchReport,
    ResearchRunQuery,
    ResearchRunSummary,
)


class InMemoryResearchRepository:
    def __init__(self) -> None:
        self._runs: dict[ResearchRunId, ResearchRun] = {}
        self._plans: dict[ResearchRunId, ResearchPlan] = {}
        self._evidence: dict[tuple[ResearchRunId, EvidenceId], Evidence[object]] = {}
        self._claims: dict[tuple[ResearchRunId, ClaimId], Claim] = {}
        self._scenarios: dict[tuple[ResearchRunId, ScenarioId], ResearchScenario] = {}
        self._verifications: dict[ResearchRunId, VerificationResult] = {}
        self._calculations: dict[tuple[ResearchRunId, CalculationId], Calculation] = {}
        self._reports: dict[ResearchRunId, ResearchReport] = {}
        self._limitations: dict[ResearchRunId, ResearchReport] = {}

    def create(self, run: ResearchRun) -> None:
        if run.id in self._runs:
            raise RepositoryConflictError(f"research run {run.id} already exists")
        self._runs[run.id] = run

    def get(self, run_id: ResearchRunId) -> ResearchRun:
        try:
            return self._runs[run_id]
        except KeyError as error:
            raise RepositoryNotFoundError(f"research run {run_id} does not exist") from error

    def save(self, run: ResearchRun) -> None:
        existing = self.get(run.id)
        if run.updated_at < existing.updated_at:
            raise RepositoryConflictError(f"research run {run.id} update is stale")
        self._runs[run.id] = run

    def save_plan(self, run_id: ResearchRunId, plan: ResearchPlan) -> None:
        self.get(run_id)
        if plan.run_id != run_id:
            raise RepositoryConflictError("research plan run ID does not match its aggregate")
        existing = self._plans.get(run_id)
        if existing is not None and existing != plan:
            raise RepositoryConflictError(f"research plan for {run_id} is immutable")
        self._plans[run_id] = plan

    def get_plan(self, run_id: ResearchRunId, plan_id: PlanId | None = None) -> ResearchPlan:
        try:
            plan = self._plans[run_id]
        except KeyError as error:
            raise RepositoryNotFoundError(f"research plan for {run_id} does not exist") from error
        if plan_id is not None and plan.id != plan_id:
            raise RepositoryNotFoundError(f"research plan {plan_id} does not exist")
        return plan

    def list(self, query: ResearchRunQuery | None = None) -> tuple[ResearchRunSummary, ...]:
        query = query or ResearchRunQuery()
        runs = sorted(self._runs.values(), key=lambda item: item.updated_at, reverse=True)
        if query.states:
            runs = [run for run in runs if run.state in query.states]
        if query.limit is not None:
            runs = runs[: query.limit]
        return tuple(
            ResearchRunSummary(
                id=run.id,
                question=run.mandate.question,
                state=run.state,
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
            for run in runs
        )

    def add_evidence(self, run_id: ResearchRunId, item: Evidence[object]) -> None:
        self.get(run_id)
        key = (run_id, item.id)
        if key in self._evidence:
            raise RepositoryConflictError(f"evidence {item.id} already exists")
        self._evidence[key] = item

    def get_evidence(self, run_id: ResearchRunId, evidence_id: EvidenceId) -> Evidence[object]:
        try:
            return self._evidence[(run_id, evidence_id)]
        except KeyError as error:
            raise RepositoryNotFoundError(f"evidence {evidence_id} does not exist") from error

    def add_claim(self, run_id: ResearchRunId, claim: Claim) -> None:
        self.get(run_id)
        key = (run_id, claim.id)
        if key in self._claims:
            raise RepositoryConflictError(f"claim {claim.id} already exists")
        self._claims[key] = claim

    def get_claim(self, run_id: ResearchRunId, claim_id: ClaimId) -> Claim:
        try:
            return self._claims[(run_id, claim_id)]
        except KeyError as error:
            raise RepositoryNotFoundError(f"claim {claim_id} does not exist") from error

    def save_claim(self, run_id: ResearchRunId, claim: Claim) -> None:
        self.get(run_id)
        key = (run_id, claim.id)
        if key not in self._claims:
            raise RepositoryNotFoundError(f"claim {claim.id} does not exist")
        if claim.run_id != run_id:
            raise RepositoryConflictError("claim run ID does not match its aggregate")
        self._claims[key] = claim

    def add_scenario(self, run_id: ResearchRunId, scenario: ResearchScenario) -> None:
        self.get(run_id)
        if scenario.run_id != run_id:
            raise RepositoryConflictError("scenario run ID does not match its aggregate")
        key = (run_id, scenario.id)
        if key in self._scenarios:
            raise RepositoryConflictError(f"scenario {scenario.id} already exists")
        self._scenarios[key] = scenario

    def get_scenario(self, run_id: ResearchRunId, scenario_id: ScenarioId) -> ResearchScenario:
        try:
            return self._scenarios[(run_id, scenario_id)]
        except KeyError as error:
            raise RepositoryNotFoundError(f"scenario {scenario_id} does not exist") from error

    def save_verification(self, run_id: ResearchRunId, verification: VerificationResult) -> None:
        self.get(run_id)
        if verification.run_id != run_id:
            raise RepositoryConflictError("verification run ID does not match its aggregate")
        self._verifications[run_id] = verification

    def get_verification(self, run_id: ResearchRunId) -> VerificationResult:
        try:
            return self._verifications[run_id]
        except KeyError as error:
            raise RepositoryNotFoundError(f"verification for {run_id} does not exist") from error

    def add_calculation(self, run_id: ResearchRunId, calculation: Calculation) -> None:
        self.get(run_id)
        if calculation.run_id != run_id:
            raise RepositoryConflictError("calculation run ID does not match its aggregate")
        key = (run_id, calculation.id)
        if key in self._calculations:
            raise RepositoryConflictError(f"calculation {calculation.id} already exists")
        self._calculations[key] = calculation

    def get_calculation(self, run_id: ResearchRunId, calculation_id: CalculationId) -> Calculation:
        try:
            return self._calculations[(run_id, calculation_id)]
        except KeyError as error:
            raise RepositoryNotFoundError(f"calculation {calculation_id} does not exist") from error

    def save_report(self, run_id: ResearchRunId, report: ResearchReport) -> None:
        self.get(run_id)
        if run_id in self._reports:
            raise RepositoryConflictError(f"report for {run_id} already exists")
        self._reports[run_id] = report

    def save_limitation(self, run_id: ResearchRunId, report: ResearchReport) -> None:
        self.get(run_id)
        self._limitations[run_id] = report


class InMemorySignalRepository:
    def __init__(self) -> None:
        self._signals: dict[tuple[SignalId, int], Signal] = {}

    def save(self, signal: Signal) -> None:
        key = (signal.id, signal.version)
        if key in self._signals:
            raise RepositoryConflictError(
                f"signal {signal.id} version {signal.version} is immutable and already exists"
            )
        if signal.version > 1 and (signal.id, signal.version - 1) not in self._signals:
            raise RepositoryConflictError("signal versions must be contiguous")
        if signal.version > 1 and signal.supersedes_version != signal.version - 1:
            raise RepositoryConflictError(
                "a signal correction must explicitly supersede the previous version"
            )
        if signal.version == 1 and signal.supersedes_version is not None:
            raise RepositoryConflictError("the first signal version cannot supersede a version")
        self._signals[key] = signal

    def get(self, signal_id: SignalId, version: int | None = None) -> Signal:
        if version is None:
            versions = [key_version for key_id, key_version in self._signals if key_id == signal_id]
            if not versions:
                raise RepositoryNotFoundError(f"signal {signal_id} does not exist")
            version = max(versions)
        try:
            return self._signals[(signal_id, version)]
        except KeyError as error:
            raise RepositoryNotFoundError(
                f"signal {signal_id} version {version} does not exist"
            ) from error

    def list(self, statuses: frozenset[SignalStatus] = frozenset()) -> tuple[Signal, ...]:
        latest = {signal_id: self.get(signal_id) for signal_id, _version in self._signals}
        signals = tuple(latest.values())
        if statuses:
            signals = tuple(signal for signal in signals if signal.status in statuses)
        return tuple(sorted(signals, key=lambda signal: signal.issued_at, reverse=True))


class InMemorySourceStatusRepository:
    def __init__(self) -> None:
        self._statuses: dict[str, SourceStatusRecord] = {}

    def save(self, status: SourceStatusRecord) -> None:
        existing = self._statuses.get(status.provider_id)
        if existing is not None and status.checked_at < existing.checked_at:
            raise RepositoryConflictError(f"source status {status.provider_id} update is stale")
        self._statuses[status.provider_id] = status

    def get(self, provider_id: str) -> SourceStatusRecord:
        try:
            return self._statuses[provider_id]
        except KeyError as error:
            raise RepositoryNotFoundError(f"source status {provider_id} does not exist") from error

    def list(self) -> tuple[SourceStatusRecord, ...]:
        return tuple(sorted(self._statuses.values(), key=lambda item: item.provider_id))


class InMemorySourceCacheRepository:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], SourceCacheEntry] = {}

    def save(self, entry: SourceCacheEntry) -> None:
        self._entries[(entry.provider_id, entry.request_fingerprint)] = entry

    def get(self, provider_id: str, request_fingerprint: str) -> SourceCacheEntry | None:
        return self._entries.get((provider_id, request_fingerprint))


class InMemoryForecastRepository:
    def __init__(self) -> None:
        self._versions: dict[tuple[ForecastId, int], ForecastVersion] = {}

    def save(self, forecast: ForecastVersion) -> None:
        key = (forecast.forecast.id, forecast.version)
        if key in self._versions:
            raise RepositoryConflictError(
                f"forecast {forecast.forecast.id} version {forecast.version} is immutable"
            )
        if (
            forecast.version > 1
            and (
                forecast.forecast.id,
                forecast.version - 1,
            )
            not in self._versions
        ):
            raise RepositoryConflictError("forecast versions must be contiguous")
        self._versions[key] = forecast

    def get(self, forecast_id: ForecastId, version: int | None = None) -> ForecastVersion:
        if version is None:
            versions = [item for item_id, item in self._versions if item_id == forecast_id]
            if not versions:
                raise RepositoryNotFoundError(f"forecast {forecast_id} does not exist")
            version = max(versions)
        try:
            return self._versions[(forecast_id, version)]
        except KeyError as error:
            raise RepositoryNotFoundError(
                f"forecast {forecast_id} version {version} does not exist"
            ) from error

    def list(self) -> tuple[ForecastVersion, ...]:
        forecast_ids = {forecast_id for forecast_id, _version in self._versions}
        return tuple(
            sorted(
                (self.get(forecast_id) for forecast_id in forecast_ids),
                key=lambda item: item.issued_at,
                reverse=True,
            )
        )


class InMemoryOutcomeRepository:
    def __init__(self) -> None:
        self._outcomes: dict[OutcomeId, ForecastOutcome] = {}
        self._scores: dict[OutcomeId, ForecastScore] = {}

    def save(self, outcome: ForecastOutcome) -> None:
        if outcome.id in self._outcomes:
            raise RepositoryConflictError(f"outcome {outcome.id} already exists")
        self._outcomes[outcome.id] = outcome

    def get(self, outcome_id: OutcomeId) -> ForecastOutcome:
        try:
            return self._outcomes[outcome_id]
        except KeyError as error:
            raise RepositoryNotFoundError(f"outcome {outcome_id} does not exist") from error

    def list(self) -> tuple[ForecastOutcome, ...]:
        return tuple(
            sorted(self._outcomes.values(), key=lambda item: item.resolved_at, reverse=True)
        )

    def save_score(self, score: ForecastScore) -> None:
        self.get(score.outcome_id)
        if score.outcome_id in self._scores:
            raise RepositoryConflictError(f"outcome {score.outcome_id} already has a score")
        self._scores[score.outcome_id] = score

    def get_score(self, outcome_id: OutcomeId) -> ForecastScore | None:
        self.get(outcome_id)
        return self._scores.get(outcome_id)


class InMemoryExposureGraphRepository:
    def __init__(self) -> None:
        self._graphs: dict[tuple[ExposureGraphId, int], ExposureGraph] = {}

    def save(self, graph: ExposureGraph) -> None:
        key = (graph.id, graph.version)
        if key in self._graphs:
            raise RepositoryConflictError(f"exposure graph {graph.id} version is immutable")
        if graph.version > 1 and (graph.id, graph.version - 1) not in self._graphs:
            raise RepositoryConflictError("exposure graph versions must be contiguous")
        self._graphs[key] = graph

    def get(self, graph_id: ExposureGraphId, version: int | None = None) -> ExposureGraph:
        if version is None:
            versions = [item for item_id, item in self._graphs if item_id == graph_id]
            if not versions:
                raise RepositoryNotFoundError(f"exposure graph {graph_id} does not exist")
            version = max(versions)
        try:
            return self._graphs[(graph_id, version)]
        except KeyError as error:
            raise RepositoryNotFoundError(
                f"exposure graph {graph_id} version {version} does not exist"
            ) from error

    def list(self) -> tuple[ExposureGraph, ...]:
        graph_ids = {graph_id for graph_id, _version in self._graphs}
        return tuple(self.get(graph_id) for graph_id in sorted(graph_ids, key=str))


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self._profiles: dict[ProfileId, InvestorProfile] = {}

    def save(self, profile: InvestorProfile) -> None:
        if profile.id in self._profiles:
            raise RepositoryConflictError(f"profile {profile.id} is immutable")
        self._profiles[profile.id] = profile

    def get(self, profile_id: ProfileId) -> InvestorProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as error:
            raise RepositoryNotFoundError(f"profile {profile_id} does not exist") from error

    def list(self) -> tuple[InvestorProfile, ...]:
        return tuple(sorted(self._profiles.values(), key=lambda item: item.confirmed_at))


class InMemoryPortfolioRepository:
    def __init__(self) -> None:
        self._portfolios: dict[tuple[PortfolioId, int], Portfolio] = {}

    def save(self, portfolio: Portfolio) -> None:
        key = (portfolio.id, portfolio.version)
        if key in self._portfolios:
            raise RepositoryConflictError(f"portfolio {portfolio.id} version is immutable")
        if portfolio.version > 1 and (portfolio.id, portfolio.version - 1) not in self._portfolios:
            raise RepositoryConflictError("portfolio versions must be contiguous")
        self._portfolios[key] = portfolio

    def get(self, portfolio_id: PortfolioId, version: int | None = None) -> Portfolio:
        if version is None:
            versions = [item for item_id, item in self._portfolios if item_id == portfolio_id]
            if not versions:
                raise RepositoryNotFoundError(f"portfolio {portfolio_id} does not exist")
            version = max(versions)
        try:
            return self._portfolios[(portfolio_id, version)]
        except KeyError as error:
            raise RepositoryNotFoundError(f"portfolio {portfolio_id} does not exist") from error

    def list(self) -> tuple[Portfolio, ...]:
        ids = {portfolio_id for portfolio_id, _version in self._portfolios}
        return tuple(self.get(portfolio_id) for portfolio_id in sorted(ids, key=str))
