import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fra.adapters.fakes.agent import FakeAgentBackend
from fra.adapters.fakes.market_data import FakeMarketDataProvider
from fra.adapters.storage.markdown_research import MarkdownResearchRepository
from fra.adapters.storage.markdown_signals import MarkdownSignalRepository
from fra.adapters.storage.markdown_sources import MarkdownSourceStatusRepository
from fra.adapters.storage.workspace import Workspace
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.application.crypto_market_timing import (
    CryptoMarketTimingWorkflow,
    CryptoResearchRequest,
    CryptoResearchService,
    CryptoRiskTolerance,
)
from fra.application.dashboard_service import DashboardService
from fra.application.research_orchestrator import ResearchOrchestrator
from fra.application.research_workflows import ResearchRegistry
from fra.application.source_platform import SourceRegistry, SourceRouter
from fra.domain.errors import SourceQuotaExceededError
from fra.domain.ids import EvidenceId, InstrumentId
from fra.domain.instruments import AssetClass, Currency, InstrumentRef, ProviderAlias
from fra.domain.market_data import HistoryRequest, InstrumentMatch, MarketObservation, MarketSeries
from fra.domain.research import ResearchMandateType, ResearchRunState
from fra.domain.shared import FailureKind
from fra.domain.signals import SignalStatus
from fra.domain.sources import DataEnvelope, SourceRole
from fra.ports.agent_backend import AgentStageType, StructuredAgentOutput

NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)


