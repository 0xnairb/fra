import asyncio
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

from fra.adapters.fakes.agent import FakeAgentBackend
from fra.adapters.storage.markdown_exposure_graphs import MarkdownExposureGraphRepository
from fra.adapters.storage.markdown_forecasts import MarkdownForecastRepository
from fra.adapters.storage.markdown_outcomes import MarkdownOutcomeRepository
from fra.adapters.storage.markdown_research import MarkdownResearchRepository
from fra.adapters.storage.markdown_signals import MarkdownSignalRepository
from fra.adapters.storage.workspace import Workspace
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.application.crisis_research import (
    CrisisResearchRequest,
    CrisisResearchService,
    CrisisResearchWorkflow,
)
from fra.application.forecast_service import ForecastLifecycleService
from fra.application.research_orchestrator import ResearchOrchestrator
from fra.application.research_workflows import ResearchRegistry
from fra.application.source_platform import SourceRegistry, SourceRouter
from fra.domain.documents import DocumentCapabilities
from fra.domain.economic import (
    EconomicObservation,
    EconomicSeries,
    EconomicSeriesCapabilities,
    EconomicSeriesRequest,
)
from fra.domain.forecasts import ForecastResolutionValue
from fra.domain.regulatory import CompanyFact
from fra.domain.research import Evidence, ResearchMandateType, ResearchRunState
from fra.domain.shared import FailureKind, HealthState, HealthStatus
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    DataKind,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    SourceRole,
    UsageProfile,
)
from fra.ports.agent_backend import StructuredAgentOutput

FIXTURE = Path(__file__).parents[1] / "fixtures" / "historical" / "oil_fertilizer_2022.json"


def test_frozen_crisis_case_issues_monitors_resolves_and_scores_from_markdown(
    tmp_path: Path,
) -> None:
    case = json.loads(FIXTURE.read_text())
    cutoff = datetime.fromisoformat(case["knowledge_cutoff_at"].replace("Z", "+00:00"))
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    research = MarkdownResearchRepository(workspace)
    signals = MarkdownSignalRepository(workspace)
    forecasts = MarkdownForecastRepository(workspace)
    outcomes = MarkdownOutcomeRepository(workspace)
    graphs = MarkdownExposureGraphRepository(workspace)
    clock = FixedClock(cutoff)
    ids = SequenceIdGenerator()
    sources = _crisis_sources(case, cutoff)
    workflows = ResearchRegistry()
    workflows.register(
        ResearchMandateType.CRISIS_IMPACT,
        CrisisResearchWorkflow(
            router=SourceRouter(sources, policy_version="fra.source_policy.v1"),
            sec=_SECProvider(case, cutoff),
            clock=clock,
            ids=ids,
        ),
    )
    orchestrator = ResearchOrchestrator(
        research,
        FakeAgentBackend(results=_agent_outputs(), now=cutoff),
        clock,
        ids,
        workflows=workflows,
        signal_repository=signals,
        forecast_repository=forecasts,
        exposure_graph_repository=graphs,
        working_directory=workspace.root,
    )

    run = asyncio.run(
        CrisisResearchService(orchestrator).start(
            CrisisResearchRequest(cutoff, case["horizon_days"], "1657853")
        )
    )

    assert run.state is ResearchRunState.COMPLETED
    run_dir = workspace.root / f"runs/2022/02/{run.id}"
    report = (run_dir / "report.md").read_text()
    assert "Official facts" in report
    assert "Discovery signals" in report
    assert "Strongest counter-scenario" in report
    assert "Evidence coverage" in report
    issued = forecasts.list()[0]
    assert issued.knowledge_cutoff_at == cutoff
    assert all(
        research.get_evidence(run.id, item).available_at <= cutoff for item in issued.evidence_ids
    )
    assert (workspace.root / f"forecasts/{issued.forecast.id}/v001.md").is_file()
    graph = graphs.list()[0]
    assert all(edge.evidence_ids and edge.invalidation_condition for edge in graph.edges)
    assert (workspace.root / f"exposure-graphs/{graph.id}/v001.md").is_file()

    lifecycle = ForecastLifecycleService(forecasts, outcomes, research, clock, ids)
    clock.advance(timedelta(days=1))
    monitored = lifecycle.monitor(
        issued.forecast.id,
        Decimal("0.75"),
        "Frozen weekly review",
        (issued.evidence_ids[0],),
    )
    assert monitored.version == 2
    clock.advance(timedelta(days=35))
    outcome_evidence = _outcome_evidence(run.id, ids, clock.now(), _descriptor("fixture-outcome"))
    research.add_evidence(run.id, cast(Evidence[object], outcome_evidence))
    resolved = lifecycle.resolve(
        issued.forecast.id,
        ForecastResolutionValue.TRUE,
        "frozen-case-rule-v1",
        (outcome_evidence.id,),
    )
    assert resolved.score.brier_score == Decimal("0.0625")

    restarted_forecasts = MarkdownForecastRepository(workspace)
    restarted_outcomes = MarkdownOutcomeRepository(workspace)
    assert restarted_forecasts.get(issued.forecast.id).version == 2
    assert restarted_outcomes.get_score(resolved.outcome.id) == resolved.score


