import asyncio
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fra.adapters.agents.claude_cli import ClaudeCliAgentAdapter
from fra.adapters.agents.codex_cli import CodexCliAgentAdapter
from fra.adapters.fakes.market_data import FakeMarketDataProvider
from fra.adapters.storage.markdown_portfolios import (
    MarkdownPortfolioRepository,
    MarkdownProfileRepository,
)
from fra.adapters.storage.markdown_research import MarkdownResearchRepository
from fra.adapters.storage.markdown_signals import MarkdownSignalRepository
from fra.adapters.storage.workspace import Workspace
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.application.allocation_research import (
    AllocationResearchRequest,
    AllocationResearchService,
    AllocationResearchWorkflow,
)
from fra.application.research_orchestrator import ResearchOrchestrator
from fra.application.research_workflows import ResearchRegistry
from fra.application.source_platform import SourceRegistry, SourceRouter
from fra.domain.ids import InstrumentId
from fra.domain.instruments import AssetClass, Currency, InstrumentRef, ProviderAlias
from fra.domain.market_data import InstrumentMatch, MarketObservation, MarketSeries
from fra.domain.portfolio import RiskTolerance
from fra.domain.research import ResearchMandateType, ResearchRunState
from fra.domain.sources import DataEnvelope, SourceDescriptor, SourceRole
from fra.ports.agent_backend import AgentBackend, StructuredAgentOutput

NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "agent_backends"


@pytest.mark.parametrize("backend_name", ["codex_cli", "claude_cli"])
def test_wp8_allocation_is_constraint_bound_and_durable_for_each_backend(
    backend_name: str, tmp_path: Path
) -> None:
    _assert_fixture_allocation(backend_name, _agent_backend(backend_name), tmp_path)


@pytest.mark.skipif(
    os.environ.get("FRA_RUN_LIVE_WP8") != "1",
    reason="set FRA_RUN_LIVE_WP8=1 to use installed Codex and Claude authentication and quota",
)
@pytest.mark.parametrize("backend_name", ["codex_cli", "claude_cli"])
def test_wp8_fixture_allocation_completes_through_each_installed_cli(
    backend_name: str, tmp_path: Path
) -> None:
    agent = _installed_agent_backend(backend_name)
    health = asyncio.run(agent.health())
    assert health.ok, health.summary
    _assert_fixture_allocation(backend_name, agent, tmp_path)


def _assert_fixture_allocation(backend_name: str, agent: AgentBackend, tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / backend_name)
    workspace.initialize()
    research = MarkdownResearchRepository(workspace)
    signals = MarkdownSignalRepository(workspace)
    profiles = MarkdownProfileRepository(workspace)
    portfolios = MarkdownPortfolioRepository(workspace)
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    sources = SourceRegistry()
    sources.register(_provider(), roles=(SourceRole.FALLBACK,))
    workflows = ResearchRegistry()
    workflows.register(
        ResearchMandateType.ASSET_ALLOCATION,
        AllocationResearchWorkflow(
            SourceRouter(sources, policy_version="fra.source_policy.v1"), clock, ids
        ),
    )
    orchestrator = ResearchOrchestrator(
        research,
        agent,
        clock,
        ids,
        workflows=workflows,
        signal_repository=signals,
        profile_repository=profiles,
        portfolio_repository=portfolios,
        working_directory=workspace.root,
    )

    run = asyncio.run(
        AllocationResearchService(orchestrator).start(
            AllocationResearchRequest(
                horizon_years=10,
                risk_tolerance=RiskTolerance.MEDIUM,
                maximum_loss=Decimal("0.80"),
                liquidity_need=Decimal("0.10"),
                tax_jurisdiction="US",
                investment_objective="Long-term capital growth",
                risk_capacity=RiskTolerance.MEDIUM,
            )
        )
    )

    assert run.state is ResearchRunState.COMPLETED
    assert run.agent_metadata is not None
    assert run.agent_metadata.provider_name == backend_name
    profile = MarkdownProfileRepository(workspace).list()[0]
    portfolio = MarkdownPortfolioRepository(workspace).list()[0]
    assert portfolio.profile_id == profile.id
    assert profile.investment_objective == "Long-term capital growth"
    assert profile.risk_capacity is RiskTolerance.MEDIUM
    assert sum((item.weight for item in portfolio.positions), Decimal(0)) == Decimal(1)
    assert all(item.weight <= profile.maximum_asset_weight for item in portfolio.positions)
    assert next(item for item in portfolio.positions if item.symbol == "CASH").weight == Decimal(
        "0.1"
    )
    report = research.get(run.id)
    assert report.state is ResearchRunState.COMPLETED
    report_text = next((workspace.root / "runs/2026/07").rglob("report.md")).read_text()
    assert "personal-use-only" in report_text
    assert "No brokerage, account, custody, or order action" in report_text
    assert "Herfindahl-Hirschman index" in report_text
    assert "twice annualized volatility" in report_text
    assert len(signals.list()) == 1


