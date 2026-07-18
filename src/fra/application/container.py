"""Explicit application object graph exposed by the composition root."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fra.application.allocation_research import AllocationResearchService
from fra.application.crisis_research import CrisisResearchService
from fra.application.crypto_market_timing import CryptoResearchService
from fra.application.dashboard_service import DashboardService
from fra.application.forecast_service import ForecastLifecycleService, ForecastRefreshService
from fra.application.regional_packs import RegionalPackService
from fra.application.research_orchestrator import ResearchOrchestrator
from fra.application.research_run_service import ResearchRunService
from fra.application.source_cache import SourceCache
from fra.application.source_platform import SourceRouter
from fra.application.source_service import SourceService
from fra.application.workspace_service import (
    ResearchQueryService,
    SignalQueryService,
    WorkspaceService,
)
from fra.ports.agent_backend import AgentBackend
from fra.ports.documents import DocumentProvider
from fra.ports.economic_series import EconomicSeriesProvider
from fra.ports.market_data import MarketDataProvider
from fra.ports.repositories import (
    ExposureGraphRepository,
    ForecastRepository,
    OutcomeRepository,
    ResearchRepository,
    SignalRepository,
    SourceStatusRepository,
)
from fra.ports.workspace_maintenance import WorkspaceMaintenance


async def _noop_close() -> None:
    return None


@dataclass(frozen=True, slots=True)
class ResearchApplication:
    research_runs: ResearchRunService
    research_repository: ResearchRepository
    signal_repository: SignalRepository
    agent_backend: AgentBackend
    market_data_provider: MarketDataProvider
    document_provider: DocumentProvider
    economic_series_provider: EconomicSeriesProvider


@dataclass(frozen=True, slots=True)
class WorkspaceApplication:
    workspace: WorkspaceService
    dashboard: DashboardService
    runs: ResearchQueryService
    signals: SignalQueryService
    research_repository: ResearchRepository
    signal_repository: SignalRepository
    source_status_repository: SourceStatusRepository
    forecasts: ForecastLifecycleService
    forecast_repository: ForecastRepository
    outcome_repository: OutcomeRepository
    exposure_graph_repository: ExposureGraphRepository
    regions: RegionalPackService
    maintenance: WorkspaceMaintenance


@dataclass(frozen=True, slots=True)
class SourceApplication:
    sources: SourceService
    router: SourceRouter
    cache: SourceCache
    close: Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ResearchWorkflowApplication:
    orchestrator: ResearchOrchestrator
    research_repository: ResearchRepository
    agent_backend: AgentBackend
    crypto: CryptoResearchService | None = None
    crisis: CrisisResearchService | None = None
    allocation: AllocationResearchService | None = None
    forecast_refresh: ForecastRefreshService | None = None
    close: Callable[[], Awaitable[None]] = _noop_close
