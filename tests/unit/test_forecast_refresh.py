import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

from fra.adapters.in_memory.repositories import (
    InMemoryForecastRepository,
    InMemoryOutcomeRepository,
    InMemoryResearchRepository,
)
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.application.forecast_service import ForecastLifecycleService, ForecastRefreshService
from fra.application.research_workflows import (
    ResearchRegistry,
    WorkflowCollection,
    WorkflowFinalization,
)
from fra.domain.forecasts import (
    Forecast,
    ForecastStatus,
    ForecastTrigger,
    ForecastVersion,
    InvalidationCondition,
    ResolutionRule,
)
from fra.domain.ids import EvidenceId, ForecastId, MandateId, PlanId, ResearchRunId
from fra.domain.research import (
    Evidence,
    ResearchDataRequirement,
    ResearchMandate,
    ResearchMandateType,
    ResearchPlan,
    ResearchPlanTask,
    ResearchRun,
)
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    DataKind,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)
from fra.ports.repositories import ResearchReport

NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)
OLD_CUTOFF = datetime(2022, 2, 24, 23, 59, tzinfo=UTC)


class _RefreshWorkflow:
    def __init__(self) -> None:
        self.cutoff: str | None = None

    def missing_inputs(self, mandate: ResearchMandate) -> tuple[str, ...]:
        return ()

    async def collect(self, run: ResearchRun, plan: ResearchPlan) -> WorkflowCollection:
        self.cutoff = dict(run.mandate.parameters)["knowledge_cutoff_at"]
        return WorkflowCollection(
            (cast(Evidence[object], _evidence(run.id)),), (), {"refresh": True}
        )

    def finalize(self, run: ResearchRun, synthesis: dict[str, object]) -> WorkflowFinalization:
        return WorkflowFinalization(ResearchReport("unused", "unused"))


def test_forecast_refresh_collects_and_persists_new_evidence_at_current_cutoff() -> None:
    research = InMemoryResearchRepository()
    forecasts = InMemoryForecastRepository()
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator(start=100)
    run = _run()
    research.create(run)
    research.save_plan(run.id, _plan(run.id))
    forecasts.save(_forecast(run.id))
    workflow = _RefreshWorkflow()
    workflows = ResearchRegistry()
    workflows.register(ResearchMandateType.CRISIS_IMPACT, workflow)
    lifecycle = ForecastLifecycleService(
        forecasts, InMemoryOutcomeRepository(), research, clock, ids
    )
    service = ForecastRefreshService(research, workflows, lifecycle, clock)

    refreshed = asyncio.run(
        service.refresh(
            ForecastId("forecast_fixture"),
            Decimal("0.60"),
            reason="Fresh official observations",
        )
    )

    assert workflow.cutoff == NOW.isoformat()
    assert refreshed.version == 2
    assert refreshed.evidence_ids == (EvidenceId("evidence_refresh"),)
    assert research.get_evidence(run.id, EvidenceId("evidence_refresh")).available_at == NOW


def _run() -> ResearchRun:
    mandate = ResearchMandate(
        MandateId("mandate_fixture"),
        ResearchMandateType.CRISIS_IMPACT,
        "Fixture crisis forecast",
        OLD_CUTOFF,
        parameters=(("knowledge_cutoff_at", OLD_CUTOFF.isoformat()), ("horizon_days", "30")),
    )
    return ResearchRun.create(ResearchRunId("run_fixture"), mandate, OLD_CUTOFF)


def _plan(run_id: ResearchRunId) -> ResearchPlan:
    return ResearchPlan(
        PlanId("plan_fixture"),
        run_id,
        "Refresh official indicators",
        (ResearchPlanTask("refresh", "Refresh official indicators"),),
        (
            ResearchDataRequirement(
                "official_series",
                "Official economic observations",
                DataKind.ECONOMIC_SERIES,
                ("economic:fixture",),
                ("value",),
            ),
        ),
        OLD_CUTOFF,
    )


def _forecast(run_id: ResearchRunId) -> ForecastVersion:
    forecast = Forecast(
        ForecastId("forecast_fixture"),
        run_id,
        "Will the pressure persist?",
        "Pressure persists.",
        ForecastTrigger("Official indicators remain elevated"),
        ResolutionRule(1, "Resolve against the official series", "fixture"),
        OLD_CUTOFF,
    )
    return ForecastVersion(
        forecast,
        1,
        Decimal("0.50"),
        OLD_CUTOFF,
        OLD_CUTOFF,
        NOW + timedelta(days=30),
        (EvidenceId("evidence_original"),),
        (InvalidationCondition("Indicators normalize"),),
        "indicator -> pressure",
        ("pressure normalizes",),
        ForecastStatus.ACTIVE,
    )


def _evidence(run_id: ResearchRunId) -> Evidence[str]:
    descriptor = SourceDescriptor(
        "fixture",
        "1",
        frozenset({SourceKind.ECONOMIC_SERIES}),
        AuthorityClass.OFFICIAL,
        True,
        frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
        RawRetentionPolicy.PERMITTED,
        "https://fixture.test/terms",
        date(2026, 1, 1),
        "fixture",
    )
    envelope = DataEnvelope(
        "fresh evidence",
        descriptor,
        "record-refresh",
        "fixture://refresh",
        NOW,
        NOW,
    )
    return Evidence(
        EvidenceId("evidence_refresh"),
        run_id,
        DataKind.ECONOMIC_SERIES,
        "Fresh official evidence",
        envelope,
        NOW,
        NOW,
    )