def test_past_crisis_cutoff_rejects_current_non_vintage_source_values(tmp_path: Path) -> None:
    case = json.loads(FIXTURE.read_text())
    cutoff = datetime.fromisoformat(case["knowledge_cutoff_at"].replace("Z", "+00:00"))
    clock = FixedClock(cutoff + timedelta(days=1))
    ids = SequenceIdGenerator()
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    repository = MarkdownResearchRepository(workspace)
    workflows = ResearchRegistry()
    workflows.register(
        ResearchMandateType.CRISIS_IMPACT,
        CrisisResearchWorkflow(
            router=SourceRouter(
                _crisis_sources(case, cutoff), policy_version="fra.source_policy.v1"
            ),
            sec=_SECProvider(case, cutoff),
            clock=clock,
            ids=ids,
        ),
    )
    orchestrator = ResearchOrchestrator(
        repository,
        FakeAgentBackend(results=(_agent_outputs()[0],), now=clock.now()),
        clock,
        ids,
        workflows=workflows,
    )

    run = asyncio.run(
        CrisisResearchService(orchestrator).start(
            CrisisResearchRequest(cutoff, case["horizon_days"], "1657853")
        )
    )

    assert run.state is ResearchRunState.FAILED
    assert run.failure is not None
    assert run.failure.kind is FailureKind.POINT_IN_TIME_UNAVAILABLE
    assert "snapshot frozen at the cutoff" in run.failure.message


def _crisis_sources(case: dict[str, object], cutoff: datetime) -> SourceRegistry:
    sources = SourceRegistry()
    sources.register(_provider("eia", case, cutoff, ("WCESTUS1",)), roles=(SourceRole.PRIMARY,))
    sources.register(
        _provider(
            "world_bank_pink_sheet",
            case,
            cutoff,
            ("Crude oil, average", "DAP"),
        ),
        roles=(SourceRole.PRIMARY,),
    )
    sources.register(
        _provider("fred_alfred", case, cutoff, ("DCOILWTICO",)),
        roles=(SourceRole.PRIMARY,),
    )
    return sources


def _provider(
    provider_id: str,
    case: dict[str, object],
    cutoff: datetime,
    series_ids: tuple[str, ...],
) -> "_SeriesProvider":
    all_series = cast(dict[str, list[list[str]]], case["series"])
    descriptor = _descriptor(provider_id)
    values = {}
    for series_id in series_ids:
        observations = tuple(
            EconomicObservation(series_id, "GLOBAL", period, Decimal(value))
            for period, value in all_series[series_id]
        )
        values[series_id] = DataEnvelope(
            EconomicSeries(series_id, "GLOBAL", series_id, observations),
            descriptor,
            f"{series_id}:frozen",
            f"https://fixture.test/{provider_id}/{series_id}",
            cutoff,
            cutoff,
            historical_cutoff_at=cutoff if provider_id == "fred_alfred" else None,
            vintage=cutoff.date().isoformat() if provider_id == "fred_alfred" else None,
            content_hash="sha256:" + "1" * 64,
            request_fingerprint="sha256:" + "2" * 64,
        )
    return _SeriesProvider(descriptor, values, cutoff)


class _SeriesProvider:
    def __init__(
        self,
        descriptor: SourceDescriptor,
        values: dict[str, DataEnvelope[EconomicSeries]],
        now: datetime,
    ) -> None:
        self._descriptor = descriptor
        self._values = values
        self._now = now

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> EconomicSeriesCapabilities:
        return EconomicSeriesCapabilities(True, self._descriptor.point_in_time_support)

    async def health(self) -> HealthStatus:
        return HealthStatus(HealthState.HEALTHY, self._now, "frozen fixture")

    async def observations(self, request: EconomicSeriesRequest) -> DataEnvelope[EconomicSeries]:
        return self._values[request.series_id]


class _SECProvider:
    def __init__(self, case: dict[str, object], cutoff: datetime) -> None:
        self._case = cast(dict[str, str], case["company_fact"])
        self._cutoff = cutoff
        self._descriptor = _descriptor("sec_edgar", SourceKind.DOCUMENT)

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> DocumentCapabilities:
        return DocumentCapabilities(True, True, True)

    async def selected_facts(
        self,
        cik: str,
        concepts: tuple[str, ...],
        *,
        point_in_time_at: datetime,
    ) -> tuple[CompanyFact, ...]:
        assert point_in_time_at == self._cutoff
        assert self._case["concept"] in concepts
        return (
            CompanyFact(
                cik.zfill(10),
                self._case["entity_name"],
                "us-gaap",
                self._case["concept"],
                "Cost of revenue",
                "USD",
                Decimal(self._case["value"]),
                date(2021, 1, 1),
                date(2021, 12, 31),
                datetime.fromisoformat(self._case["filed_at"].replace("Z", "+00:00")),
                "10-K",
                "0001657853-22-000010",
            ),
        )


