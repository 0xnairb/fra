from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from fra.adapters.agents.claude_cli import ClaudeCliAgentAdapter
from fra.domain.ids import ResearchRunId, StageId
from fra.ports.agent_backend import (
    AgentResultStatus,
    AgentStageRequest,
    AgentStageType,
    JsonValue,
)


@pytest.mark.skipif(
    os.environ.get("FRA_RUN_LIVE_CLAUDE") != "1",
    reason="set FRA_RUN_LIVE_CLAUDE=1 to use installed Claude authentication and quota",
)
def test_installed_claude_structured_output_smoke() -> None:
    backend = ClaudeCliAgentAdapter(binary="claude", permission_mode="plan")
    health = asyncio.run(backend.health())
    assert health.ok, health.summary

    schema: Mapping[str, JsonValue] = {
        "type": "object",
        "properties": {"status": {"type": "string", "const": "ok"}},
        "required": ("status",),
        "additionalProperties": False,
    }
    result = asyncio.run(
        backend.execute(
            AgentStageRequest(
                run_id=ResearchRunId("run_live_claude_smoke"),
                stage_id=StageId("stage_live_claude_smoke"),
                stage_type=AgentStageType.PLAN,
                instructions='Return {"status": "ok"} and perform no tool calls.',
                evidence_ids=(),
                timeout_seconds=60,
                output_schema=schema,
                working_directory=Path.cwd(),
            )
        )
    )

    assert result.status is AgentResultStatus.COMPLETED
    assert result.output is not None
    assert result.output.values == {"status": "ok"}