def test_wp8_allocation_missing_suitability_stops_before_agent_or_provider(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    research = MarkdownResearchRepository(workspace)
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    workflows = ResearchRegistry()
    sources = SourceRegistry()
    workflows.register(
        ResearchMandateType.ASSET_ALLOCATION,
        AllocationResearchWorkflow(
            SourceRouter(sources, policy_version="fra.source_policy.v1"), clock, ids
        ),
    )
    agent = _agent_backend("codex_cli")
    orchestrator = ResearchOrchestrator(
        research, agent, clock, ids, workflows=workflows, working_directory=workspace.root
    )

    run = asyncio.run(
        AllocationResearchService(orchestrator).start(
            AllocationResearchRequest(None, None, None, None, None)
        )
    )

    assert run.state is ResearchRunState.NEEDS_USER_INPUT
    assert run.failure is not None
    assert "risk tolerance" in run.failure.message
    assert "maximum loss" in run.failure.message
    assert "investment objective" in run.failure.message
    assert "risk capacity" in run.failure.message
    assert run.stage_attempts == ()


def _agent_backend(backend_name: str) -> AgentBackend:
    payloads = {
        f"fra.agent.{stage}.v2": output.values
        for stage, output in zip(
            ("plan", "analyze", "verify", "synthesize"),
            _agent_outputs(),
            strict=True,
        )
    }
    encoded = json.dumps(payloads)
    if backend_name == "codex_cli":
        return CodexCliAgentAdapter(
            binary=str(FIXTURES / "fake_codex.py"),
            environment={"FAKE_CODEX_OUTPUTS": encoded},
        )
    if backend_name == "claude_cli":
        return ClaudeCliAgentAdapter(
            binary=str(FIXTURES / "fake_claude.py"),
            environment={"FAKE_CLAUDE_OUTPUTS": encoded},
        )
    raise AssertionError(f"unsupported backend fixture: {backend_name}")


def _installed_agent_backend(backend_name: str) -> AgentBackend:
    if backend_name == "codex_cli":
        return CodexCliAgentAdapter(binary="codex", sandbox="read-only")
    if backend_name == "claude_cli":
        return ClaudeCliAgentAdapter(binary="claude", permission_mode="plan")
    raise AssertionError(f"unsupported installed backend: {backend_name}")


class _AllocationProvider(FakeMarketDataProvider):
    def descriptor(self) -> SourceDescriptor:
        return replace(
            super().descriptor(),
            provider_id="yfinance",
            required_attribution="Yahoo Finance via yfinance",
        )


def _provider() -> FakeMarketDataProvider:
    instruments = tuple(_instrument(symbol) for symbol in ("SPY", "BND", "GLD"))
    descriptor = _AllocationProvider().descriptor()
    return _AllocationProvider(
        matches=tuple(InstrumentMatch(item, Decimal(1)) for item in instruments),
        histories=tuple((item, _history(descriptor, item)) for item in instruments),
        now=NOW,
    )


def _instrument(symbol: str) -> InstrumentRef:
    return InstrumentRef(
        InstrumentId(f"etf:{symbol.lower()}"),
        AssetClass.FUND,
        symbol,
        Currency("USD"),
        (ProviderAlias("yfinance", symbol),),
        symbol,
    )


def _history(descriptor: SourceDescriptor, instrument: InstrumentRef) -> DataEnvelope[MarketSeries]:
    observations = tuple(
        MarketObservation(
            instrument.id,
            NOW - timedelta(days=30 - index),
            Decimal(100) + Decimal(index),
            None,
            Decimal(1000),
            Currency("USD"),
        )
        for index in range(31)
    )
    return DataEnvelope(
        MarketSeries(instrument.id, observations, Currency("USD")),
        descriptor,
        instrument.display_symbol or "unknown",
        "https://query1.finance.yahoo.com/fixture",
        NOW,
        NOW,
        provider_subject_ids=(instrument.display_symbol or "unknown",),
        fra_subject_ids=(instrument.id,),
        period_start=observations[0].observed_at,
        period_end=observations[-1].observed_at,
        currency="USD",
        required_attribution="Yahoo Finance via yfinance",
    )


def _agent_outputs() -> tuple[StructuredAgentOutput, ...]:
    return (
        StructuredAgentOutput(
            {
                "objective": "Propose a constrained allocation",
                "tasks": (
                    {
                        "task_id": "collect",
                        "description": "Collect adjusted histories",
                        "depends_on": (),
                    },
                    {
                        "task_id": "calculate",
                        "description": "Calculate constrained weights",
                        "depends_on": ("collect",),
                    },
                    {
                        "task_id": "challenge",
                        "description": "Challenge the allocation",
                        "depends_on": ("calculate",),
                    },
                ),
                "data_requirements": (
                    {
                        "requirement_id": "adjusted_histories",
                        "description": "Adjusted histories for the candidate assets",
                        "data_kind": "market_series",
                        "subject_ids": ("equity:SPY", "bond:BND", "commodity:GLD"),
                        "fields": ("adjusted_close",),
                        "geography_or_market": "US",
                        "resolution": "daily",
                        "freshness": None,
                    },
                ),
            }
        ),
        StructuredAgentOutput(
            {
                "claims": (
                    {
                        "statement": "The persisted constraints bind the proposal.",
                        "materiality": "high",
                        "confidence": "medium",
                        "evidence_ids": ("evidence_0006",),
                        "calculation_ids": ("calculation_0010",),
                        "limitations": ("No trade execution was performed.",),
                    },
                ),
                "scenarios": (
                    {
                        "title": "Base",
                        "description": "The declared constraints remain unchanged.",
                        "evidence_ids": ("evidence_0006",),
                        "invalidation_conditions": ("the investor profile changes",),
                    },
                    {
                        "title": "Stress",
                        "description": "Asset losses approach the declared tolerance.",
                        "evidence_ids": ("evidence_0006",),
                        "invalidation_conditions": ("stress assumptions are breached",),
                    },
                ),
                "open_questions": (),
            }
        ),
        StructuredAgentOutput({"passed": True, "issues": ()}),
        StructuredAgentOutput(
            {
                "title": "Allocation research",
                "summary": "Cash and capped asset weights preserve the declared constraints.",
                "limitations": ("No trade execution was performed.",),
            }
        ),
    )
