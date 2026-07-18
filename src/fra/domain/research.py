"""Research mandate, evidence, claim, and run-state policies."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from fra.domain.errors import (
    DomainValidationError,
    InvalidStateTransitionError,
    LookAheadEvidenceError,
)
from fra.domain.ids import (
    CalculationId,
    ClaimId,
    EvidenceId,
    MandateId,
    PlanId,
    ResearchRunId,
    ScenarioId,
    VerificationId,
)
from fra.domain.shared import Failure
from fra.domain.sources import DataEnvelope, DataKind
from fra.domain.time import as_utc


class ResearchMandateType(StrEnum):
    GENERAL_RESEARCH = "general_research"
    CRYPTO_MARKET_TIMING = "crypto_market_timing"
    ASSET_ALLOCATION = "asset_allocation"
    CRISIS_IMPACT = "crisis_impact"


@dataclass(frozen=True, slots=True)
class ResearchMandate:
    id: MandateId
    kind: ResearchMandateType
    question: str
    created_at: datetime
    user_facts: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    horizon: str | None = None
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise DomainValidationError("research question must not be empty")
        names = tuple(name for name, _value in self.parameters)
        if len(names) != len(set(names)) or any(not name.strip() for name in names):
            raise DomainValidationError("research mandate parameters require unique names")
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))


@dataclass(frozen=True, slots=True)
class ResearchPlanTask:
    task_id: str
    description: str
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.description.strip():
            raise DomainValidationError("research plan task requires identity and description")
        if len(self.depends_on) != len(set(self.depends_on)) or self.task_id in self.depends_on:
            raise DomainValidationError(
                "research plan task dependencies must be unique and acyclic"
            )


@dataclass(frozen=True, slots=True)
class ResearchDataRequirement:
    requirement_id: str
    description: str
    data_kind: DataKind
    subject_ids: tuple[str, ...]
    fields: tuple[str, ...]
    geography_or_market: str | None = None
    resolution: str | None = None
    freshness: str | None = None

    def __post_init__(self) -> None:
        if not self.requirement_id.strip() or not self.description.strip():
            raise DomainValidationError(
                "research data requirement requires identity and description"
            )
        if not self.subject_ids or any(not item.strip() for item in self.subject_ids):
            raise DomainValidationError("research data requirement requires subjects")
        if not self.fields or any(not item.strip() for item in self.fields):
            raise DomainValidationError("research data requirement requires fields")


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    id: PlanId
    run_id: ResearchRunId
    objective: str
    tasks: tuple[ResearchPlanTask, ...]
    data_requirements: tuple[ResearchDataRequirement, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.objective.strip() or not self.tasks or not self.data_requirements:
            raise DomainValidationError(
                "research plan requires an objective, tasks, and typed data requirements"
            )
        task_ids = tuple(item.task_id for item in self.tasks)
        requirement_ids = tuple(item.requirement_id for item in self.data_requirements)
        if len(task_ids) != len(set(task_ids)) or len(requirement_ids) != len(set(requirement_ids)):
            raise DomainValidationError("research plan identities must be unique")
        known_tasks = set(task_ids)
        if any(
            dependency not in known_tasks for task in self.tasks for dependency in task.depends_on
        ):
            raise DomainValidationError("research plan task dependency is unknown")
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))


@dataclass(frozen=True, slots=True)
class Evidence[EvidenceValueT]:
    id: EvidenceId
    run_id: ResearchRunId
    kind: DataKind
    summary: str
    envelope: DataEnvelope[EvidenceValueT]
    knowledge_cutoff_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise DomainValidationError("evidence summary must not be empty")
        object.__setattr__(
            self,
            "knowledge_cutoff_at",
            as_utc(self.knowledge_cutoff_at, field="knowledge_cutoff_at"),
        )
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))
        if self.envelope.available_at > self.knowledge_cutoff_at:
            raise LookAheadEvidenceError(
                "available_at cannot occur after the evidence knowledge cutoff"
            )

    @classmethod
    def from_envelope(
        cls,
        *,
        id: EvidenceId,
        run_id: ResearchRunId,
        kind: DataKind,
        summary: str,
        envelope: DataEnvelope[EvidenceValueT],
        knowledge_cutoff_at: datetime,
        created_at: datetime,
    ) -> Evidence[EvidenceValueT]:
        return cls(
            id=id,
            run_id=run_id,
            kind=kind,
            summary=summary,
            envelope=envelope,
            knowledge_cutoff_at=knowledge_cutoff_at,
            created_at=created_at,
        )

    @property
    def provider_id(self) -> str:
        return self.envelope.descriptor.provider_id

    @property
    def value(self) -> EvidenceValueT:
        return self.envelope.value

    @property
    def available_at(self) -> datetime:
        return self.envelope.available_at


class ClaimMateriality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ClaimStatus(StrEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"
    CONFLICTING = "conflicting"


class ClaimConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class Claim:
    id: ClaimId
    run_id: ResearchRunId
    statement: str
    materiality: ClaimMateriality
    status: ClaimStatus
    confidence: ClaimConfidence
    evidence_ids: tuple[EvidenceId, ...]
    created_at: datetime
    limitations: tuple[str, ...] = ()
    calculation_ids: tuple[CalculationId, ...] = ()

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise DomainValidationError("claim statement must not be empty")
        if self.materiality is ClaimMateriality.HIGH and not (
            self.evidence_ids or self.calculation_ids
        ):
            raise DomainValidationError("a material claim requires supporting evidence")
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))


@dataclass(frozen=True, slots=True)
class ResearchScenario:
    id: ScenarioId
    run_id: ResearchRunId
    title: str
    description: str
    evidence_ids: tuple[EvidenceId, ...]
    invalidation_conditions: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.description.strip():
            raise DomainValidationError("research scenario requires a title and description")
        if not self.evidence_ids or not self.invalidation_conditions:
            raise DomainValidationError("research scenario requires evidence and invalidation")
        if any(not item.strip() for item in self.invalidation_conditions):
            raise DomainValidationError("scenario invalidation conditions must not be empty")
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))


class VerificationSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class VerificationIssue:
    code: str
    message: str
    severity: VerificationSeverity
    claim_id: ClaimId | None = None

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip():
            raise DomainValidationError("verification issue requires a code and message")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    id: VerificationId
    run_id: ResearchRunId
    passed: bool
    deterministic_passed: bool
    agent_passed: bool
    issues: tuple[VerificationIssue, ...]
    checked_at: datetime

    def __post_init__(self) -> None:
        has_blocking_issue = any(
            issue.severity is VerificationSeverity.HIGH for issue in self.issues
        )
        if self.passed != (
            self.deterministic_passed and self.agent_passed and not has_blocking_issue
        ):
            raise DomainValidationError("verification pass state must match its component checks")
        object.__setattr__(self, "checked_at", as_utc(self.checked_at, field="checked_at"))


class ResearchRunState(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    COLLECTING_EVIDENCE = "collecting_evidence"
    ANALYZING = "analyzing"
    VERIFYING = "verifying"
    NEEDS_RESEARCH = "needs_research"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_USER_INPUT = "needs_user_input"


_ACTIVE_STATES = frozenset(
    {
        ResearchRunState.CREATED,
        ResearchRunState.PLANNING,
        ResearchRunState.COLLECTING_EVIDENCE,
        ResearchRunState.ANALYZING,
        ResearchRunState.VERIFYING,
        ResearchRunState.NEEDS_RESEARCH,
        ResearchRunState.SYNTHESIZING,
    }
)
_INTERRUPTED_STATES = frozenset(
    {ResearchRunState.FAILED, ResearchRunState.CANCELLED, ResearchRunState.NEEDS_USER_INPUT}
)
_NEXT_STATES: dict[ResearchRunState, frozenset[ResearchRunState]] = {
    ResearchRunState.CREATED: frozenset({ResearchRunState.PLANNING}),
    ResearchRunState.PLANNING: frozenset({ResearchRunState.COLLECTING_EVIDENCE}),
    ResearchRunState.COLLECTING_EVIDENCE: frozenset({ResearchRunState.ANALYZING}),
    ResearchRunState.ANALYZING: frozenset({ResearchRunState.VERIFYING}),
    ResearchRunState.VERIFYING: frozenset(
        {ResearchRunState.NEEDS_RESEARCH, ResearchRunState.SYNTHESIZING}
    ),
    ResearchRunState.NEEDS_RESEARCH: frozenset({ResearchRunState.COLLECTING_EVIDENCE}),
    ResearchRunState.SYNTHESIZING: frozenset({ResearchRunState.COMPLETED}),
}


@dataclass(frozen=True, slots=True)
class AgentRunMetadata:
    provider_name: str
    adapter_version: str
    cli_version: str | None
    model: str | None
    provider_session_id: str | None
    prompt_versions: tuple[tuple[str, int], ...]
    output_schema_versions: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not self.provider_name.strip() or not self.adapter_version.strip():
            raise DomainValidationError("agent run metadata requires provider and adapter versions")


@dataclass(frozen=True, slots=True)
class ResearchStageCheckpoint:
    stage: str
    stage_id: str
    completed_at: datetime
    result_json: str

    def __post_init__(self) -> None:
        if not self.stage.strip() or not self.stage_id.strip() or not self.result_json.strip():
            raise DomainValidationError("research checkpoint fields must not be empty")
        object.__setattr__(self, "completed_at", as_utc(self.completed_at, field="completed_at"))


@dataclass(frozen=True, slots=True)
class ResearchRun:
    id: ResearchRunId
    mandate: ResearchMandate
    state: ResearchRunState
    created_at: datetime
    updated_at: datetime
    state_history: tuple[ResearchRunState, ...]
    completed_at: datetime | None = None
    failure: Failure | None = None
    agent_metadata: AgentRunMetadata | None = None
    stage_checkpoints: tuple[ResearchStageCheckpoint, ...] = ()
    stage_attempts: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))
        object.__setattr__(self, "updated_at", as_utc(self.updated_at, field="updated_at"))
        if self.completed_at is not None:
            object.__setattr__(
                self, "completed_at", as_utc(self.completed_at, field="completed_at")
            )
        if self.updated_at < self.created_at:
            raise DomainValidationError("research run updated_at cannot precede created_at")
        if not self.state_history or self.state_history[-1] is not self.state:
            raise DomainValidationError("research run history must end at its current state")
        if self.state is ResearchRunState.COMPLETED and self.completed_at is None:
            raise DomainValidationError("completed research run requires completed_at")

    @classmethod
    def create(
        cls, id: ResearchRunId, mandate: ResearchMandate, created_at: datetime
    ) -> ResearchRun:
        created_at = as_utc(created_at, field="created_at")
        return cls(
            id=id,
            mandate=mandate,
            state=ResearchRunState.CREATED,
            created_at=created_at,
            updated_at=created_at,
            state_history=(ResearchRunState.CREATED,),
        )

    def transition(
        self,
        target: ResearchRunState,
        transitioned_at: datetime,
        *,
        failure: Failure | None = None,
    ) -> ResearchRun:
        transitioned_at = as_utc(transitioned_at, field="transitioned_at")
        if transitioned_at < self.updated_at:
            raise DomainValidationError("transition time cannot precede the previous update")
        allowed = set(_NEXT_STATES.get(self.state, frozenset()))
        if self.state in _ACTIVE_STATES:
            allowed.update(_INTERRUPTED_STATES)
        if target not in allowed:
            raise InvalidStateTransitionError(
                f"research run cannot transition from {self.state.value} to {target.value}"
            )
        if failure is not None and target not in {
            ResearchRunState.FAILED,
            ResearchRunState.NEEDS_USER_INPUT,
        }:
            raise DomainValidationError("failure may only accompany a failed or input-needed run")
        completed_at = transitioned_at if target is ResearchRunState.COMPLETED else None
        return replace(
            self,
            state=target,
            updated_at=transitioned_at,
            state_history=(*self.state_history, target),
            completed_at=completed_at,
            failure=failure,
        )

    def resume(self, target: ResearchRunState, resumed_at: datetime) -> ResearchRun:
        resumed_at = as_utc(resumed_at, field="resumed_at")
        if self.state not in _INTERRUPTED_STATES:
            raise InvalidStateTransitionError(f"research run cannot resume from {self.state.value}")
        if target not in _ACTIVE_STATES:
            raise InvalidStateTransitionError(f"research run cannot resume into {target.value}")
        if resumed_at < self.updated_at:
            raise DomainValidationError("resume time cannot precede the previous update")
        return replace(
            self,
            state=target,
            updated_at=resumed_at,
            state_history=(*self.state_history, target),
            failure=None,
        )
