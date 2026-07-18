from __future__ import annotations

import asyncio
from pathlib import Path

from fra.adapters.agents.codex_cli import CodexCliAgentAdapter
from fra.domain.ids import ResearchRunId, StageId
from fra.domain.shared import FailureKind, HealthState
from fra.ports.agent_backend import (
    AgentEvent,
    AgentResultStatus,
    AgentStageRequest,
    AgentStageResult,
    AgentStageType,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "agent_backends" / "fake_codex.py"


def _request(tmp_path: Path, *, timeout: int = 5) -> AgentStageRequest:
    return AgentStageRequest(
        run_id=ResearchRunId("run_0001"),
        stage_id=StageId("stage_0001"),
        stage_type=AgentStageType.PLAN,
        instructions="Return the fixture plan.",
        evidence_ids=(),
        timeout_seconds=timeout,
        output_schema={"type": "object"},
        working_directory=tmp_path,
    )


def test_codex_contract_health_execute_resume_and_redaction(tmp_path: Path) -> None:
    adapter = CodexCliAgentAdapter(
        binary=str(FIXTURE),
        sandbox="read-only",
        environment={
            "FAKE_CODEX_OUTPUT": '{"status":"ok"}',
            "FAKE_CODEX_REQUIRE_SKIP_GIT": "1",
            "FRA_TEST_SECRET": "fake-secret",
        },
        secrets=("fake-secret",),
    )
    events: list[AgentEvent] = []

    health = asyncio.run(adapter.health())
    result = asyncio.run(adapter.execute(_request(tmp_path), events.append))
    resumed = asyncio.run(adapter.resume("fixture-session", _request(tmp_path), events.append))

    assert health.state is HealthState.HEALTHY
    assert "0.999.0" in health.summary
    assert result.status is AgentResultStatus.COMPLETED
    assert result.output is not None and result.output.values == {"status": "ok"}
    assert result.provider_session_id == "fixture-session"
    assert resumed.provider_session_id == "fixture-session-resumed"
    assert result.cli_version == "0.999.0"
    assert result.usage is not None and result.usage.input_tokens == 10
    assert all("fake-secret" not in event.message for event in events)
    assert all("fake-secret" not in warning for warning in result.warnings)


def test_codex_contract_classifies_authentication_and_malformed_output(tmp_path: Path) -> None:
    unauthenticated = CodexCliAgentAdapter(
        binary=str(FIXTURE), environment={"FAKE_CODEX_MODE": "auth_failure"}
    )
    malformed = CodexCliAgentAdapter(
        binary=str(FIXTURE), environment={"FAKE_CODEX_MODE": "malformed"}
    )

    health = asyncio.run(unauthenticated.health())
    result = asyncio.run(malformed.execute(_request(tmp_path)))

    assert health.state is HealthState.UNAVAILABLE
    assert health.failure is not None
    assert health.failure.kind is FailureKind.AUTHENTICATION_REQUIRED
    assert "fake-secret" not in health.failure.message
    assert result.status is AgentResultStatus.FAILED
    assert result.failure is not None
    assert result.failure.kind is FailureKind.STRUCTURED_OUTPUT_INVALID


def test_codex_health_rejects_a_missing_configured_profile(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    adapter = CodexCliAgentAdapter(
        binary=str(FIXTURE),
        profile="fra",
        environment={"CODEX_HOME": str(codex_home)},
    )

    health = asyncio.run(adapter.health())

    assert health.state is HealthState.UNAVAILABLE
    assert health.failure is not None
    assert health.failure.kind is FailureKind.CAPABILITY_UNAVAILABLE
    assert "profile 'fra'" in health.summary
    assert "fra.config.toml" in health.summary


def test_codex_contract_preserves_jsonl_failure_detail(tmp_path: Path) -> None:
    adapter = CodexCliAgentAdapter(
        binary=str(FIXTURE),
        environment={"FAKE_CODEX_MODE": "jsonl_error"},
    )

    result = asyncio.run(adapter.execute(_request(tmp_path)))

    assert result.status is AgentResultStatus.FAILED
    assert result.failure is not None
    assert result.failure.message == "fixture JSONL failure"


def test_timeout_terminates_the_complete_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "child-survived"
    adapter = CodexCliAgentAdapter(
        binary=str(FIXTURE),
        environment={
            "FAKE_CODEX_MODE": "timeout",
            "FAKE_CODEX_CHILD_MARKER": str(marker),
        },
    )

    result = asyncio.run(adapter.execute(_request(tmp_path, timeout=1)))
    asyncio.run(asyncio.sleep(1.2))

    assert result.status is AgentResultStatus.FAILED
    assert result.failure is not None and result.failure.kind is FailureKind.TIMEOUT
    assert not marker.exists()


def test_task_cancellation_terminates_the_group_and_returns_a_typed_result(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "child-survived"
    adapter = CodexCliAgentAdapter(
        binary=str(FIXTURE),
        environment={
            "FAKE_CODEX_MODE": "cancel",
            "FAKE_CODEX_CHILD_MARKER": str(marker),
        },
    )

    async def cancel() -> AgentStageResult:
        task = asyncio.create_task(adapter.execute(_request(tmp_path, timeout=10)))
        await asyncio.sleep(0.1)
        task.cancel()
        return await task

    result = asyncio.run(cancel())
    asyncio.run(asyncio.sleep(1.2))

    assert result.status is AgentResultStatus.CANCELLED
    assert not marker.exists()