def test_wp5_crypto_workflow_is_reconstructable_from_markdown(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    research = MarkdownResearchRepository(workspace)
    signals = MarkdownSignalRepository(workspace)
    source_status = MarkdownSourceStatusRepository(workspace)
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    provider = _AdvancingProvider(clock)
    source_registry = SourceRegistry()
    source_registry.register(provider, roles=(SourceRole.PRIMARY,))
    router = SourceRouter(source_registry, policy_version="fra.source_policy.v1")
    workflows = ResearchRegistry()
    workflows.register(
        ResearchMandateType.CRYPTO_MARKET_TIMING,
        CryptoMarketTimingWorkflow(router, clock, ids),
    )
    agent = FakeAgentBackend(
        results=(
            StructuredAgentOutput(
                {
                    "objective": "Assess BTC and ETH",
                    "tasks": (
                        {
                            "task_id": "collect",
                            "description": "Collect market history",
                            "depends_on": (),
                        },
                        {
                            "task_id": "calculate",
                            "description": "Calculate deterministic metrics",
                            "depends_on": ("collect",),
                        },
                        {
                            "task_id": "challenge",
                            "description": "Challenge the conclusion",
                            "depends_on": ("calculate",),
                        },
                    ),
                    "data_requirements": (
                        {
                            "requirement_id": "crypto_history",
                            "description": "BTC and ETH daily market history",
                            "data_kind": "market_series",
                            "subject_ids": ("crypto:bitcoin", "crypto:ethereum"),
                            "fields": ("price", "market_cap", "volume"),
                            "geography_or_market": "CRYPTO",
                            "resolution": "daily",
                            "freshness": "1 hour",
                        },
                    ),
                }
            ),
            StructuredAgentOutput(
                {
                    "claims": (
                        {
                            "statement": "Regime follows the persisted calculations.",
                            "materiality": "high",
                            "confidence": "medium",
                            "evidence_ids": ("evidence_0006", "evidence_0008"),
                            "calculation_ids": (
                                "calculation_0007",
                                "calculation_0009",
                            ),
                            "limitations": ("Historical returns do not predict future returns.",),
                        },
                    ),
                    "scenarios": (
                        {
                            "title": "Bullish",
                            "description": "Positive returns persist.",
                            "evidence_ids": ("evidence_0006", "evidence_0008"),
                            "invalidation_conditions": ("returns turn negative",),
                        },
                        {
                            "title": "Base",
                            "description": "The mixed regime persists.",
                            "evidence_ids": ("evidence_0006", "evidence_0008"),
                            "invalidation_conditions": ("volatility changes materially",),
                        },
                        {
                            "title": "Bearish",
                            "description": "Drawdowns deepen.",
                            "evidence_ids": ("evidence_0006", "evidence_0008"),
                            "invalidation_conditions": ("drawdowns recover",),
                        },
                    ),
                    "open_questions": (),
                }
            ),
            StructuredAgentOutput({"passed": True, "issues": ()}),
            StructuredAgentOutput(
                {
                    "title": "BTC and ETH regime",
                    "summary": "The declared scenarios depend on the cited deterministic metrics.",
                    "limitations": ("Historical returns do not predict future returns.",),
                }
            ),
        ),
        now=NOW,
    )
    orchestrator = ResearchOrchestrator(
        research,
        agent,
        clock,
        ids,
        workflows=workflows,
        signal_repository=signals,
        working_directory=workspace.root,
    )

    run = asyncio.run(
        CryptoResearchService(orchestrator).start(
            CryptoResearchRequest(
                horizon_days=365,
                risk_tolerance=CryptoRiskTolerance.MEDIUM,
                currency=Currency("USD"),
                lookback_days=30,
            )
        )
    )

    assert run.state is ResearchRunState.COMPLETED
    assert [item.stage for item in run.stage_checkpoints] == [
        "plan",
        "collect",
        "analyze",
        "verify",
        "synthesize",
    ]
    run_dir = workspace.root / f"runs/2026/07/{run.id}"
    assert len(tuple((run_dir / "evidence").glob("*.md"))) == 2
    assert len(tuple((run_dir / "calculations").glob("*.md"))) == 2
    assert (run_dir / "plan.md").is_file()
    assert len(tuple((run_dir / "claims").glob("*.md"))) == 1
    assert len(tuple((run_dir / "scenarios").glob("*.md"))) == 3
    assert (run_dir / "verification.md").is_file()
    assert (run_dir / "report.md").is_file()
    report = (run_dir / "report.md").read_text()
    collection_checkpoint = next(item for item in run.stage_checkpoints if item.stage == "collect")
    collection = json.loads(collection_checkpoint.result_json)
    assert collection["declared_inputs"] == {
        "asset_scope": ["bitcoin", "ethereum"],
        "currency": "USD",
        "horizon_days": 365,
        "horizon_semantics": "forward interpretation horizon",
        "lookback_days": 30,
        "lookback_semantics": "bounded historical measurement window",
        "risk_semantics": "categorical interpretation constraint",
        "risk_tolerance": "medium",
    }
    assert collection["collection_window"] == {
        "knowledge_cutoff_at": (NOW + timedelta(seconds=2)).isoformat(),
        "requested_end_at": NOW.isoformat(),
        "requested_start_at": (NOW - timedelta(days=30)).isoformat(),
        "resolution": "daily",
    }
    assert collection["calculation_conventions"]["annualization_periods"] == 365
    assert collection["calculation_conventions"]["formula_version"] == 1
    first_asset = collection["assets"][0]
    assert first_asset["currency"] == "USD"
    assert first_asset["resolution"] == "daily"
    assert first_asset["first_price"] == "100"
    assert first_asset["last_price"] == "130"
    assert first_asset["first_observed_at"] == (NOW - timedelta(days=30)).isoformat()
    assert first_asset["last_observed_at"] == NOW.isoformat()
    assert first_asset["available_at"] == (NOW + timedelta(seconds=1)).isoformat()
    analyze_request = next(
        item for item in agent.requests if item.stage_type is AgentStageType.ANALYZE
    )
    verify_request = next(
        item for item in agent.requests if item.stage_type is AgentStageType.VERIFY
    )
    assert '"declared_inputs"' in analyze_request.instructions
    assert "forward-looking" in analyze_request.instructions
    assert "do not require an invented numeric suitability threshold" in verify_request.instructions
    assert "Source Routing and Attribution" in report
    assert "Deterministic Evidence and Calculations" in report
    assert "Evidence Window" in report
    assert "Calculation Conventions" in report
    assert "fake_market" in report
    signal = signals.list()[0]
    assert signal.status is SignalStatus.ACTIVE
    assert signal.evidence_ids
    assert signal.calculation_ids
    assert (workspace.root / f"signals/{signal.id}/v001.md").is_file()
    persisted_evidence = tuple(
        research.get_evidence(run.id, EvidenceId(value))
        for value in ("evidence_0006", "evidence_0008")
    )
    assert all(item.knowledge_cutoff_at >= item.available_at for item in persisted_evidence)

    restarted = DashboardService(
        MarkdownResearchRepository(workspace),
        MarkdownSignalRepository(workspace),
        source_status,
    ).snapshot(NOW)
    assert restarted.signals[0].artifact.location == f"signals/{signal.id}/v001.md"
    assert restarted.recent_runs[0].state == "completed"


def test_missing_crypto_risk_inputs_persist_needs_user_input_without_agent_call(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    research = MarkdownResearchRepository(workspace)
    signals = MarkdownSignalRepository(workspace)
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    provider = _provider()
    sources = SourceRegistry()
    sources.register(provider, roles=(SourceRole.PRIMARY,))
    workflows = ResearchRegistry()
    workflows.register(
        ResearchMandateType.CRYPTO_MARKET_TIMING,
        CryptoMarketTimingWorkflow(
            SourceRouter(sources, policy_version="fra.source_policy.v1"),
            clock,
            ids,
        ),
    )
    agent = FakeAgentBackend(now=NOW)
    orchestrator = ResearchOrchestrator(
        research,
        agent,
        clock,
        ids,
        workflows=workflows,
        signal_repository=signals,
    )

    run = asyncio.run(
        CryptoResearchService(orchestrator).start(
            CryptoResearchRequest(horizon_days=None, risk_tolerance=None, lookback_days=30)
        )
    )

    assert run.state is ResearchRunState.NEEDS_USER_INPUT
    assert run.failure is not None
    assert "investment horizon" in run.failure.message
    assert "risk tolerance" in run.failure.message
    assert not agent.requests
    assert (workspace.root / f"runs/2026/07/{run.id}/limitation.md").is_file()


def test_crypto_quota_failure_is_typed_and_retains_a_limitation_artifact(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    research = MarkdownResearchRepository(workspace)
    signals = MarkdownSignalRepository(workspace)
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    provider = _QuotaProvider()
    sources = SourceRegistry()
    sources.register(provider, roles=(SourceRole.PRIMARY,))
    workflows = ResearchRegistry()
    workflows.register(
        ResearchMandateType.CRYPTO_MARKET_TIMING,
        CryptoMarketTimingWorkflow(
            SourceRouter(sources, policy_version="fra.source_policy.v1"),
            clock,
            ids,
        ),
    )
    agent = FakeAgentBackend(
        results=(
            StructuredAgentOutput(
                {
                    "objective": "Assess BTC and ETH",
                    "tasks": (
                        {
                            "task_id": "collect",
                            "description": "Collect market history",
                            "depends_on": (),
                        },
                    ),
                    "data_requirements": (
                        {
                            "requirement_id": "crypto_history",
                            "description": "BTC and ETH market history",
                            "data_kind": "market_series",
                            "subject_ids": ("crypto:bitcoin", "crypto:ethereum"),
                            "fields": ("price",),
                            "geography_or_market": "CRYPTO",
                            "resolution": "daily",
                            "freshness": None,
                        },
                    ),
                }
            ),
        ),
        now=NOW,
    )
    orchestrator = ResearchOrchestrator(
        research,
        agent,
        clock,
        ids,
        workflows=workflows,
        signal_repository=signals,
    )

    run = asyncio.run(
        CryptoResearchService(orchestrator).start(
            CryptoResearchRequest(
                horizon_days=365,
                risk_tolerance=CryptoRiskTolerance.MEDIUM,
                lookback_days=30,
            )
        )
    )

    assert run.state is ResearchRunState.FAILED
    assert run.failure is not None
    assert run.failure.kind is FailureKind.QUOTA_EXCEEDED
    assert (workspace.root / f"runs/2026/07/{run.id}/limitation.md").is_file()
    assert not signals.list()


def _provider() -> FakeMarketDataProvider:
    bitcoin = _instrument("bitcoin", "Bitcoin", "BTC")
    ethereum = _instrument("ethereum", "Ethereum", "ETH")
    descriptor = FakeMarketDataProvider().descriptor()
    return FakeMarketDataProvider(
        matches=(
            InstrumentMatch(bitcoin, Decimal("1")),
            InstrumentMatch(ethereum, Decimal("1")),
        ),
        histories=(
            (bitcoin, _envelope(descriptor, bitcoin, Decimal("100"), Decimal("130"))),
            (ethereum, _envelope(descriptor, ethereum, Decimal("50"), Decimal("55"))),
        ),
        now=NOW,
    )


class _QuotaProvider(FakeMarketDataProvider):
    def __init__(self) -> None:
        bitcoin = _instrument("bitcoin", "Bitcoin", "BTC")
        ethereum = _instrument("ethereum", "Ethereum", "ETH")
        super().__init__(
            matches=(
                InstrumentMatch(bitcoin, Decimal("1")),
                InstrumentMatch(ethereum, Decimal("1")),
            ),
            now=NOW,
        )

    async def history(self, request: HistoryRequest) -> DataEnvelope[MarketSeries]:
        del request
        raise SourceQuotaExceededError("fixture quota exhausted")


class _AdvancingProvider(FakeMarketDataProvider):
    """Models a live fetch whose retrieval completes after collection starts."""

    def __init__(self, clock: FixedClock) -> None:
        bitcoin = _instrument("bitcoin", "Bitcoin", "BTC")
        ethereum = _instrument("ethereum", "Ethereum", "ETH")
        descriptor = FakeMarketDataProvider().descriptor()
        available_at = NOW + timedelta(seconds=1)
        super().__init__(
            matches=(
                InstrumentMatch(bitcoin, Decimal("1")),
                InstrumentMatch(ethereum, Decimal("1")),
            ),
            histories=(
                (
                    bitcoin,
                    _envelope(
                        descriptor,
                        bitcoin,
                        Decimal("100"),
                        Decimal("130"),
                        available_at=available_at,
                    ),
                ),
                (
                    ethereum,
                    _envelope(
                        descriptor,
                        ethereum,
                        Decimal("50"),
                        Decimal("55"),
                        available_at=available_at,
                    ),
                ),
            ),
            now=NOW,
        )
        self._clock = clock

    async def history(self, request: HistoryRequest) -> DataEnvelope[MarketSeries]:
        self._clock.advance(timedelta(seconds=1))
        return await super().history(request)


def _instrument(coin_id: str, name: str, symbol: str) -> InstrumentRef:
    return InstrumentRef(
        id=InstrumentId(f"crypto:{coin_id}"),
        asset_class=AssetClass.CRYPTO,
        name=name,
        currency=Currency("USD"),
        aliases=(ProviderAlias("coingecko", coin_id),),
        display_symbol=symbol,
    )


def _envelope(
    descriptor: object,
    instrument: InstrumentRef,
    first_price: Decimal,
    final_price: Decimal,
    *,
    available_at: datetime = NOW,
) -> DataEnvelope[MarketSeries]:
    from fra.domain.sources import SourceDescriptor

    assert isinstance(descriptor, SourceDescriptor)
    observations = tuple(
        MarketObservation(
            instrument_id=instrument.id,
            observed_at=NOW - timedelta(days=30 - index),
            price=(first_price + (final_price - first_price) * Decimal(index) / Decimal(30)),
            market_cap=Decimal("1000000000") + Decimal(index),
            volume=Decimal("100000000") + Decimal(index),
            currency=Currency("USD"),
        )
        for index in range(31)
    )
    return DataEnvelope(
        value=MarketSeries(instrument.id, observations, Currency("USD")),
        descriptor=descriptor,
        provider_record_id=instrument.alias_for("coingecko") or "missing",
        source="https://fixture.test/market-chart",
        available_at=available_at,
        retrieved_at=available_at,
        provider_subject_ids=(instrument.alias_for("coingecko") or "missing",),
        fra_subject_ids=(instrument.id,),
        observed_at=NOW,
        period_start=observations[0].observed_at,
        period_end=observations[-1].observed_at,
        currency="USD",
        content_hash="sha256:" + "1" * 64,
        request_fingerprint="sha256:" + "2" * 64,
        required_attribution="Fixture market data",
    )
