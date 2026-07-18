"""Factories for the replaceable WP1 in-memory object graph."""

from datetime import UTC, datetime

from fra.adapters.fakes.agent import FakeAgentBackend
from fra.adapters.fakes.documents import FakeDocumentProvider
from fra.adapters.fakes.economic_series import FakeEconomicSeriesProvider
from fra.adapters.fakes.market_data import FakeMarketDataProvider
from fra.adapters.in_memory.repositories import InMemoryResearchRepository, InMemorySignalRepository
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.ports.agent_backend import AgentBackend
from fra.ports.clock import Clock
from fra.ports.documents import DocumentProvider
from fra.ports.economic_series import EconomicSeriesProvider
from fra.ports.ids import IdGenerator
from fra.ports.market_data import MarketDataProvider
from fra.ports.repositories import ResearchRepository, SignalRepository


class RepositoryFactory:
    @staticmethod
    def research() -> ResearchRepository:
        return InMemoryResearchRepository()

    @staticmethod
    def signals() -> SignalRepository:
        return InMemorySignalRepository()


class AgentBackendFactory:
    @staticmethod
    def create() -> AgentBackend:
        return FakeAgentBackend()


class SourceAdapterFactory:
    @staticmethod
    def market_data() -> MarketDataProvider:
        return FakeMarketDataProvider()

    @staticmethod
    def documents() -> DocumentProvider:
        return FakeDocumentProvider()

    @staticmethod
    def economic_series() -> EconomicSeriesProvider:
        return FakeEconomicSeriesProvider()


class SystemAdapterFactory:
    @staticmethod
    def clock() -> Clock:
        return FixedClock(datetime(2000, 1, 1, tzinfo=UTC))

    @staticmethod
    def ids() -> IdGenerator:
        return SequenceIdGenerator()
