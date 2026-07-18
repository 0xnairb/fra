"""Application composition root."""

import typer

from fra.application.container import ResearchApplication
from fra.application.doctor_service import DoctorService
from fra.application.research_run_service import ResearchRunService
from fra.cli.app import create_app
from fra.config.loader import validate_configuration
from fra.factories.in_memory import (
    AgentBackendFactory,
    RepositoryFactory,
    SourceAdapterFactory,
    SystemAdapterFactory,
)
from fra.ports.agent_backend import AgentBackend
from fra.ports.clock import Clock
from fra.ports.documents import DocumentProvider
from fra.ports.ids import IdGenerator
from fra.ports.market_data import MarketDataProvider
from fra.ports.repositories import ResearchRepository, SignalRepository


def build_cli() -> typer.Typer:
    """Construct the current application object graph."""
    doctor_service = DoctorService(configuration_probe=validate_configuration)
    return create_app(doctor_service)


def build_in_memory_application(
    *,
    research_repository: ResearchRepository | None = None,
    signal_repository: SignalRepository | None = None,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    agent_backend: AgentBackend | None = None,
    market_data_provider: MarketDataProvider | None = None,
    document_provider: DocumentProvider | None = None,
) -> ResearchApplication:
    """Construct the fully replaceable, hermetic WP1 application graph."""
    research_repository = research_repository or RepositoryFactory.research()
    signal_repository = signal_repository or RepositoryFactory.signals()
    clock = clock or SystemAdapterFactory.clock()
    ids = ids or SystemAdapterFactory.ids()
    agent_backend = agent_backend or AgentBackendFactory.create()
    market_data_provider = market_data_provider or SourceAdapterFactory.market_data()
    document_provider = document_provider or SourceAdapterFactory.documents()
    return ResearchApplication(
        research_runs=ResearchRunService(research_repository, clock, ids),
        research_repository=research_repository,
        signal_repository=signal_repository,
        agent_backend=agent_backend,
        market_data_provider=market_data_provider,
        document_provider=document_provider,
    )


def main() -> None:
    """Construct and run the FRA application."""
    build_cli()()
