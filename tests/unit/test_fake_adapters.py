import asyncio
from datetime import UTC, datetime

import pytest

from fra.adapters.fakes.agent import FakeAgentBackend
from fra.adapters.fakes.documents import FakeDocumentProvider
from fra.adapters.fakes.market_data import FakeMarketDataProvider
from fra.domain.documents import DocumentQuery
from fra.domain.errors import CapabilityUnavailableError
from fra.domain.ids import ResearchRunId, StageId
from fra.domain.shared import HealthState
from fra.ports.agent_backend import AgentStageRequest, AgentStageType


def test_fake_agent_is_deterministic_and_returns_an_fra_owned_result() -> None:
    backend = FakeAgentBackend(now=datetime(2026, 7, 18, 8, tzinfo=UTC))
    request = AgentStageRequest(
        run_id=ResearchRunId("run_0001"),
        stage_id=StageId("stage_0001"),
        stage_type=AgentStageType.PLAN,
        instructions="Create a fixture plan.",
        evidence_ids=(),
        timeout_seconds=10,
        output_schema={"type": "object"},
    )

    result = asyncio.run(backend.execute(request))
    health = asyncio.run(backend.health())

    assert result.output is not None
    assert result.output.values == {"status": "ok"}
    assert health.state is HealthState.HEALTHY
    assert backend.requests == [request]


def test_empty_fake_sources_return_typed_capability_failures() -> None:
    documents = FakeDocumentProvider()
    market = FakeMarketDataProvider()

    with pytest.raises(CapabilityUnavailableError, match="document search"):
        asyncio.run(documents.search(DocumentQuery("fixture")))

    assert market.descriptor().provider_id == "fake_market"
    assert documents.descriptor().provider_id == "fake_documents"
