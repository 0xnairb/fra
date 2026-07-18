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
        results: tuple[StructuredAgentOutput, ...] | None = None,
        cancel_on_request: int | None = None,
        now: datetime = datetime(2000, 1, 1, tzinfo=UTC),
    ) -> None:
        self._result = result or StructuredAgentOutput({"status": "ok"})
        self._results = list(results) if results is not None else None
        self._cancel_on_request = cancel_on_request
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
        if self._cancel_on_request == len(self.requests):
            return AgentStageResult(
                status=AgentResultStatus.CANCELLED,
                output=None,
                final_text=None,
                provider_name="fake_agent",
                provider_session_id="fake-session",
                started_at=self._now,
                ended_at=self._now,
            )
        if on_event is not None:
            outcome = on_event(AgentEvent("completed", "fake stage complete", self._now))
            if outcome is not None:
                await outcome
        output = self._result
        if self._results is not None:
            if not self._results:
                raise AssertionError("fake agent received an unexpected request")
            output = self._results.pop(0)
        return AgentStageResult(
            status=AgentResultStatus.COMPLETED,
            output=output,
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
        request = AgentStageRequest(
            run_id=request.run_id,
            stage_id=request.stage_id,
            stage_type=request.stage_type,
            instructions=request.instructions,
            evidence_ids=request.evidence_ids,
            timeout_seconds=request.timeout_seconds,
            output_schema=request.output_schema,
            provider_session_id=provider_session_id,
            working_directory=request.working_directory,
            allowed_capabilities=request.allowed_capabilities,
        )
        return await self.execute(request, on_event)
