from datetime import UTC, datetime, timedelta

import pytest

from fra.domain.errors import InvalidStateTransitionError
from fra.domain.ids import MandateId, ResearchRunId
from fra.domain.research import (
    ResearchMandate,
    ResearchMandateType,
    ResearchRun,
    ResearchRunState,
)

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def make_run() -> ResearchRun:
    mandate = ResearchMandate(
        id=MandateId("mandate_0001"),
        kind=ResearchMandateType.GENERAL_RESEARCH,
        question="What changed?",
        created_at=NOW,
    )
    return ResearchRun.create(ResearchRunId("run_0001"), mandate, NOW)


def test_research_run_can_follow_the_complete_happy_path() -> None:
    run = make_run()
    path = (
        ResearchRunState.PLANNING,
        ResearchRunState.COLLECTING_EVIDENCE,
        ResearchRunState.ANALYZING,
        ResearchRunState.VERIFYING,
        ResearchRunState.SYNTHESIZING,
        ResearchRunState.COMPLETED,
    )

    for offset, state in enumerate(path, start=1):
        run = run.transition(state, NOW + timedelta(minutes=offset))

    assert run.state is ResearchRunState.COMPLETED
    assert run.completed_at == NOW + timedelta(minutes=len(path))
    assert run.state_history == (ResearchRunState.CREATED, *path)


def test_verification_can_request_more_research_then_rejoin_collection() -> None:
    run = make_run()
    for state in (
        ResearchRunState.PLANNING,
        ResearchRunState.COLLECTING_EVIDENCE,
        ResearchRunState.ANALYZING,
        ResearchRunState.VERIFYING,
        ResearchRunState.NEEDS_RESEARCH,
        ResearchRunState.COLLECTING_EVIDENCE,
    ):
        run = run.transition(state, run.updated_at + timedelta(minutes=1))

    assert run.state is ResearchRunState.COLLECTING_EVIDENCE


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (ResearchRunState.CREATED, ResearchRunState.ANALYZING),
        (ResearchRunState.PLANNING, ResearchRunState.SYNTHESIZING),
        (ResearchRunState.COMPLETED, ResearchRunState.VERIFYING),
        (ResearchRunState.CANCELLED, ResearchRunState.PLANNING),
    ],
)
def test_stages_cannot_be_skipped_or_terminal_runs_reopened(
    source: ResearchRunState, target: ResearchRunState
) -> None:
    run = make_run()
    if source is not ResearchRunState.CREATED:
        path_to_source = {
            ResearchRunState.PLANNING: (ResearchRunState.PLANNING,),
            ResearchRunState.COMPLETED: (
                ResearchRunState.PLANNING,
                ResearchRunState.COLLECTING_EVIDENCE,
                ResearchRunState.ANALYZING,
                ResearchRunState.VERIFYING,
                ResearchRunState.SYNTHESIZING,
                ResearchRunState.COMPLETED,
            ),
            ResearchRunState.CANCELLED: (ResearchRunState.CANCELLED,),
        }[source]
        for state in path_to_source:
            run = run.transition(state, run.updated_at + timedelta(minutes=1))

    with pytest.raises(InvalidStateTransitionError, match="cannot transition"):
        run.transition(target, run.updated_at + timedelta(minutes=1))
