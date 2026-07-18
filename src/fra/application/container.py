"""Explicit application object graph exposed by the composition root."""

from dataclasses import dataclass

from fra.application.research_run_service import ResearchRunService
from fra.ports.agent_backend import AgentBackend
from fra.ports.documents import DocumentProvider
from fra.ports.market_data import MarketDataProvider
from fra.ports.repositories import ResearchRepository, SignalRepository


@dataclass(frozen=True, slots=True)
class ResearchApplication:
    research_runs: ResearchRunService
    research_repository: ResearchRepository
    signal_repository: SignalRepository
    agent_backend: AgentBackend
    market_data_provider: MarketDataProvider
    document_provider: DocumentProvider
