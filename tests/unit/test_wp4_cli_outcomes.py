from datetime import UTC, datetime

import pytest
import typer

from fra.cli.app import _show_research_outcome
from fra.cli.exit_codes import ExitCode
from fra.domain.ids import MandateId, ResearchRunId
from fra.domain.research import (
    ResearchMandate,
    ResearchMandateType,
    ResearchRun,
    ResearchRunState,
)
from fra.domain.shared import Failure, FailureKind

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def _active_run() -> ResearchRun:
    mandate = ResearchMandate(
        MandateId("mandate_0001"),
        ResearchMandateType.GENERAL_RESEARCH,
        "What changed?",
        NOW,
    )
    return ResearchRun.create(ResearchRunId("run_0001"), mandate, NOW).transition(
        ResearchRunState.PLANNING, NOW
    )


def test_cancelled_research_has_the_stable_incomplete_exit_result() -> None:
    cancelled = _active_run().transition(ResearchRunState.CANCELLED, NOW)

    with pytest.raises(typer.Exit) as raised:
        _show_research_outcome(cancelled)

    assert raised.value.exit_code == ExitCode.INCOMPLETE


def test_agent_authentication_failure_has_the_external_dependency_exit_result() -> None:
    failed = _active_run().transition(
        ResearchRunState.FAILED,
        NOW,
        failure=Failure(
            FailureKind.AUTHENTICATION_REQUIRED,
            "Codex login required",
            provider_id="codex_cli",
        ),
    )

    with pytest.raises(typer.Exit) as raised:
        _show_research_outcome(failed)

    assert raised.value.exit_code == ExitCode.EXTERNAL_DEPENDENCY
