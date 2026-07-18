"""Deterministic agent backend used by default WP1 tests."""

from datetime import UTC, datetime

from fra.domain.shared import HealthState, HealthStatus
from fra.ports.agent_backend import (
    AgentBackend,
    AgentCapabilities,
    AgentEvent,
    AgentEventHandler,
    AgentResultStatus,
    AgentStageRequest,
    AgentStageResult,
    StructuredAgentOutput,
)


class FakeAgentBackend(AgentBackend):
    def __init__(
        self,
        *,
        result: StructuredAgentOutput | None = None,
        now: datetime = datetime(2000, 1, 1, tzinfo=UTC),
    ) -> None:
        self._result = result or StructuredAgentOutput({"status": "ok"})
        self._now = now
        self.requests: list[AgentStageRequest] = []

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            structured_output=True,
            session_resume=True,
            event_streaming=True,
            provider_name="fake_agent",
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(HealthState.HEALTHY, self._now, "fake agent ready")

    async def execute(
        self,
        request: AgentStageRequest,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult:
        self.requests.append(request)
        if on_event is not None:
            outcome = on_event(AgentEvent("completed", "fake stage complete", self._now))
            if outcome is not None:
                await outcome
        return AgentStageResult(
            status=AgentResultStatus.COMPLETED,
            output=self._result,
            final_text=None,
            provider_name="fake_agent",
            provider_session_id="fake-session",
            started_at=self._now,
            ended_at=self._now,
        )

    async def resume(
        self,
        provider_session_id: str,
        request: AgentStageRequest,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult:
        del provider_session_id
        return await self.execute(request, on_event)
