"""Application composition root."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import cast

import typer

from fra.adapters.data_sources.common.http import (
    AsyncRateLimiter,
    HttpClient,
    create_async_client,
)
from fra.adapters.storage.markdown_exposure_graphs import MarkdownExposureGraphRepository
from fra.adapters.storage.markdown_forecasts import MarkdownForecastRepository
from fra.adapters.storage.markdown_outcomes import MarkdownOutcomeRepository
from fra.adapters.storage.markdown_portfolios import (
    MarkdownPortfolioRepository,
    MarkdownProfileRepository,
)
from fra.adapters.storage.markdown_research import MarkdownResearchRepository
from fra.adapters.storage.markdown_signals import MarkdownSignalRepository
from fra.adapters.storage.markdown_sources import (
    MarkdownSourceCacheRepository,
    MarkdownSourceStatusRepository,
)
from fra.adapters.storage.workspace import Workspace
from fra.adapters.storage.workspace_maintenance import WorkspaceMaintenanceService
from fra.adapters.system.runtime import RandomIdGenerator, SystemClock
from fra.application.allocation_research import (
    AllocationResearchService,
    AllocationResearchWorkflow,
)
from fra.application.container import (
    ResearchApplication,
    ResearchWorkflowApplication,
    SourceApplication,
    WorkspaceApplication,
)
from fra.application.crisis_research import (
    CompanyFactsProvider,
    CrisisResearchService,
    CrisisResearchWorkflow,
)
from fra.application.crypto_market_timing import CryptoMarketTimingWorkflow, CryptoResearchService
from fra.application.dashboard_service import DashboardService
from fra.application.doctor_service import DoctorCheck, DoctorService
from fra.application.forecast_service import ForecastLifecycleService, ForecastRefreshService
from fra.application.regional_packs import RegionalPackService
from fra.application.research_orchestrator import ResearchOrchestrator
from fra.application.research_run_service import ResearchRunService
from fra.application.research_workflows import ResearchRegistry
from fra.application.source_cache import SourceCache
from fra.application.source_platform import SourceRegistry, SourceRouter
from fra.application.source_service import SourceService
from fra.application.workspace_service import (
    ResearchQueryService,
    SignalQueryService,
    WorkspaceService,
)
from fra.cli.app import create_app
from fra.config.loader import load_config, validate_configuration
from fra.domain.research import ResearchMandateType
from fra.domain.shared import FailureKind
from fra.domain.sources import UsageProfile
from fra.errors import ConfigurationError
from fra.factories.agents import AgentBackendFactory
from fra.factories.in_memory import (
    AgentBackendFactory as InMemoryAgentBackendFactory,
)
from fra.factories.in_memory import (
    RepositoryFactory,
    SourceAdapterFactory,
    SystemAdapterFactory,
)
from fra.factories.sources import BuiltInSourceFactory
from fra.ports.agent_backend import AgentBackend
from fra.ports.clock import Clock
from fra.ports.documents import DocumentProvider
from fra.ports.economic_series import EconomicSeriesProvider
from fra.ports.ids import IdGenerator
from fra.ports.market_data import MarketDataProvider
from fra.ports.repositories import ResearchRepository, SignalRepository


def build_cli() -> typer.Typer:
    """Construct the current application object graph."""
    doctor_service = DoctorService(
        configuration_probe=validate_configuration,
        workspace_probe=_workspace_probe,
        atomic_repository_probe=_atomic_repository_probe,
        source_probes=_source_probes,
        agent_probes=_agent_probes,
    )
    return create_app(
        doctor_service,
        build_markdown_application,
        build_source_application,
        build_research_workflow_application,
    )


def build_markdown_application(config_path: Path | None = None) -> WorkspaceApplication:
    """Construct the durable WP2 object graph from validated configuration."""
    workspace = _workspace(config_path)
    research = MarkdownResearchRepository(workspace)
    signals = MarkdownSignalRepository(workspace)
    source_status = MarkdownSourceStatusRepository(workspace)
    forecasts = MarkdownForecastRepository(workspace)
    outcomes = MarkdownOutcomeRepository(workspace)
    graphs = MarkdownExposureGraphRepository(workspace)
    forecast_lifecycle = ForecastLifecycleService(
        forecasts,
        outcomes,
        research,
        SystemClock(),
        RandomIdGenerator(),
    )
    return WorkspaceApplication(
        workspace=WorkspaceService(workspace),
        dashboard=DashboardService(
            research,
            signals,
            source_status,
            forecasts,
            outcomes,
            graphs,
        ),
        runs=ResearchQueryService(research),
        signals=SignalQueryService(signals),
        research_repository=research,
        signal_repository=signals,
        source_status_repository=source_status,
        forecasts=forecast_lifecycle,
        forecast_repository=forecasts,
        outcome_repository=outcomes,
        exposure_graph_repository=graphs,
        regions=RegionalPackService(),
        maintenance=WorkspaceMaintenanceService(workspace),
    )


def build_source_application(config_path: Path | None = None) -> SourceApplication:
    """Construct enabled built-in sources and explicit source-check services."""
    loaded = load_config(config_path)
    raw_client = create_async_client()
    try:
        registry = SourceRegistry()
        BuiltInSourceFactory.register_all(
            loaded.config,
            HttpClient(raw_client, rate_limiter=AsyncRateLimiter(5)),
            registry,
        )
        statuses = MarkdownSourceStatusRepository(_workspace(config_path))
        cache = MarkdownSourceCacheRepository(_workspace(config_path))
    except Exception:
        asyncio.run(raw_client.aclose())
        raise
    return SourceApplication(
        SourceService(registry, statuses),
        SourceRouter(registry, policy_version="fra.source_policy.v1", statuses=statuses),
        SourceCache(cache),
        raw_client.aclose,
    )


def build_research_workflow_application(
    config_path: Path | None = None,
) -> ResearchWorkflowApplication:
    """Construct the durable WP4 agent and orchestration graph."""
    loaded = load_config(config_path)
    workspace = _workspace(config_path)
    if not workspace.initialized:
        raise ConfigurationError("Workspace is not initialized; run `fra init` first")
    repository = MarkdownResearchRepository(workspace)
    signals = MarkdownSignalRepository(workspace)
    forecasts = MarkdownForecastRepository(workspace)
    outcomes = MarkdownOutcomeRepository(workspace)
    graphs = MarkdownExposureGraphRepository(workspace)
    profiles = MarkdownProfileRepository(workspace)
    portfolios = MarkdownPortfolioRepository(workspace)
    backend = AgentBackendFactory.create(loaded.config.agent)
    raw_client = create_async_client()
    try:
        registry = SourceRegistry()
        BuiltInSourceFactory.register_all(
            loaded.config,
            HttpClient(raw_client, rate_limiter=AsyncRateLimiter(5)),
            registry,
        )
        statuses = MarkdownSourceStatusRepository(workspace)
        router = SourceRouter(
            registry,
            policy_version="fra.source_policy.v1",
            statuses=statuses,
        )
        sec_provider: CompanyFactsProvider | None = None
        for source in registry.list():
            if source.descriptor.provider_id == "sec_edgar":
                sec_provider = cast(CompanyFactsProvider, source.adapter)
        clock = SystemClock()
        ids = RandomIdGenerator()
        workflows = ResearchRegistry()
        workflows.register(
            ResearchMandateType.CRYPTO_MARKET_TIMING,
            CryptoMarketTimingWorkflow(
                router,
                clock,
                ids,
                usage_profile=UsageProfile(loaded.config.workspace.usage_profile),
            ),
        )
        workflows.register(
            ResearchMandateType.ASSET_ALLOCATION,
            AllocationResearchWorkflow(router, clock, ids),
        )
        workflows.register(
            ResearchMandateType.CRISIS_IMPACT,
            CrisisResearchWorkflow(
                router=router,
                sec=sec_provider,
                clock=clock,
                ids=ids,
            ),
        )
        orchestrator = ResearchOrchestrator(
            repository,
            backend,
            clock,
            ids,
            working_directory=workspace.root,
            timeout_seconds=loaded.config.agent.timeout_seconds,
            workflows=workflows,
            signal_repository=signals,
            forecast_repository=forecasts,
            exposure_graph_repository=graphs,
            profile_repository=profiles,
            portfolio_repository=portfolios,
        )
        forecast_lifecycle = ForecastLifecycleService(
            forecasts,
            outcomes,
            repository,
            clock,
            ids,
        )
        forecast_refresh = ForecastRefreshService(
            repository,
            workflows,
            forecast_lifecycle,
            clock,
        )
    except Exception:
        asyncio.run(raw_client.aclose())
        raise
    return ResearchWorkflowApplication(
        orchestrator,
        repository,
        backend,
        crypto=CryptoResearchService(orchestrator),
        crisis=CrisisResearchService(orchestrator),
        allocation=AllocationResearchService(orchestrator),
        forecast_refresh=forecast_refresh,
        close=raw_client.aclose,
    )


def _workspace(config_path: Path | None) -> Workspace:
    loaded = load_config(config_path)
    root = loaded.config.workspace.root
    if not root.is_absolute():
        root = Path.cwd() / root
    return Workspace(root)


def _workspace_probe(config_path: Path | None) -> DoctorCheck:
    workspace = _workspace(config_path)
    if not workspace.root.exists():
        return DoctorCheck("Workspace", True, f"ready to initialize ({workspace.root})")
    if not workspace.initialized:
        return DoctorCheck("Workspace", True, f"directory ready for init ({workspace.root})")
    try:
        workspace.codec.parse(
            workspace.path("workspace.md").read_text(encoding="utf-8"),
            expected_schema="fra.workspace",
        )
    except Exception as error:
        return DoctorCheck("Workspace", False, f"invalid: {error}")
    return DoctorCheck("Workspace", True, f"initialized ({workspace.root})")


def _atomic_repository_probe(config_path: Path | None) -> DoctorCheck:
    workspace = _workspace(config_path)
    if not workspace.initialized:
        return DoctorCheck("Markdown atomic write", True, "deferred until workspace init")
    probe = workspace.path(".locks/doctor-atomic-probe.md")
    try:
        workspace.writer.write_text(probe, "probe\n")
        if probe.read_text(encoding="utf-8") != "probe\n":
            raise OSError("probe content mismatch")
    except OSError as error:
        return DoctorCheck("Markdown atomic write", False, str(error))
    finally:
        probe.unlink(missing_ok=True)
    return DoctorCheck("Markdown atomic write", True, "atomic replace available")


def _source_probes(config_path: Path | None) -> tuple[DoctorCheck, ...]:
    application = build_source_application(config_path)
    try:
        summaries = application.sources.list()
        descriptions = tuple(application.sources.describe(item.provider_id) for item in summaries)
    finally:
        asyncio.run(_close_source_application(application))
    manifests = DoctorCheck(
        "Source manifests",
        True,
        f"{len(descriptions)} enabled source manifest(s) valid",
    )
    capabilities = DoctorCheck(
        "Source capabilities",
        True,
        "all enabled sources expose typed capabilities; "
        + (
            ", ".join(f"{item.provider_id}={item.health}" for item in summaries)
            if summaries
            else "no enabled sources"
        ),
    )
    today = date.today()
    expired = tuple(
        item.provider_id
        for item in descriptions
        if (today - date.fromisoformat(item.terms_reviewed_at)).days > 366
        or date.fromisoformat(item.terms_reviewed_at) > today
    )
    terms = DoctorCheck(
        "Source terms reviews",
        not expired,
        "current" if not expired else f"expired or future-dated: {', '.join(expired)}",
    )
    return manifests, capabilities, terms


def _agent_probes(config_path: Path | None) -> tuple[DoctorCheck, ...]:
    loaded = load_config(config_path)
    backend = AgentBackendFactory.create(loaded.config.agent)
    health = asyncio.run(backend.health())
    capabilities = backend.capabilities()
    binary_ok = health.failure is None or health.failure.kind is not FailureKind.ADAPTER_UNAVAILABLE
    binary_detail = health.summary
    if not binary_ok and health.failure is not None:
        binary_detail = health.failure.message
    required = (
        capabilities.structured_output
        and capabilities.session_resume
        and capabilities.event_streaming
    )
    return (
        DoctorCheck(
            "Agent binary",
            binary_ok,
            binary_detail,
        ),
        DoctorCheck(
            "Agent capabilities",
            required,
            "structured output, JSONL events, and resume available"
            if required
            else "required agent capabilities unavailable",
        ),
        DoctorCheck(
            "Agent authentication",
            health.ok,
            "authenticated" if health.ok else health.summary,
        ),
    )


async def _close_source_application(application: SourceApplication) -> None:
    await application.close()


def build_in_memory_application(
    *,
    research_repository: ResearchRepository | None = None,
    signal_repository: SignalRepository | None = None,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    agent_backend: AgentBackend | None = None,
    market_data_provider: MarketDataProvider | None = None,
    document_provider: DocumentProvider | None = None,
    economic_series_provider: EconomicSeriesProvider | None = None,
) -> ResearchApplication:
    """Construct the fully replaceable, hermetic WP1 application graph."""
    research_repository = research_repository or RepositoryFactory.research()
    signal_repository = signal_repository or RepositoryFactory.signals()
    clock = clock or SystemAdapterFactory.clock()
    ids = ids or SystemAdapterFactory.ids()
    agent_backend = agent_backend or InMemoryAgentBackendFactory.create()
    market_data_provider = market_data_provider or SourceAdapterFactory.market_data()
    document_provider = document_provider or SourceAdapterFactory.documents()
    economic_series_provider = economic_series_provider or SourceAdapterFactory.economic_series()
    return ResearchApplication(
        research_runs=ResearchRunService(research_repository, clock, ids),
        research_repository=research_repository,
        signal_repository=signal_repository,
        agent_backend=agent_backend,
        market_data_provider=market_data_provider,
        document_provider=document_provider,
        economic_series_provider=economic_series_provider,
    )


def main() -> None:
    """Construct and run the FRA application."""
    build_cli()()
