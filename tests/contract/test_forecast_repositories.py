from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fra.adapters.in_memory.repositories import (
    InMemoryExposureGraphRepository,
    InMemoryForecastRepository,
    InMemoryOutcomeRepository,
)
from fra.adapters.storage.markdown_exposure_graphs import MarkdownExposureGraphRepository
from fra.adapters.storage.markdown_forecasts import MarkdownForecastRepository
from fra.adapters.storage.markdown_outcomes import MarkdownOutcomeRepository
from fra.adapters.storage.workspace import Workspace
from fra.domain.errors import RepositoryConflictError
from fra.domain.forecasts import (
    ExposureEdge,
    ExposureGraph,
    ExposureNode,
    ExposureNodeKind,
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
from fra.domain.ids import (
    EvidenceId,
    ExposureGraphId,
    ForecastId,
    ForecastScoreId,
    OutcomeId,
    ResearchRunId,
)
from fra.ports.repositories import (
    ExposureGraphRepository,
    ForecastRepository,
    OutcomeRepository,
)

NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)


@pytest.mark.parametrize("kind", ["memory", "markdown"])
def test_forecast_outcome_and_graph_repository_contract(kind: str, tmp_path: Path) -> None:
    forecasts, outcomes, graphs = _repositories(kind, tmp_path)
    first = _forecast()
    forecasts.save(first)

    with pytest.raises(RepositoryConflictError):
        forecasts.save(first)
    second = replace(
        first,
        version=2,
        probability=Decimal("0.55"),
        issued_at=NOW + timedelta(days=1),
        knowledge_cutoff_at=NOW + timedelta(days=1),
        status=ForecastStatus.MONITORING,
        supersedes_version=1,
        update_reason="New official observation",
    )
    forecasts.save(second)
    assert forecasts.get(first.forecast.id, 1).probability == Decimal("0.35")
    assert forecasts.get(first.forecast.id).probability == Decimal("0.55")
    assert forecasts.list() == (second,)

    outcome = ForecastOutcome(
        id=OutcomeId("outcome_0001"),
        forecast_id=first.forecast.id,
        forecast_version=2,
        resolved_at=NOW + timedelta(days=30),
        value=ForecastResolutionValue.TRUE,
        evidence_ids=(EvidenceId("evidence_0002"),),
        rule_version=1,
        resolver="fixture",
    )
    outcomes.save(outcome)
    score = ForecastScore(
        id=ForecastScoreId("score_0001"),
        outcome_id=outcome.id,
        forecast_id=outcome.forecast_id,
        forecast_version=2,
        brier_score=Decimal("0.2025"),
        scored_at=NOW + timedelta(days=30),
    )
    outcomes.save_score(score)
    assert outcomes.get(outcome.id) == outcome
    assert outcomes.get_score(outcome.id) == score

    graph = _graph()
    graphs.save(graph)
    assert graphs.get(graph.id) == graph


def _repositories(
    kind: str, tmp_path: Path
) -> tuple[ForecastRepository, OutcomeRepository, ExposureGraphRepository]:
    if kind == "memory":
        return (
            InMemoryForecastRepository(),
            InMemoryOutcomeRepository(),
            InMemoryExposureGraphRepository(),
        )
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    return (
        MarkdownForecastRepository(workspace),
        MarkdownOutcomeRepository(workspace),
        MarkdownExposureGraphRepository(workspace),
    )


def _forecast() -> ForecastVersion:
    forecast = Forecast(
        id=ForecastId("forecast_0001"),
        run_id=ResearchRunId("run_0001"),
        question="Will the event occur?",
        hypothesis="The event occurs.",
        trigger=ForecastTrigger("Official indicator crosses threshold"),
        resolution_rule=ResolutionRule(1, "Use the official observation.", "fixture"),
        created_at=NOW,
    )
    return ForecastVersion(
        forecast=forecast,
        version=1,
        probability=Decimal("0.35"),
        issued_at=NOW,
        knowledge_cutoff_at=NOW,
        horizon_end=NOW + timedelta(days=30),
        evidence_ids=(EvidenceId("evidence_0001"),),
        invalidation_conditions=(InvalidationCondition("Indicator reverses"),),
        transmission_path="indicator -> event",
        alternatives=("Event does not occur",),
        status=ForecastStatus.ACTIVE,
    )


def _graph() -> ExposureGraph:
    return ExposureGraph(
        id=ExposureGraphId("graph_0001"),
        version=1,
        title="Fixture exposure graph",
        nodes=(
            ExposureNode("event:fixture", ExposureNodeKind.EVENT, "Fixture event"),
            ExposureNode("industry:fixture", ExposureNodeKind.INDUSTRY, "Fixture industry"),
        ),
        edges=(
            ExposureEdge(
                from_node="event:fixture",
                to_node="industry:fixture",
                relationship="affects",
                direction="negative",
                expected_lag="weeks",
                confidence=Decimal("0.6"),
                jurisdiction="GLOBAL",
                evidence_ids=(EvidenceId("evidence_0001"),),
                invalidation_condition="Impact does not materialize",
            ),
        ),
        created_at=NOW,
    )
