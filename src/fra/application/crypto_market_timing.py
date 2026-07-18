"""Bounded BTC/ETH market-timing workflow with deterministic analytics."""

import json
from dataclasses import dataclass, field, replace
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TypedDict, cast

from fra.application.research_orchestrator import ResearchOrchestrator
from fra.application.research_workflows import WorkflowCollection, WorkflowFinalization
from fra.application.source_platform import SourceRouter
from fra.domain.analytics import Calculation, CryptoMarketMetrics, crypto_market_metrics
from fra.domain.errors import (
    CapabilityUnavailableError,
    DomainValidationError,
    ResearchIncompleteError,
)
from fra.domain.ids import CalculationId, EvidenceId, InstrumentId
from fra.domain.instruments import Currency, InstrumentRef
from fra.domain.market_data import HistoryRequest, InstrumentQuery, MarketSeries
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
    RoutingDecision,
    UsageProfile,
)
from fra.ports.clock import Clock
from fra.ports.ids import IdGenerator
from fra.ports.market_data import MarketDataProvider
from fra.ports.repositories import ResearchReport


class CryptoRiskTolerance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class _AssetRecord(TypedDict):
    subject_id: str
    evidence_id: str
    calculation_id: str
    total_return: str
    annualized_volatility: str
    current_drawdown: str
    maximum_drawdown: str
    observation_count: int


@dataclass(frozen=True, slots=True)
class CryptoResearchRequest:
    horizon_days: int | None
    risk_tolerance: CryptoRiskTolerance | None
    currency: Currency = field(default_factory=lambda: Currency("USD"))
    lookback_days: int = 365

    def __post_init__(self) -> None:
        if self.horizon_days is not None and self.horizon_days <= 0:
            raise DomainValidationError("crypto horizon days must be positive")
        if not 30 <= self.lookback_days <= 365:
            raise DomainValidationError("crypto lookback must be between 30 and 365 days")


