import asyncio
from pathlib import Path

from fra.adapters.agents.claude_cli import ClaudeCliAgentAdapter
from fra.domain.ids import ResearchRunId, StageId
from fra.domain.shared import FailureKind, HealthState
from fra.ports.agent_backend import AgentResultStatus, AgentStageRequest, AgentStageType

FIXTURE = Path(__file__).parents[2] / "fixtures" / "agent_backends" / "fake_claude.py"


def _request(tmp_path: Path, timeout: int = 5) -> AgentStageRequest:
    return AgentStageRequest(
        ResearchRunId("run_0001"),
        StageId("stage_0001"),
        AgentStageType.PLAN,
        "Return the fixture plan.",
        (),
        timeout,
        {"type": "object"},
        working_directory=tmp_path,
    )


def test_claude_contract_health_execute_resume_and_schema_output(tmp_path: Path) -> None:
    adapter = ClaudeCliAgentAdapter(
        binary=str(FIXTURE),
        environment={"FAKE_CLAUDE_OUTPUT": '{"status":"ok"}'},
    )

    health = asyncio.run(adapter.health())
    result = asyncio.run(adapter.execute(_request(tmp_path)))
    resumed = asyncio.run(adapter.resume("claude-session", _request(tmp_path)))

    assert health.state is HealthState.HEALTHY
    assert result.status is AgentResultStatus.COMPLETED
    assert result.output is not None and result.output.values == {"status": "ok"}
    assert result.provider_session_id == "claude-session"
    assert resumed.provider_session_id == "claude-session-resumed"
    assert result.usage is not None and result.usage.input_tokens == 11


def test_claude_contract_classifies_auth_and_malformed_output(tmp_path: Path) -> None:
    auth = ClaudeCliAgentAdapter(
        binary=str(FIXTURE),
        environment={"FAKE_CLAUDE_MODE": "auth_failure"},
        secrets=("fake-secret",),
    )
    malformed = ClaudeCliAgentAdapter(
        binary=str(FIXTURE), environment={"FAKE_CLAUDE_MODE": "malformed"}
    )

    health = asyncio.run(auth.health())
    result = asyncio.run(malformed.execute(_request(tmp_path)))

    assert health.failure is not None
    assert health.failure.kind is FailureKind.AUTHENTICATION_REQUIRED
    assert "fake-secret" not in health.failure.message
    assert result.failure is not None
    assert result.failure.kind is FailureKind.STRUCTURED_OUTPUT_INVALID


def test_claude_timeout_terminates_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "child-survived"
    adapter = ClaudeCliAgentAdapter(
        binary=str(FIXTURE),
        environment={
            "FAKE_CLAUDE_MODE": "timeout",
            "FAKE_CLAUDE_CHILD_MARKER": str(marker),
        },
    )

    result = asyncio.run(adapter.execute(_request(tmp_path, 1)))
    asyncio.run(asyncio.sleep(1.2))

    assert result.failure is not None and result.failure.kind is FailureKind.TIMEOUT
    assert not marker.exists()
