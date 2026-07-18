from datetime import UTC, datetime, timedelta

from fra.adapters.fakes.agent import FakeAgentBackend
from fra.adapters.fakes.documents import FakeDocumentProvider
from fra.adapters.fakes.market_data import FakeMarketDataProvider
from fra.adapters.in_memory.repositories import InMemoryResearchRepository, InMemorySignalRepository
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.bootstrap import build_in_memory_application
from fra.domain.research import ResearchMandateType, ResearchRunState

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def test_bootstrap_can_replace_every_wp1_boundary_without_changing_the_use_case() -> None:
    research = InMemoryResearchRepository()
    signals = InMemorySignalRepository()
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator(start=40)
    agent = FakeAgentBackend()
    market = FakeMarketDataProvider()
    documents = FakeDocumentProvider()

    application = build_in_memory_application(
        research_repository=research,
        signal_repository=signals,
        clock=clock,
        ids=ids,
        agent_backend=agent,
        market_data_provider=market,
        document_provider=documents,
    )

    assert application.research_repository is research
    assert application.signal_repository is signals
    assert application.agent_backend is agent
    assert application.market_data_provider is market
    assert application.document_provider is documents

    result = application.research_runs.start(
        "Can the in-memory graph complete?", ResearchMandateType.GENERAL_RESEARCH
    )
    assert result.value is not None
    run = result.value
    for state in (
        ResearchRunState.PLANNING,
        ResearchRunState.COLLECTING_EVIDENCE,
        ResearchRunState.ANALYZING,
        ResearchRunState.VERIFYING,
        ResearchRunState.SYNTHESIZING,
        ResearchRunState.COMPLETED,
    ):
        clock.advance(timedelta(minutes=1))
        transitioned = application.research_runs.transition(run.id, state)
        assert transitioned.value is not None
        run = transitioned.value

    assert run.state is ResearchRunState.COMPLETED