class CryptoResearchService:
    def __init__(self, orchestrator: ResearchOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def start(self, request: CryptoResearchRequest) -> ResearchRun:
        parameters = [
            ("asset_scope", "bitcoin,ethereum"),
            ("currency", request.currency.code),
            ("lookback_days", str(request.lookback_days)),
        ]
        unresolved: list[str] = []
        if request.horizon_days is None:
            unresolved.append("investment horizon is required")
        else:
            parameters.append(("horizon_days", str(request.horizon_days)))
        if request.risk_tolerance is None:
            unresolved.append("risk tolerance is required")
        else:
            parameters.append(("risk_tolerance", request.risk_tolerance.value))
        return await self._orchestrator.start(
            "Assess the current BTC and ETH market regime for the declared horizon and risk.",
            ResearchMandateType.CRYPTO_MARKET_TIMING,
            user_facts=tuple(f"{name}={value}" for name, value in parameters),
            unresolved_questions=tuple(unresolved),
            horizon=(f"{request.horizon_days} days" if request.horizon_days is not None else None),
            parameters=tuple(parameters),
        )


class CryptoMarketTimingWorkflow:
    def __init__(
        self,
        router: SourceRouter,
        clock: Clock,
        ids: IdGenerator,
        *,
        usage_profile: UsageProfile = UsageProfile.LOCAL_PERSONAL_RESEARCH,
    ) -> None:
        self._router = router
        self._clock = clock
        self._ids = ids
        self._usage_profile = usage_profile

    def missing_inputs(self, mandate: ResearchMandate) -> tuple[str, ...]:
        parameters = dict(mandate.parameters)
        missing = []
        if "horizon_days" not in parameters:
            missing.append("investment horizon")
        if "risk_tolerance" not in parameters:
            missing.append("risk tolerance")
        return tuple(missing)

    async def collect(self, run: ResearchRun, plan: ResearchPlan) -> WorkflowCollection:
        if not any(item.data_kind is DataKind.MARKET_SERIES for item in plan.data_requirements):
            raise ResearchIncompleteError("crypto plan requires typed market-series evidence")
        parameters = dict(run.mandate.parameters)
        lookback_days = int(parameters["lookback_days"])
        currency = Currency(parameters["currency"])
        now = self._clock.now()
        start_at = now - timedelta(days=lookback_days)
        subject_ids = (InstrumentId("crypto:bitcoin"), InstrumentId("crypto:ethereum"))
        requirement = EvidenceRequirement(
            data_kind=DataKind.MARKET_SERIES,
            subject_ids=subject_ids,
            allowed_usage_profile=self._usage_profile,
            fields=("price", "market_cap", "volume"),
            geography_or_market="CRYPTO",
            start_at=start_at,
            end_at=now,
            resolution="daily",
            maximum_age=timedelta(hours=1),
            minimum_authority=AuthorityClass.AGGREGATOR,
        )
        evidence: list[Evidence[object]] = []
        calculations: list[Calculation] = []
        assets: list[dict[str, object]] = []
        routing: dict[str, object] = {}
        attributions: set[str] = set()
        for query in ("bitcoin", "ethereum"):

            async def fetch(
                adapter: object, query: str = query
            ) -> tuple[InstrumentRef, DataEnvelope[MarketSeries]]:
                provider = cast(MarketDataProvider, adapter)
                matches = await provider.resolve_instrument(InstrumentQuery(query))
                if len(matches) != 1:
                    raise CapabilityUnavailableError(
                        f"could not uniquely resolve crypto asset: {query}"
                    )
                instrument = replace(matches[0].instrument, currency=currency)
                envelope = await provider.history(
                    HistoryRequest(instrument, start_at, now, "daily")
                )
                return instrument, envelope

            execution = await self._router.execute(requirement, fetch)
            routing[query] = _routing_record(execution.decision)
            selected_asset: dict[str, object] | None = None
            for routed in execution.values:
                instrument, envelope = routed.value
                if envelope.descriptor.required_attribution:
                    attributions.add(envelope.descriptor.required_attribution)
                if envelope.is_stale or now - envelope.value.observations[
                    -1
                ].observed_at > timedelta(days=2):
                    raise ResearchIncompleteError(f"{query} market history is stale")
                evidence_id = self._ids.evidence_id()
                item = Evidence.from_envelope(
                    id=evidence_id,
                    run_id=run.id,
                    kind=DataKind.MARKET_SERIES,
                    summary=(
                        f"{routed.provider_id} {query} daily market history in {currency.code}"
                    ),
                    envelope=envelope,
                    knowledge_cutoff_at=now,
                    created_at=now,
                )
                evidence.append(cast(Evidence[object], item))
                if selected_asset is not None:
                    continue
                metrics = crypto_market_metrics(envelope.value)
                calculation = _calculation(
                    self._ids.calculation_id(), run, evidence_id, metrics, lookback_days, now
                )
                calculations.append(calculation)
                selected_asset = {
                    "subject_id": str(instrument.id),
                    "evidence_id": str(evidence_id),
                    "calculation_id": str(calculation.id),
                    "total_return": str(metrics.total_return),
                    "annualized_volatility": str(metrics.annualized_volatility),
                    "current_drawdown": str(metrics.current_drawdown),
                    "maximum_drawdown": str(metrics.maximum_drawdown),
                    "observation_count": metrics.observation_count,
                }
            if selected_asset is None:
                raise CapabilityUnavailableError(
                    f"routing produced no usable market history for {query}"
                )
            assets.append(selected_asset)
        return WorkflowCollection(
            evidence=tuple(evidence),
            calculations=tuple(calculations),
            durable_result={
                "assets": assets,
                "routing": routing,
                "attribution": sorted(attributions),
                "usage_policy": sorted(
                    {
                        item.envelope.usage_policy_id
                        for item in evidence
                        if item.envelope.usage_policy_id is not None
                    }
                ),
            },
        )

    def finalize(self, run: ResearchRun, synthesis: dict[str, object]) -> WorkflowFinalization:
        collection = _collection_checkpoint(run)
        raw_assets = collection.get("assets")
        if not isinstance(raw_assets, list) or len(raw_assets) != 2:
            raise ResearchIncompleteError("crypto finalization requires BTC and ETH evidence")
        assets = [_asset_record(item) for item in raw_assets]
        average_return = sum(
            (Decimal(item["total_return"]) for item in assets), Decimal(0)
        ) / Decimal(len(assets))
        stance = (
            SignalStance.BULLISH
            if average_return > Decimal("0.10")
            else SignalStance.BEARISH
            if average_return < Decimal("-0.10")
            else SignalStance.MIXED
        )
        absolute_return = abs(average_return)
        strength = (
            SignalStrength.STRONG
            if absolute_return >= Decimal("0.20")
            else SignalStrength.MODERATE
            if absolute_return >= Decimal("0.05")
            else SignalStrength.WEAK
        )
        confidence = (
            Confidence.MEDIUM
            if all(int(item["observation_count"]) >= 30 for item in assets)
            else Confidence.LOW
        )
        now = self._clock.now()
        evidence_ids = tuple(EvidenceId(item["evidence_id"]) for item in assets)
        calculation_ids = tuple(item["calculation_id"] for item in assets)
        signal = Signal(
            id=self._ids.signal_id(),
            version=1,
            run_id=run.id,
            subject_ids=tuple(item["subject_id"] for item in assets),
            summary=(
                f"BTC/ETH market regime is {stance.value} over the declared lookback; "
                "this is an observation, not an action instruction."
            ),
            stance=stance,
            strength=strength,
            confidence=confidence,
            horizon=run.mandate.horizon or "unspecified",
            issued_at=now,
            knowledge_cutoff_at=now,
            evidence_ids=evidence_ids,
            calculation_ids=calculation_ids,
            invalidation_conditions=(
                "Market evidence becomes older than two days",
                "BTC or ETH drawdown or return regime changes materially",
            ),
            status=SignalStatus.ACTIVE,
            rationale="Deterministic BTC and ETH returns, volatility, and drawdowns.",
            limitations=(
                "CoinGecko is an aggregator and not an exchange-authoritative price source.",
                "Price history alone cannot establish suitability or predict future returns.",
            ),
            warnings=("Data provided by CoinGecko",),
            next_review_at=now + timedelta(days=1),
        )
        report = ResearchReport(
            title="BTC and ETH Market-Timing Research",
            body=_render_report(run, assets, collection, synthesis, signal),
        )
        return WorkflowFinalization(report=report, signal=signal)


def _calculation(
    calculation_id: CalculationId,
    run: ResearchRun,
    evidence_id: EvidenceId,
    metrics: CryptoMarketMetrics,
    lookback_days: int,
    created_at: object,
) -> Calculation:
    from datetime import datetime

    assert isinstance(created_at, datetime)
    return Calculation(
        id=calculation_id,
        run_id=run.id,
        name="crypto_market_metrics",
        formula_version=1,
        input_evidence_ids=(evidence_id,),
        parameters=(("lookback_days", str(lookback_days)), ("annualization_periods", "365")),
        results=(
            ("total_return", metrics.total_return),
            ("annualized_volatility", metrics.annualized_volatility),
            ("current_drawdown", metrics.current_drawdown),
            ("maximum_drawdown", metrics.maximum_drawdown),
            ("observation_count", Decimal(metrics.observation_count)),
        ),
        created_at=created_at,
    )


def _routing_record(decision: RoutingDecision) -> dict[str, object]:
    return {
        "policy_version": decision.policy_version,
        "candidates": [
            {
                "provider_id": item.provider_id,
                "selected_role": item.selected_role.value if item.selected_role else None,
                "exclusions": list(item.exclusions),
            }
            for item in decision.candidates
        ],
        "warnings": list(decision.warnings),
    }


def _collection_checkpoint(run: ResearchRun) -> dict[str, object]:
    checkpoint = next((item for item in run.stage_checkpoints if item.stage == "collect"), None)
    if checkpoint is None:
        raise ResearchIncompleteError("crypto collection checkpoint is missing")
    value = json.loads(checkpoint.result_json)
    if not isinstance(value, dict):
        raise ResearchIncompleteError("crypto collection checkpoint is invalid")
    return value


def _asset_record(value: object) -> _AssetRecord:
    if not isinstance(value, dict):
        raise ResearchIncompleteError("crypto asset calculation record is invalid")
    required = {
        "subject_id",
        "evidence_id",
        "calculation_id",
        "total_return",
        "annualized_volatility",
        "current_drawdown",
        "maximum_drawdown",
        "observation_count",
    }
    if not required <= value.keys():
        raise ResearchIncompleteError("crypto asset calculation record is incomplete")
    string_fields = required - {"observation_count"}
    if any(not isinstance(value[key], str) for key in string_fields) or not isinstance(
        value["observation_count"], int
    ):
        raise ResearchIncompleteError("crypto asset calculation record has invalid values")
    return _AssetRecord(
        subject_id=cast(str, value["subject_id"]),
        evidence_id=cast(str, value["evidence_id"]),
        calculation_id=cast(str, value["calculation_id"]),
        total_return=cast(str, value["total_return"]),
        annualized_volatility=cast(str, value["annualized_volatility"]),
        current_drawdown=cast(str, value["current_drawdown"]),
        maximum_drawdown=cast(str, value["maximum_drawdown"]),
        observation_count=value["observation_count"],
    )


def _render_report(
    run: ResearchRun,
    assets: list[_AssetRecord],
    collection: dict[str, object],
    synthesis: dict[str, object],
    signal: Signal,
) -> str:
    parameters = dict(run.mandate.parameters)
    rows = "\n".join(
        "| {subject} | {total_return} | {volatility} | {drawdown} | "
        "[{evidence}](evidence/{evidence}.md) | "
        "[{calculation}](calculations/{calculation}.md) |".format(
            subject=item["subject_id"],
            total_return=item["total_return"],
            volatility=item["annualized_volatility"],
            drawdown=item["maximum_drawdown"],
            evidence=item["evidence_id"],
            calculation=item["calculation_id"],
        )
        for item in assets
    )
    routing = collection.get("routing", {})
    agent_summary = str(synthesis.get("summary", "No agent synthesis available."))
    return (
        "# BTC and ETH Market-Timing Research\n\n"
        "## Declared Inputs\n\n"
        f"- Horizon: {run.mandate.horizon}\n"
        f"- Risk tolerance: {parameters['risk_tolerance']}\n"
        f"- Currency: {parameters['currency']}\n"
        f"- Lookback: {parameters['lookback_days']} days\n\n"
        "## Deterministic Evidence and Calculations\n\n"
        "| Subject | Total return | Annualized volatility | Maximum drawdown | "
        "Evidence | Calculation |\n"
        "| --- | ---: | ---: | ---: | --- | --- |\n"
        f"{rows}\n\n"
        "## Signal\n\n"
        f"{signal.summary} Confidence: {signal.confidence.value}.\n\n"
        "## Scenario Synthesis\n\n"
        f"{agent_summary} Supporting material: "
        + ", ".join(
            f"[{item['calculation_id']}](calculations/{item['calculation_id']}.md)"
            for item in assets
        )
        + ".\n\n"
        "## Source Routing and Attribution\n\n"
        f"```json\n{json.dumps(routing, indent=2, sort_keys=True)}\n```\n\n"
        f"- Attribution: {collection.get('attribution')}\n"
        f"- Usage policy: {collection.get('usage_policy')}\n\n"
        "## Risk Limits and Invalidation\n\n"
        + "\n".join(f"- {item}" for item in signal.invalidation_conditions)
        + "\n\n## Limitations\n\n"
        + "\n".join(f"- {item}" for item in signal.limitations)
        + "\n"
    )