def _descriptor(
    provider_id: str, kind: SourceKind = SourceKind.ECONOMIC_SERIES
) -> SourceDescriptor:
    geographies = {
        "eia": frozenset({"US"}),
        "world_bank_pink_sheet": frozenset({"GLOBAL"}),
        "fred_alfred": frozenset({"US"}),
    }.get(provider_id, frozenset({"GLOBAL", "US"}))
    frequencies = {
        "eia": frozenset({"weekly"}),
        "world_bank_pink_sheet": frozenset({"monthly"}),
        "fred_alfred": frozenset({"daily", "weekly", "monthly"}),
    }.get(provider_id, frozenset())
    return SourceDescriptor(
        provider_id,
        "fixture-v1",
        frozenset({kind}),
        AuthorityClass.OFFICIAL,
        provider_id in {"fred_alfred", "sec_edgar", "fixture-outcome"},
        frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
        RawRetentionPolicy.PERMITTED,
        "https://fixture.test/terms",
        date(2022, 2, 24),
        provider_id,
        geographies=geographies,
        frequencies=frequencies,
    )


def _outcome_evidence(
    run_id: object,
    ids: SequenceIdGenerator,
    available_at: datetime,
    descriptor: SourceDescriptor,
) -> Evidence[EconomicSeries]:
    from fra.domain.ids import ResearchRunId

    assert isinstance(run_id, ResearchRunId)
    series = EconomicSeries(
        "PRESSURE_OUTCOME",
        "GLOBAL",
        "Frozen pressure outcome",
        (EconomicObservation("PRESSURE_OUTCOME", "GLOBAL", "2022-04-01", Decimal("1")),),
    )
    envelope = DataEnvelope(
        series,
        descriptor,
        "outcome:true",
        "https://fixture.test/outcome",
        available_at,
        available_at,
        historical_cutoff_at=available_at,
    )
    return Evidence.from_envelope(
        id=ids.evidence_id(),
        run_id=run_id,
        kind=DataKind.ECONOMIC_SERIES,
        summary="Frozen known outcome",
        envelope=envelope,
        knowledge_cutoff_at=available_at,
        created_at=available_at,
    )


def _agent_outputs() -> tuple[StructuredAgentOutput, ...]:
    return (
        StructuredAgentOutput(
            {
                "objective": "Assess frozen crisis transmission",
                "tasks": (
                    {
                        "task_id": "collect",
                        "description": "Collect point-in-time observations",
                        "depends_on": (),
                    },
                    {
                        "task_id": "calculate",
                        "description": "Calculate crisis pressure",
                        "depends_on": ("collect",),
                    },
                    {
                        "task_id": "challenge",
                        "description": "Challenge the causal scenario",
                        "depends_on": ("calculate",),
                    },
                    {
                        "task_id": "forecast",
                        "description": "Issue the bounded forecast",
                        "depends_on": ("challenge",),
                    },
                ),
                "data_requirements": (
                    {
                        "requirement_id": "official_series",
                        "description": "Official point-in-time energy and price observations",
                        "data_kind": "economic_series",
                        "subject_ids": ("WCESTUS1", "DAP", "DCOILWTICO"),
                        "fields": ("value", "available_at", "vintage"),
                        "geography_or_market": "GLOBAL",
                        "resolution": None,
                        "freshness": None,
                    },
                ),
            }
        ),
        StructuredAgentOutput(
            {
                "claims": (
                    {
                        "statement": "Persisted pressure calculations support the causal scenario.",
                        "materiality": "high",
                        "confidence": "medium",
                        "evidence_ids": ("evidence_0006",),
                        "calculation_ids": ("calculation_0011",),
                        "limitations": ("The fixture case is not a live recommendation.",),
                    },
                ),
                "scenarios": (
                    {
                        "title": "Supported chain",
                        "description": "Physical and price pressure reaches business margins.",
                        "evidence_ids": ("evidence_0006",),
                        "invalidation_conditions": ("official pressure measures normalize",),
                    },
                    {
                        "title": "Inventory relief counter-scenario",
                        "description": "Inventory growth absorbs the disruption.",
                        "evidence_ids": ("evidence_0006",),
                        "invalidation_conditions": ("inventories remain constrained",),
                    },
                ),
                "open_questions": (),
            }
        ),
        StructuredAgentOutput({"passed": True, "issues": ()}),
        StructuredAgentOutput(
            {
                "title": "Frozen crisis case",
                "summary": "The skeptic case is inventory relief and demand destruction.",
                "limitations": ("Fixture case is not a live recommendation.",),
            }
        ),
    )
