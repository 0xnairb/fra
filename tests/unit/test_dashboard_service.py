from datetime import UTC, datetime
from decimal import Decimal

from fra.adapters.in_memory.repositories import (
    InMemoryForecastRepository,
    InMemoryOutcomeRepository,
    InMemoryResearchRepository,
    InMemorySignalRepository,
)
from fra.application.dashboard_service import DashboardService
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
from fra.domain.ids import (
    EvidenceId,
    ForecastId,
    ForecastScoreId,
    MandateId,
    OutcomeId,
    ResearchRunId,
    SignalId,
)
from fra.domain.research import ResearchMandate, ResearchMandateType, ResearchRun
from fra.domain.signals import Confidence, Signal, SignalStance, SignalStatus, SignalStrength

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def test_dashboard_snapshot_is_provider_independent_and_has_artifact_references() -> None:
    runs = InMemoryResearchRepository()
    signals = InMemorySignalRepository()
    mandate = ResearchMandate(
        id=MandateId("mandate_0001"),
        kind=ResearchMandateType.GENERAL_RESEARCH,
        question="What changed?",
        created_at=NOW,
    )
    run = ResearchRun.create(ResearchRunId("run_0001"), mandate, NOW)
    runs.create(run)
    signals.save(
        Signal(
            id=SignalId("signal_0001"),
            version=1,
            run_id=run.id,
            subject_ids=("crypto:bitcoin",),
            summary="Fixture signal",
            stance=SignalStance.NEUTRAL,
            strength=SignalStrength.MODERATE,
            confidence=Confidence.MEDIUM,
            horizon="3 months",
            issued_at=NOW,
            knowledge_cutoff_at=NOW,
            evidence_ids=(EvidenceId("evidence_0001"),),
            invalidation_conditions=("Fixture changes",),
            status=SignalStatus.ACTIVE,
        )
    )

    snapshot = DashboardService(runs, signals).snapshot(NOW)

    assert snapshot.generated_at == NOW
    assert snapshot.signals[0].artifact.location == "signals/signal_0001/v001.md"
    assert snapshot.recent_runs[0].artifact.location.endswith("run_0001/run.md")


def test_dashboard_keeps_unresolved_and_ambiguous_forecasts_visible() -> None:
    runs = InMemoryResearchRepository()
    signals = InMemorySignalRepository()
    forecasts = InMemoryForecastRepository()
    outcomes = InMemoryOutcomeRepository()
    unresolved = _forecast(ForecastId("forecast_unresolved"))
    ambiguous = _forecast(ForecastId("forecast_ambiguous"))
    forecasts.save(unresolved)
    forecasts.save(ambiguous)
    outcome = ForecastOutcome(
        OutcomeId("outcome_ambiguous"),
        ambiguous.forecast.id,
        1,
        NOW,
        ForecastResolutionValue.AMBIGUOUS,
        (EvidenceId("evidence_0001"),),
        1,
        "fixture",
        "Official facts conflict.",
    )
    outcomes.save(outcome)
    outcomes.save_score(
        ForecastScore(
            ForecastScoreId("score_ambiguous"),
            outcome.id,
            ambiguous.forecast.id,
            1,
            None,
            NOW,
        )
    )

    snapshot = DashboardService(
        runs,
        signals,
        forecast_repository=forecasts,
        outcome_repository=outcomes,
    ).snapshot(NOW)

    projected = {item.forecast_id: (item.state, item.score) for item in snapshot.forecasts}
    assert projected == {
        "forecast_ambiguous": ("resolved", "ambiguous"),
        "forecast_unresolved": ("active", "unresolved"),
    }


def _forecast(forecast_id: ForecastId) -> ForecastVersion:
    forecast = Forecast(
        forecast_id,
        ResearchRunId("run_0001"),
        "Will the fixture event occur?",
        "The fixture event occurs.",
        ForecastTrigger("Official fact crosses threshold"),
        ResolutionRule(1, "Use the official fact.", "fixture"),
        NOW,
    )
    return ForecastVersion(
        forecast,
        1,
        Decimal("0.4"),
        NOW,
        NOW,
        NOW,
        (EvidenceId("evidence_0001"),),
        (InvalidationCondition("Official fact reverses"),),
        "fact -> event",
        ("Event does not occur",),
        ForecastStatus.ACTIVE,
    )
