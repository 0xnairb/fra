"""Explicit issue, monitor, resolve, refresh, and score forecast use cases."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from fra.application.research_workflows import ResearchRegistry
from fra.domain.errors import (
    CapabilityUnavailableError,
    DomainValidationError,
    LookAheadEvidenceError,
    ResearchIncompleteError,
)
from fra.domain.forecasts import (
    Forecast,
    ForecastOutcome,
    ForecastResolutionValue,
    ForecastScore,
    ForecastStatus,
    ForecastTrigger,
    ForecastVersion,
    InvalidationCondition,
    ResolutionRule,
)
from fra.domain.ids import EvidenceId, ForecastId, ResearchRunId
from fra.domain.research import Evidence, ResearchMandateType, ResearchRun
from fra.domain.time import as_utc
from fra.ports.clock import Clock
from fra.ports.ids import IdGenerator
from fra.ports.repositories import ForecastRepository, OutcomeRepository, ResearchRepository


@dataclass(frozen=True, slots=True)
class ForecastDraft:
    run_id: ResearchRunId
    question: str
    hypothesis: str
    probability: Decimal
    horizon_end: datetime
    trigger: ForecastTrigger
    invalidation_conditions: tuple[InvalidationCondition, ...]
    resolution_rule: ResolutionRule
    transmission_path: str
    alternatives: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "horizon_end", as_utc(self.horizon_end, field="horizon_end"))
        if not self.probability.is_finite() or not Decimal(0) <= self.probability <= Decimal(1):
            raise DomainValidationError("forecast probability must be between zero and one")


class IssueForecast:
    def __init__(self, repository: ForecastRepository, clock: Clock, ids: IdGenerator) -> None:
        self._repository = repository
        self._clock = clock
        self._ids = ids

    def issue(self, draft: ForecastDraft, evidence: tuple[Evidence[Any], ...]) -> ForecastVersion:
        now = self._clock.now()
        evidence_ids = _evidence_snapshot(evidence, now)
        forecast = Forecast(
            id=self._ids.forecast_id(),
            run_id=draft.run_id,
            question=draft.question,
            hypothesis=draft.hypothesis,
            trigger=draft.trigger,
            resolution_rule=draft.resolution_rule,
            created_at=now,
        )
        version = ForecastVersion(
            forecast=forecast,
            version=1,
            probability=draft.probability,
            issued_at=now,
            knowledge_cutoff_at=now,
            horizon_end=draft.horizon_end,
            evidence_ids=evidence_ids,
            invalidation_conditions=draft.invalidation_conditions,
            transmission_path=draft.transmission_path,
            alternatives=draft.alternatives,
            status=ForecastStatus.ACTIVE,
        )
        self._repository.save(version)
        return version


class MonitorForecast:
    def __init__(self, repository: ForecastRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def update(
        self,
        forecast_id: object,
        probability: Decimal,
        evidence: tuple[Evidence[Any], ...],
        *,
        reason: str,
    ) -> ForecastVersion:
        from fra.domain.ids import ForecastId

        if not isinstance(forecast_id, ForecastId):
            raise DomainValidationError("monitor requires a forecast ID")
        previous = self._repository.get(forecast_id)
        now = self._clock.now()
        version = ForecastVersion(
            forecast=previous.forecast,
            version=previous.version + 1,
            probability=probability,
            issued_at=now,
            knowledge_cutoff_at=now,
            horizon_end=previous.horizon_end,
            evidence_ids=_evidence_snapshot(evidence, now),
            invalidation_conditions=previous.invalidation_conditions,
            transmission_path=previous.transmission_path,
            alternatives=previous.alternatives,
            status=ForecastStatus.MONITORING,
            supersedes_version=previous.version,
            update_reason=reason,
        )
        self._repository.save(version)
        return version


class ResolveForecast:
    def __init__(
        self,
        forecasts: ForecastRepository,
        outcomes: OutcomeRepository,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._forecasts = forecasts
        self._outcomes = outcomes
        self._clock = clock
        self._ids = ids

    def resolve(
        self,
        forecast_id: object,
        value: ForecastResolutionValue,
        evidence: tuple[Evidence[Any], ...],
        *,
        resolver: str,
        ambiguity_notes: str | None = None,
    ) -> ForecastOutcome:
        from fra.domain.ids import ForecastId

        if not isinstance(forecast_id, ForecastId):
            raise DomainValidationError("resolve requires a forecast ID")
        forecast = self._forecasts.get(forecast_id)
        now = self._clock.now()
        if now < forecast.horizon_end:
            raise DomainValidationError("forecast cannot resolve before its declared horizon")
        outcome = ForecastOutcome(
            id=self._ids.outcome_id(),
            forecast_id=forecast_id,
            forecast_version=forecast.version,
            resolved_at=now,
            value=value,
            evidence_ids=_evidence_snapshot(evidence, now),
            rule_version=forecast.forecast.resolution_rule.version,
            resolver=resolver,
            ambiguity_notes=ambiguity_notes,
        )
        self._outcomes.save(outcome)
        return outcome


class ScoreForecast:
    def __init__(
        self,
        forecasts: ForecastRepository,
        outcomes: OutcomeRepository,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._forecasts = forecasts
        self._outcomes = outcomes
        self._clock = clock
        self._ids = ids

    def score(self, outcome_id: object) -> ForecastScore:
        from fra.domain.ids import OutcomeId

        if not isinstance(outcome_id, OutcomeId):
            raise DomainValidationError("score requires an outcome ID")
        outcome = self._outcomes.get(outcome_id)
        forecast = self._forecasts.get(outcome.forecast_id, outcome.forecast_version)
        actual = (
            Decimal(1)
            if outcome.value is ForecastResolutionValue.TRUE
            else Decimal(0)
            if outcome.value is ForecastResolutionValue.FALSE
            else None
        )
        brier = None if actual is None else (forecast.probability - actual) ** 2
        score = ForecastScore(
            id=self._ids.forecast_score_id(),
            outcome_id=outcome.id,
            forecast_id=outcome.forecast_id,
            forecast_version=outcome.forecast_version,
            brier_score=brier,
            scored_at=self._clock.now(),
        )
        self._outcomes.save_score(score)
        return score


def _evidence_snapshot(
    evidence: tuple[Evidence[Any], ...], cutoff: datetime
) -> tuple[EvidenceId, ...]:
    if not evidence:
        raise DomainValidationError("forecast operation requires evidence")
    if any(item.available_at > cutoff for item in evidence):
        raise LookAheadEvidenceError("future-published evidence cannot enter a forecast version")
    return tuple(EvidenceId(str(item.id)) for item in evidence)


@dataclass(frozen=True, slots=True)
class ForecastResolutionResult:
    outcome: ForecastOutcome
    score: ForecastScore


class ForecastLifecycleService:
    """Load persisted evidence and expose explicit local forecast operations."""

    def __init__(
        self,
        forecasts: ForecastRepository,
        outcomes: OutcomeRepository,
        research: ResearchRepository,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._forecasts = forecasts
        self._outcomes = outcomes
        self._research = research
        self._monitor = MonitorForecast(forecasts, clock)
        self._resolve = ResolveForecast(forecasts, outcomes, clock, ids)
        self._score = ScoreForecast(forecasts, outcomes, clock, ids)

    def list(self) -> tuple[ForecastVersion, ...]:
        return self._forecasts.list()

    def show(self, forecast_id: ForecastId) -> ForecastVersion:
        return self._forecasts.get(forecast_id)

    def monitor(
        self,
        forecast_id: ForecastId,
        probability: Decimal,
        reason: str,
        evidence_ids: tuple[EvidenceId, ...],
    ) -> ForecastVersion:
        forecast = self._forecasts.get(forecast_id)
        evidence = tuple(
            self._research.get_evidence(forecast.forecast.run_id, evidence_id)
            for evidence_id in evidence_ids
        )
        return self._monitor.update(
            forecast_id,
            probability,
            evidence,
            reason=reason,
        )

    def resolve(
        self,
        forecast_id: ForecastId,
        value: ForecastResolutionValue,
        resolver: str,
        evidence_ids: tuple[EvidenceId, ...],
        *,
        ambiguity_notes: str | None = None,
    ) -> ForecastResolutionResult:
        forecast = self._forecasts.get(forecast_id)
        evidence = tuple(
            self._research.get_evidence(forecast.forecast.run_id, evidence_id)
            for evidence_id in evidence_ids
        )
        outcome = self._resolve.resolve(
            forecast_id,
            value,
            evidence,
            resolver=resolver,
            ambiguity_notes=ambiguity_notes,
        )
        return ForecastResolutionResult(outcome, self._score.score(outcome.id))


class ForecastRefreshService:
    """Collect fresh workflow evidence before appending a monitored forecast version."""

    def __init__(
        self,
        research: ResearchRepository,
        workflows: ResearchRegistry,
        lifecycle: ForecastLifecycleService,
        clock: Clock,
    ) -> None:
        self._research = research
        self._workflows = workflows
        self._lifecycle = lifecycle
        self._clock = clock

    async def refresh(
        self,
        forecast_id: ForecastId,
        probability: Decimal,
        *,
        reason: str,
    ) -> ForecastVersion:
        forecast = self._lifecycle.show(forecast_id)
        run = self._research.get(forecast.forecast.run_id)
        workflow = self._workflows.get(run.mandate.kind)
        if workflow is None:
            raise CapabilityUnavailableError(
                f"no evidence workflow is registered for {run.mandate.kind.value}"
            )
        plan = self._research.get_plan(run.id)
        refresh_run = _at_refresh_cutoff(run, self._clock.now())
        collection = await workflow.collect(refresh_run, plan)
        if not collection.evidence:
            raise ResearchIncompleteError("forecast refresh produced no new evidence")
        for evidence in collection.evidence:
            self._research.add_evidence(run.id, evidence)
        for calculation in collection.calculations:
            self._research.add_calculation(run.id, calculation)
        return self._lifecycle.monitor(
            forecast_id,
            probability,
            reason,
            tuple(item.id for item in collection.evidence),
        )


def _at_refresh_cutoff(run: ResearchRun, cutoff: datetime) -> ResearchRun:
    if run.mandate.kind is not ResearchMandateType.CRISIS_IMPACT:
        return run
    parameters = dict(run.mandate.parameters)
    parameters["knowledge_cutoff_at"] = cutoff.isoformat()
    mandate = replace(run.mandate, parameters=tuple(sorted(parameters.items())))
    return replace(run, mandate=mandate)
