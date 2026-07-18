"""Provider-independent dashboard projection assembled only from repositories."""

from dataclasses import dataclass
from datetime import datetime

from fra.domain.shared import ArtifactKind, ArtifactRef
from fra.domain.signals import Confidence, SignalStance, SignalStatus, SignalStrength
from fra.domain.time import as_utc
from fra.ports.repositories import (
    ExposureGraphRepository,
    ForecastRepository,
    OutcomeRepository,
    ResearchRepository,
    SignalRepository,
    SourceStatusRepository,
)


@dataclass(frozen=True, slots=True)
class DashboardSignal:
    signal_id: str
    subject: str
    stance: SignalStance
    strength: SignalStrength
    confidence: Confidence
    horizon: str
    freshness: str
    status: SignalStatus
    artifact: ArtifactRef


@dataclass(frozen=True, slots=True)
class DashboardRun:
    run_id: str
    question: str
    state: str
    updated_at: datetime
    artifact: ArtifactRef


@dataclass(frozen=True, slots=True)
class DashboardSource:
    provider_id: str
    role: str
    freshness: str
    health: str
    quota_warning: str
    capability_summary: str
    artifact: ArtifactRef


@dataclass(frozen=True, slots=True)
class DashboardForecast:
    forecast_id: str
    question: str
    probability: str
    horizon_end: datetime
    updated_at: datetime
    state: str
    score: str
    artifact: ArtifactRef


@dataclass(frozen=True, slots=True)
class DashboardRisk:
    graph_id: str
    event: str
    transmission_path: str
    exposed_subjects: str
    severity: str
    next_check: str
    artifact: ArtifactRef


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    generated_at: datetime
    signals: tuple[DashboardSignal, ...]
    recent_runs: tuple[DashboardRun, ...]
    sources: tuple[DashboardSource, ...] = ()
    forecasts: tuple[DashboardForecast, ...] = ()
    risks: tuple[DashboardRisk, ...] = ()


class DashboardService:
    def __init__(
        self,
        research_repository: ResearchRepository,
        signal_repository: SignalRepository,
        source_status_repository: SourceStatusRepository | None = None,
        forecast_repository: ForecastRepository | None = None,
        outcome_repository: OutcomeRepository | None = None,
        exposure_graph_repository: ExposureGraphRepository | None = None,
    ) -> None:
        self._research = research_repository
        self._signals = signal_repository
        self._source_status = source_status_repository
        self._forecasts = forecast_repository
        self._outcomes = outcome_repository
        self._graphs = exposure_graph_repository

    def snapshot(self, generated_at: datetime) -> DashboardSnapshot:
        generated_at = as_utc(generated_at, field="generated_at")
        signals = tuple(
            DashboardSignal(
                signal_id=str(signal.id),
                subject=", ".join(signal.subject_ids),
                stance=signal.stance,
                strength=signal.strength,
                confidence=signal.confidence,
                horizon=signal.horizon,
                freshness=(
                    "unknown"
                    if signal.next_review_at is None
                    else "stale"
                    if generated_at > signal.next_review_at
                    else "current"
                ),
                status=signal.status,
                artifact=ArtifactRef(
                    ArtifactKind.SIGNAL,
                    f"signals/{signal.id}/v{signal.version:03d}.md",
                ),
            )
            for signal in self._signals.list()
        )
        recent_runs = tuple(
            DashboardRun(
                run_id=str(summary.id),
                question=summary.question,
                state=summary.state.value,
                updated_at=summary.updated_at,
                artifact=summary.artifact
                or ArtifactRef(
                    ArtifactKind.RESEARCH_RUN,
                    f"runs/{summary.created_at.year:04d}/{summary.created_at.month:02d}/"
                    f"{summary.id}/run.md",
                ),
            )
            for summary in self._research.list()
        )
        sources: tuple[DashboardSource, ...] = ()
        if self._source_status is not None:
            sources = tuple(
                DashboardSource(
                    provider_id=status.provider_id,
                    role=",".join(role.value for role in status.roles) or "configured",
                    freshness="last explicit check",
                    health=status.health.state.value,
                    quota_warning=status.quota_warning or "none",
                    capability_summary=(
                        "; ".join(status.capability_warnings)
                        if status.capability_warnings
                        else "validated"
                    ),
                    artifact=ArtifactRef(
                        ArtifactKind.SOURCE_STATUS,
                        f"source-status/{status.provider_id}.md",
                    ),
                )
                for status in self._source_status.list()
            )
        forecasts: tuple[DashboardForecast, ...] = ()
        if self._forecasts is not None:
            outcomes = self._outcomes.list() if self._outcomes is not None else ()
            outcomes_by_forecast = {item.forecast_id: item for item in outcomes}
            forecasts = tuple(
                DashboardForecast(
                    forecast_id=str(forecast.forecast.id),
                    question=forecast.forecast.question,
                    probability=str(forecast.probability),
                    horizon_end=forecast.horizon_end,
                    updated_at=forecast.issued_at,
                    state=(
                        "resolved"
                        if forecast.forecast.id in outcomes_by_forecast
                        else forecast.status.value
                    ),
                    score=_score_for(
                        outcomes_by_forecast.get(forecast.forecast.id), self._outcomes
                    ),
                    artifact=ArtifactRef(
                        ArtifactKind.FORECAST,
                        f"forecasts/{forecast.forecast.id}/v{forecast.version:03d}.md",
                    ),
                )
                for forecast in self._forecasts.list()
            )
        risks: tuple[DashboardRisk, ...] = ()
        if self._graphs is not None:
            risks = tuple(
                DashboardRisk(
                    graph_id=str(graph.id),
                    event=graph.title,
                    transmission_path=" -> ".join(
                        f"{edge.from_node}:{edge.relationship}:{edge.to_node}"
                        for edge in graph.edges
                    ),
                    exposed_subjects=", ".join(sorted({edge.to_node for edge in graph.edges})),
                    severity=_severity(max(edge.confidence for edge in graph.edges)),
                    next_check="explicit monitor",
                    artifact=ArtifactRef(
                        ArtifactKind.EXPOSURE_GRAPH,
                        f"exposure-graphs/{graph.id}/v{graph.version:03d}.md",
                    ),
                )
                for graph in self._graphs.list()
            )
        return DashboardSnapshot(
            generated_at=generated_at,
            signals=signals,
            recent_runs=recent_runs,
            sources=sources,
            forecasts=forecasts,
            risks=risks,
        )


def _score_for(outcome: object, repository: OutcomeRepository | None) -> str:
    from fra.domain.forecasts import ForecastOutcome

    if not isinstance(outcome, ForecastOutcome) or repository is None:
        return "unresolved"
    score = repository.get_score(outcome.id)
    if score is None:
        return "unscored"
    return "ambiguous" if score.brier_score is None else str(score.brier_score)


def _severity(confidence: object) -> str:
    from decimal import Decimal

    assert isinstance(confidence, Decimal)
    if confidence >= Decimal("0.75"):
        return "high"
    if confidence >= Decimal("0.5"):
        return "medium"
    return "low"
