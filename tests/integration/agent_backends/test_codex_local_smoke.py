from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from fra.adapters.agents.codex_cli import CodexCliAgentAdapter
from fra.domain.ids import ResearchRunId, StageId
from fra.ports.agent_backend import (
    AgentResultStatus,
    AgentStageRequest,
    AgentStageType,
    JsonValue,
)


@pytest.mark.skipif(
    os.environ.get("FRA_RUN_LIVE_CODEX") != "1",
    reason="set FRA_RUN_LIVE_CODEX=1 to use installed Codex authentication and quota",
)
def test_installed_codex_structured_output_smoke() -> None:
    backend = CodexCliAgentAdapter(binary="codex", sandbox="read-only")
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
                run_id=ResearchRunId("run_live_smoke"),
                stage_id=StageId("stage_live_smoke"),
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
