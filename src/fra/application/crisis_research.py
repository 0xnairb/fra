"""Oil-and-fertilizer crisis research with deterministic exposure and forecast outputs."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol, cast

from fra.application.research_orchestrator import ResearchOrchestrator
from fra.application.research_workflows import WorkflowCollection, WorkflowFinalization
from fra.application.source_platform import SourceRouter
from fra.domain.analytics import Calculation
from fra.domain.crisis import crisis_metrics, rank_business_exposures
from fra.domain.economic import EconomicSeries, EconomicSeriesRequest
from fra.domain.errors import (
    CapabilityUnavailableError,
    LookAheadEvidenceError,
    PointInTimeUnavailableError,
)
from fra.domain.forecasts import (
    ExposureEdge,
    ExposureGraph,
    ExposureNode,
    ExposureNodeKind,
    Forecast,
    ForecastStatus,
    ForecastTrigger,
    ForecastVersion,
    InvalidationCondition,
    ResolutionRule,
)
from fra.domain.ids import EvidenceId, InstrumentId
from fra.domain.regulatory import CompanyFact
from fra.domain.research import (
    Evidence,
    ResearchMandate,
    ResearchMandateType,
    ResearchPlan,
    ResearchRun,
)
from fra.domain.signals import (
    Confidence,
    Signal,
    SignalStance,
    SignalStatus,
    SignalStrength,
)
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    DataKind,
    EvidenceRequirement,
    SourceDescriptor,
    UsageProfile,
)
from fra.ports.clock import Clock
from fra.ports.economic_series import EconomicSeriesProvider
from fra.ports.ids import IdGenerator
from fra.ports.repositories import ResearchReport


class CompanyFactsProvider(Protocol):
    def descriptor(self) -> SourceDescriptor: ...

    async def selected_facts(
        self,
        cik: str,
        concepts: tuple[str, ...],
        *,
        point_in_time_at: datetime,
    ) -> tuple[CompanyFact, ...]: ...


@dataclass(frozen=True, slots=True)
class CrisisResearchRequest:
    knowledge_cutoff_at: datetime | None
    horizon_days: int | None
    company_cik: str = "1657853"

    def __post_init__(self) -> None:
        if self.horizon_days is not None and self.horizon_days <= 0:
            raise ValueError("crisis forecast horizon must be positive")
        if not self.company_cik.strip():
            raise ValueError("crisis company CIK must not be empty")


class CrisisResearchService:
    def __init__(self, orchestrator: ResearchOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def start(self, request: CrisisResearchRequest) -> ResearchRun:
        parameters: list[tuple[str, str]] = [("company_cik", request.company_cik)]
        unresolved = []
        if request.knowledge_cutoff_at is None:
            unresolved.append("knowledge cutoff is required")
        else:
            parameters.append(("knowledge_cutoff_at", request.knowledge_cutoff_at.isoformat()))
        if request.horizon_days is None:
            unresolved.append("forecast horizon is required")
        else:
            parameters.append(("horizon_days", str(request.horizon_days)))
        return await self._orchestrator.start(
            "Assess oil and fertilizer crisis transmission and affected businesses.",
            ResearchMandateType.CRISIS_IMPACT,
            unresolved_questions=tuple(unresolved),
            horizon=f"{request.horizon_days} days" if request.horizon_days else None,
            parameters=tuple(parameters),
        )


class CrisisResearchWorkflow:
    def __init__(
        self,
        *,
        router: SourceRouter,
        sec: CompanyFactsProvider | None,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._router = router
        self._sec = sec
        self._clock = clock
        self._ids = ids

    def missing_inputs(self, mandate: ResearchMandate) -> tuple[str, ...]:
        parameters = dict(mandate.parameters)
        return tuple(
            label
            for field, label in (
                ("knowledge_cutoff_at", "knowledge cutoff"),
                ("horizon_days", "forecast horizon"),
            )
            if field not in parameters
        )

    async def collect(self, run: ResearchRun, plan: ResearchPlan) -> WorkflowCollection:
        if not any(item.data_kind is DataKind.ECONOMIC_SERIES for item in plan.data_requirements):
            raise CapabilityUnavailableError("crisis plan requires typed economic-series evidence")
        parameters = dict(run.mandate.parameters)
        cutoff = datetime.fromisoformat(parameters["knowledge_cutoff_at"])
        start = cutoff - timedelta(days=62)
        requests = (
            (
                "eia_inventory",
                EconomicSeriesRequest(
                    "WCESTUS1", "US", start.date().isoformat(), cutoff.date().isoformat()
                ),
                "weekly",
            ),
            (
                "pink_oil",
                EconomicSeriesRequest(
                    "Crude oil, average",
                    "GLOBAL",
                    start.date().isoformat()[:7],
                    cutoff.date().isoformat()[:7],
                ),
                "monthly",
            ),
            (
                "pink_fertilizer",
                EconomicSeriesRequest(
                    "DAP",
                    "GLOBAL",
                    start.date().isoformat()[:7],
                    cutoff.date().isoformat()[:7],
                ),
                "monthly",
            ),
            (
                "fred_oil_vintage",
                EconomicSeriesRequest(
                    "DCOILWTICO",
                    "US",
                    start.date().isoformat(),
                    cutoff.date().isoformat(),
                    point_in_time_at=cutoff,
                ),
                "daily",
            ),
        )
        evidence: list[Evidence[object]] = []
        series_by_name: dict[str, EconomicSeries] = {}
        evidence_by_name: dict[str, EvidenceId] = {}
        for name, request, resolution in requests:
            requirement = EvidenceRequirement(
                DataKind.ECONOMIC_SERIES,
                (InstrumentId(f"economic:{name}"),),
                UsageProfile.LOCAL_PERSONAL_RESEARCH,
                fields=("value",),
                geography_or_market=request.geography,
                resolution=resolution,
                point_in_time_at=request.point_in_time_at,
                minimum_authority=AuthorityClass.OFFICIAL,
            )

            async def fetch(
                adapter: object, request: EconomicSeriesRequest = request
            ) -> DataEnvelope[EconomicSeries]:
                provider = cast(EconomicSeriesProvider, adapter)
                return await provider.observations(request)

            execution = await self._router.execute(requirement, fetch)
            routed = execution.values[0]
            envelope = routed.value
            if self._clock.now() > cutoff and envelope.historical_cutoff_at != cutoff:
                raise PointInTimeUnavailableError(
                    f"{routed.provider_id} did not return a snapshot frozen at the cutoff"
                )
            if envelope.available_at > cutoff:
                raise LookAheadEvidenceError(f"{routed.provider_id} was unavailable at the cutoff")
            evidence_id = self._ids.evidence_id()
            item = Evidence.from_envelope(
                id=evidence_id,
                run_id=run.id,
                kind=DataKind.ECONOMIC_SERIES,
                summary=f"{routed.provider_id} {name.replace('_', ' ')} observations",
                envelope=envelope,
                knowledge_cutoff_at=cutoff,
                created_at=self._clock.now(),
            )
            evidence.append(cast(Evidence[object], item))
            series_by_name[name] = envelope.value
            evidence_by_name[name] = evidence_id

        facts: tuple[CompanyFact, ...] = ()
        if self._sec is not None:
            facts = await self._sec.selected_facts(
                parameters["company_cik"],
                ("CostOfRevenue",),
                point_in_time_at=cutoff,
            )
            if facts:
                available_at = max(item.filed_at for item in facts)
                facts_envelope = DataEnvelope(
                    facts,
                    self._sec.descriptor(),
                    f"CIK{parameters['company_cik']}:selected-facts",
                    "https://data.sec.gov/api/xbrl/companyfacts/",
                    available_at,
                    self._clock.now(),
                    historical_cutoff_at=cutoff,
                    required_attribution=self._sec.descriptor().required_attribution,
                )
                evidence_id = self._ids.evidence_id()
                evidence.append(
                    cast(
                        Evidence[object],
                        Evidence.from_envelope(
                            id=evidence_id,
                            run_id=run.id,
                            kind=DataKind.DOCUMENT,
                            summary="SEC filing facts available at the knowledge cutoff",
                            envelope=facts_envelope,
                            knowledge_cutoff_at=cutoff,
                            created_at=self._clock.now(),
                        ),
                    )
                )
                evidence_by_name["sec_company_facts"] = evidence_id

        metrics = crisis_metrics(
            series_by_name["pink_oil"],
            series_by_name["pink_fertilizer"],
            series_by_name["eia_inventory"],
        )
        profiles = (
            (
                f"company:cik-{parameters['company_cik']}",
                facts[0].entity_name if facts else "Fertilizer producer",
                "fertilizer",
                "US",
                Decimal("0.90"),
                Decimal("0.55"),
                Decimal("1.0") if facts else Decimal("0.55"),
            ),
            (
                "industry:airlines",
                "Airlines",
                "transportation",
                "GLOBAL",
                Decimal("0.75"),
                Decimal("0.30"),
                Decimal("0.70"),
            ),
            (
                "industry:food-processing",
                "Food processors",
                "consumer staples",
                "GLOBAL",
                Decimal("0.55"),
                Decimal("0.45"),
                Decimal("0.65"),
            ),
        )
        ranking = rank_business_exposures(metrics, profiles)
        calculation_id = self._ids.calculation_id()
        calculation = Calculation(
            calculation_id,
            run.id,
            "oil_fertilizer_crisis_pressure",
            1,
            tuple(evidence_by_name.values()),
            (("cutoff", cutoff.isoformat()),),
            (
                ("oil_price_change", metrics.oil_price_change),
                ("fertilizer_price_change", metrics.fertilizer_price_change),
                ("inventory_change", metrics.inventory_change),
                ("pressure_index", metrics.pressure_index),
            ),
            self._clock.now(),
        )
        return WorkflowCollection(
            tuple(evidence),
            (calculation,),
            {
                "knowledge_cutoff_at": cutoff.isoformat(),
                "evidence_ids": {name: str(value) for name, value in evidence_by_name.items()},
                "calculation_id": str(calculation_id),
                "metrics": {name: str(value) for name, value in calculation.results},
                "events": [
                    {
                        "title": "Official physical and price stress observations",
                        "evidence_class": "official_fact",
                        "available_at": cutoff.isoformat(),
                    }
                ],
                "discovery_signals": [],
                "ranking": [
                    {
                        "subject_id": item.subject_id,
                        "name": item.name,
                        "industry": item.industry,
                        "jurisdiction": item.jurisdiction,
                        "stress_score": str(item.stress_score),
                        "evidence_coverage": str(item.evidence_coverage),
                        "confidence": str(item.confidence),
                    }
                    for item in ranking
                ],
            },
        )

    def finalize(self, run: ResearchRun, synthesis: dict[str, object]) -> WorkflowFinalization:
        collection = _collection(run)
        evidence_map = collection["evidence_ids"]
        metrics = collection["metrics"]
        ranking = collection["ranking"]
        if (
            not isinstance(evidence_map, dict)
            or not isinstance(metrics, dict)
            or not isinstance(ranking, list)
        ):
            raise CapabilityUnavailableError("crisis collection checkpoint is invalid")
        evidence_ids = tuple(EvidenceId(str(value)) for value in evidence_map.values())
        pressure = Decimal(str(metrics["pressure_index"]))
        now = self._clock.now()
        probability = min(Decimal(1), max(Decimal(0), Decimal("0.5") + pressure / Decimal(2)))
        horizon_days = int(dict(run.mandate.parameters)["horizon_days"])
        forecast = ForecastVersion(
            Forecast(
                self._ids.forecast_id(),
                run.id,
                "Will oil-and-fertilizer stress remain elevated through the forecast horizon?",
                "Physical tightness and fertilizer input pressure persist long enough "
                "to affect businesses.",
                ForecastTrigger(
                    "Official price pressure rises while physical inventory fails to offset it"
                ),
                ResolutionRule(
                    1,
                    "Resolve true when the frozen pressure index remains positive at horizon end.",
                    "EIA, World Bank Pink Sheet, and FRED/ALFRED",
                ),
                now,
            ),
            1,
            probability,
            now,
            datetime.fromisoformat(str(collection["knowledge_cutoff_at"])),
            now + timedelta(days=horizon_days),
            evidence_ids,
            (
                InvalidationCondition("Oil and fertilizer prices normalize together"),
                InvalidationCondition("Official inventories rise enough to offset price pressure"),
            ),
            "supply event -> energy/fertilizer prices -> industry costs -> business margins",
            (
                "Inventory relief absorbs the disruption",
                "Demand destruction reverses commodity price pressure",
            ),
            ForecastStatus.ACTIVE,
        )
        graph = _graph(self._ids, evidence_ids, ranking, now)
        signal = Signal(
            id=self._ids.signal_id(),
            version=1,
            run_id=run.id,
            subject_ids=tuple(
                str(item.get("subject_id")) for item in ranking if isinstance(item, dict)
            ),
            summary=(
                "Oil-and-fertilizer pressure is elevated; ranked impacts are scenario stress, "
                "not advice."
            ),
            stance=SignalStance.BEARISH if pressure > 0 else SignalStance.MIXED,
            strength=(
                SignalStrength.STRONG
                if abs(pressure) >= Decimal("0.25")
                else SignalStrength.MODERATE
            ),
            confidence=Confidence.MEDIUM,
            horizon=run.mandate.horizon or "unspecified",
            issued_at=now,
            knowledge_cutoff_at=forecast.knowledge_cutoff_at,
            evidence_ids=evidence_ids,
            invalidation_conditions=tuple(
                item.statement for item in forecast.invalidation_conditions
            ),
            status=SignalStatus.ACTIVE,
            calculation_ids=(str(collection["calculation_id"]),),
            rationale="Deterministic commodity, inventory, vintage, and filing evidence.",
            limitations=(
                "Exposure ranks are stress scenarios, not valuation models.",
                "Current EIA and Pink Sheet values cannot prove historical vintages by themselves.",
            ),
            next_review_at=now + timedelta(days=7),
        )
        report = ResearchReport(
            "Oil and Fertilizer Crisis Research",
            _report(run, collection, synthesis, forecast, graph),
        )
        return WorkflowFinalization(report, signal, (forecast,), (graph,))


def _collection(run: ResearchRun) -> dict[str, object]:
    checkpoint = next((item for item in run.stage_checkpoints if item.stage == "collect"), None)
    if checkpoint is None:
        raise CapabilityUnavailableError("crisis collection checkpoint is missing")
    value = json.loads(checkpoint.result_json)
    if not isinstance(value, dict):
        raise CapabilityUnavailableError("crisis collection checkpoint is invalid")
    return value


def _graph(
    ids: IdGenerator,
    evidence_ids: tuple[EvidenceId, ...],
    ranking: list[object],
    now: datetime,
) -> ExposureGraph:
    company_nodes = tuple(
        ExposureNode(str(item["subject_id"]), ExposureNodeKind.COMPANY, str(item["name"]))
        for item in ranking
        if isinstance(item, dict)
    )
    nodes = (
        ExposureNode("event:supply-stress", ExposureNodeKind.EVENT, "Supply stress"),
        ExposureNode("country:global", ExposureNodeKind.COUNTRY, "Global transmission"),
        ExposureNode("commodity:oil", ExposureNodeKind.COMMODITY, "Crude oil"),
        ExposureNode("commodity:fertilizer", ExposureNodeKind.COMMODITY, "DAP fertilizer"),
        ExposureNode("industry:input-costs", ExposureNodeKind.INDUSTRY, "Input-cost industries"),
        *company_nodes,
    )

    def edge(from_node: str, to_node: str, relationship: str) -> ExposureEdge:
        return ExposureEdge(
            from_node,
            to_node,
            relationship,
            "negative",
            "days-to-months",
            Decimal("0.7"),
            "GLOBAL",
            evidence_ids,
            "Official price and inventory indicators normalize",
        )

    edges = [
        edge("event:supply-stress", "country:global", "propagates"),
        edge("country:global", "commodity:oil", "tightens"),
        edge("country:global", "commodity:fertilizer", "tightens"),
        edge("commodity:oil", "industry:input-costs", "raises costs"),
        edge("commodity:fertilizer", "industry:input-costs", "raises costs"),
    ]
    edges.extend(edge("industry:input-costs", node.id, "stresses") for node in company_nodes)
    return ExposureGraph(
        ids.exposure_graph_id(), 1, "Oil and fertilizer risk watch", nodes, tuple(edges), now
    )


def _report(
    run: ResearchRun,
    collection: dict[str, object],
    synthesis: dict[str, object],
    forecast: ForecastVersion,
    graph: ExposureGraph,
) -> str:
    ranking_value = collection.get("ranking", [])
    ranking = ranking_value if isinstance(ranking_value, list) else []
    rows = "\n".join(
        f"| {item['name']} | {item['industry']} | {item['stress_score']} | "
        f"{item['evidence_coverage']} | {item['confidence']} |"
        for item in ranking
        if isinstance(item, dict)
    )
    return (
        "# Oil and Fertilizer Crisis Research\n\n"
        f"- Frozen knowledge cutoff: {collection['knowledge_cutoff_at']}\n"
        f"- Forecast horizon: {run.mandate.horizon}\n\n"
        "## Evidence classes\n\n"
        "### Official facts\n\n"
        "EIA physical inventory, World Bank commodity benchmarks, ALFRED vintage observations, "
        "and cutoff-filtered SEC facts are persisted as evidence.\n\n"
        "### Discovery signals\n\nNone were used for material claims in this run.\n\n"
        "## Supported causal chain\n\n"
        "Supply stress can tighten oil and fertilizer benchmarks, transmit into industry input "
        "costs, and pressure exposed business margins. Every graph edge includes evidence, "
        "confidence, lag, jurisdiction, and an invalidation condition.\n\n"
        "## Strongest counter-scenario\n\n"
        "Inventory relief and demand destruction can jointly normalize prices before margin "
        "pressure persists. This is the skeptic case and the forecast invalidation path.\n\n"
        "## Affected-business ranking\n\n"
        "| Subject | Industry | Stress | Evidence coverage | Confidence |\n"
        "| --- | --- | ---: | ---: | ---: |\n"
        f"{rows}\n\n"
        "## Leading indicators and monitoring\n\n"
        "- EIA crude inventories: weekly; explicit `fra monitor` review.\n"
        "- Pink Sheet oil and DAP: monthly; review after publication.\n"
        "- ALFRED oil vintage: daily series with cutoff-pinned vintage.\n"
        "- SEC filings: event-driven; refresh only after new filing availability.\n\n"
        "## Forecast\n\n"
        f"Probability {forecast.probability}; artifact "
        f"`forecasts/{forecast.forecast.id}/v001.md`.\n\n"
        "## Exposure graph\n\n"
        f"`exposure-graphs/{graph.id}/v001.md`\n\n"
        "## Agent skeptic synthesis\n\n"
        f"{synthesis.get('summary', 'No additional agent synthesis.')}\n\n"
        "## Limitations\n\n"
        "- Rankings expose coverage and confidence and must not be read as precise valuations.\n"
        "- EIA and Pink Sheet current downloads are not accepted as historical vintages.\n"
    )
