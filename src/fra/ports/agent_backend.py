"""Vendor-neutral structured agent execution port."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from fra.domain.errors import DomainValidationError
from fra.domain.ids import EvidenceId, ResearchRunId, StageId
from fra.domain.shared import Failure, HealthStatus
from fra.domain.time import as_utc

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]


class AgentStageType(StrEnum):
    PLAN = "plan"
    ANALYZE = "analyze"
    VERIFY = "verify"
    SYNTHESIZE = "synthesize"


class AgentResultStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AgentCapabilities:
    structured_output: bool
    session_resume: bool
    event_streaming: bool
    provider_name: str


@dataclass(frozen=True, slots=True)
class StructuredAgentOutput:
    """Validated provider-neutral structured content."""

    values: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AgentEvent:
    kind: str
    message: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", as_utc(self.occurred_at, field="occurred_at"))


AgentEventHandler = Callable[[AgentEvent], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class AgentStageRequest:
    run_id: ResearchRunId
    stage_id: StageId
    stage_type: AgentStageType
    instructions: str
    evidence_ids: tuple[EvidenceId, ...]
    timeout_seconds: int
    output_schema: Mapping[str, JsonValue]
    provider_session_id: str | None = None

    def __post_init__(self) -> None:
        if not self.instructions.strip():
            raise DomainValidationError("agent stage instructions must not be empty")
        if self.timeout_seconds <= 0:
            raise DomainValidationError("agent stage timeout must be positive")


@dataclass(frozen=True, slots=True)
class AgentStageResult:
    status: AgentResultStatus
    output: StructuredAgentOutput | None
    final_text: str | None
    provider_name: str
    started_at: datetime
    ended_at: datetime
    provider_session_id: str | None = None
    cli_version: str | None = None
    model: str | None = None
    warnings: tuple[str, ...] = ()
    failure: Failure | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "started_at", as_utc(self.started_at, field="started_at"))
        object.__setattr__(self, "ended_at", as_utc(self.ended_at, field="ended_at"))
        if self.ended_at < self.started_at:
            raise DomainValidationError("agent stage cannot end before it starts")
        if self.status is AgentResultStatus.COMPLETED and self.output is None:
            raise DomainValidationError("completed agent stage requires structured output")


class AgentBackend(Protocol):
    def capabilities(self) -> AgentCapabilities: ...

    async def health(self) -> HealthStatus: ...

    async def execute(
        self,
        request: AgentStageRequest,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult: ...

    async def resume(
        self,
        provider_session_id: str,
        request: AgentStageRequest,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult: ...
