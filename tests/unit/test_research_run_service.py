from datetime import UTC, datetime, timedelta

from fra.adapters.in_memory.repositories import InMemoryResearchRepository
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.application.research_run_service import ResearchRunService
from fra.domain.research import ResearchMandateType, ResearchRunState
from fra.domain.shared import FailureKind

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def test_service_returns_typed_results_for_success_and_expected_domain_failure() -> None:
    clock = FixedClock(NOW)
    service = ResearchRunService(InMemoryResearchRepository(), clock, SequenceIdGenerator())

    started = service.start("What changed?", ResearchMandateType.GENERAL_RESEARCH)
    assert started.ok is True
    assert started.value is not None

    invalid = service.transition(started.value.id, ResearchRunState.ANALYZING)
    assert invalid.ok is False
    assert invalid.failure is not None
    assert invalid.failure.kind is FailureKind.INVALID_STATE_TRANSITION

    clock.advance(timedelta(minutes=1))
    planning = service.transition(started.value.id, ResearchRunState.PLANNING)
    assert planning.ok is True
    assert planning.value is not None
    assert planning.value.state is ResearchRunState.PLANNING
