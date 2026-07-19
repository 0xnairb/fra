from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import cast

from fra.adapters.fakes.agent import FakeAgentBackend
from fra.adapters.in_memory.repositories import InMemoryResearchRepository
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.application.agent_schemas import AgentSchemaRegistry
from fra.application.research_orchestrator import ResearchOrchestrator
from fra.application.research_workflows import (
    ResearchRegistry,
    WorkflowCollection,
    WorkflowFinalization,
)
from fra.domain.ids import EvidenceId
from fra.domain.research import (
    Evidence,
    ResearchMandateType,
    ResearchPlan,
    ResearchRun,
    ResearchRunState,
)
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    DataKind,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)
from fra.ports.agent_backend import (
    AgentCapabilities,
    AgentEventHandler,
    AgentStageRequest,
    AgentStageResult,
    StructuredAgentOutput,
)

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def test_agent_schemas_require_every_declared_property_for_strict_cli_output() -> None:
    schemas = AgentSchemaRegistry()

    for stage in ("plan", "analyze", "verify", "synthesize"):
        _assert_all_object_properties_required(schemas.schema_for(stage))


def _assert_all_object_properties_required(value: object) -> None:
    if isinstance(value, dict):
        properties = value.get("properties")
        if value.get("type") == "object" and isinstance(properties, dict):
            required = value.get("required")
            assert isinstance(required, list)
            assert set(required) == set(properties)
        for child in value.values():
            _assert_all_object_properties_required(child)
    elif isinstance(value, list):
        for child in value:
            _assert_all_object_properties_required(child)


def _outputs() -> tuple[StructuredAgentOutput, ...]:
    return (
        StructuredAgentOutput(
            {
                "objective": "Answer the question",
                "tasks": (
                    {
                        "task_id": "task_1",
                        "description": "inspect durable inputs",
                        "depends_on": (),
                    },
                ),
                "data_requirements": (
                    {
                        "requirement_id": "requirement_1",
                        "description": "collect the fixture document",
                        "data_kind": "document",
                        "subject_ids": ("fixture:document",),
                        "fields": ("content",),
                        "geography_or_market": None,
                        "resolution": None,
                        "freshness": None,
                    },
                ),
            }
        ),
        StructuredAgentOutput(
            {
                "claims": (
                    {
                        "statement": "The fixture evidence is available.",
                        "materiality": "high",
                        "confidence": "high",
                        "evidence_ids": ("evidence_fixture",),
                        "calculation_ids": (),
                        "limitations": (),
                    },
                ),
                "scenarios": (
                    {
                        "title": "Base",
                        "description": "The fixture evidence remains available.",
                        "evidence_ids": ("evidence_fixture",),
                        "invalidation_conditions": ("the fixture is withdrawn",),
                    },
                ),
                "open_questions": (),
            }
        ),
        StructuredAgentOutput({"passed": True, "issues": ()}),
        StructuredAgentOutput({"title": "Fixture research", "summary": "Done", "limitations": ()}),
    )


class _FixtureWorkflow:
    def __init__(self) -> None:
        self._collected = False

    def missing_inputs(self, mandate: object) -> tuple[str, ...]:
        return ()

    async def collect(self, run: ResearchRun, plan: ResearchPlan) -> WorkflowCollection:
        assert plan.data_requirements[0].data_kind is DataKind.DOCUMENT
        if self._collected:
            return WorkflowCollection((), (), {"evidence_ids": ("evidence_fixture",)})
        self._collected = True
        descriptor = SourceDescriptor(
            provider_id="fixture",
            adapter_version="1",
            source_kinds=frozenset({SourceKind.DOCUMENT}),
            authority_class=AuthorityClass.OFFICIAL,
            point_in_time_support=True,
            allowed_usage_profiles=frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
            raw_retention=RawRetentionPolicy.PERMITTED,
            terms_url="https://example.test/terms",
            terms_reviewed_at=date(2026, 1, 1),
            independence_group="fixture",
        )
        envelope = DataEnvelope(
            value="fixture contents",
            descriptor=descriptor,
            provider_record_id="record-1",
            source="fixture://document",
            available_at=NOW,
            retrieved_at=NOW,
        )
        evidence = Evidence.from_envelope(
            id=EvidenceId("evidence_fixture"),
            run_id=run.id,
            kind=DataKind.DOCUMENT,
            summary="Fixture evidence",
            envelope=envelope,
            knowledge_cutoff_at=NOW,
            created_at=NOW,
        )
        return WorkflowCollection(
            (cast(Evidence[object], evidence),),
            (),
            {"evidence_ids": (str(evidence.id),)},
        )

    def finalize(self, run: object, synthesis: dict[str, object]) -> WorkflowFinalization:
        from fra.ports.repositories import ResearchReport

        return WorkflowFinalization(
            ResearchReport(str(synthesis["title"]), str(synthesis["summary"]))
        )


def _workflows() -> ResearchRegistry:
    registry = ResearchRegistry()
    registry.register(ResearchMandateType.GENERAL_RESEARCH, _FixtureWorkflow())
    return registry


def test_fra_owned_models_generate_closed_json_schemas() -> None:
    registry = AgentSchemaRegistry()

    schema = registry.schema_for("plan")

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["objective", "tasks", "data_requirements"]


def test_orchestrator_checkpoints_all_stages_and_restart_uses_only_durable_state() -> None:
    repository = InMemoryResearchRepository()
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    first_backend = FakeAgentBackend(results=_outputs())
    orchestrator = ResearchOrchestrator(
        repository, first_backend, clock, ids, workflows=_workflows()
    )

    completed = asyncio.run(
        orchestrator.start("What changed?", ResearchMandateType.GENERAL_RESEARCH)
    )

    assert completed.state is ResearchRunState.COMPLETED
    assert tuple(checkpoint.stage for checkpoint in completed.stage_checkpoints) == (
        "plan",
        "collect",
        "analyze",
        "verify",
        "synthesize",
    )
    assert completed.agent_metadata is not None
    assert completed.agent_metadata.prompt_versions == (
        ("plan", 2),
        ("analyze", 2),
        ("verify", 2),
        ("synthesize", 2),
    )

    second_backend = FakeAgentBackend(results=())
    resumed = asyncio.run(
        ResearchOrchestrator(repository, second_backend, clock, ids, workflows=_workflows()).resume(
            completed.id
        )
    )

    assert resumed == completed
    assert second_backend.requests == []


def test_invalid_structured_output_gets_exactly_one_repair_attempt_and_stays_visible() -> None:
    repository = InMemoryResearchRepository()
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    backend = FakeAgentBackend(
        results=(
            StructuredAgentOutput({"objective": "missing fields"}),
            StructuredAgentOutput({"objective": "still missing fields"}),
        )
    )
    orchestrator = ResearchOrchestrator(repository, backend, clock, ids, max_repairs=1)

    failed = asyncio.run(orchestrator.start("What changed?", ResearchMandateType.GENERAL_RESEARCH))

    assert failed.state is ResearchRunState.FAILED
    assert len(backend.requests) == 2
    assert backend.requests[1].instructions.startswith("Repair the previous structured output")
    assert failed.failure is not None
    assert failed.failure.kind.value == "structured_output_invalid"
    assert failed.stage_attempts == (("plan", 2),)


def test_cancelled_run_resumes_from_last_markdown_checkpoint() -> None:
    repository = InMemoryResearchRepository()
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    cancelling = FakeAgentBackend(results=_outputs(), cancel_on_request=2)
    orchestrator = ResearchOrchestrator(repository, cancelling, clock, ids, workflows=_workflows())

    cancelled = asyncio.run(
        orchestrator.start("What changed?", ResearchMandateType.GENERAL_RESEARCH)
    )
    assert cancelled.state is ResearchRunState.CANCELLED
    assert tuple(item.stage for item in cancelled.stage_checkpoints) == ("plan", "collect")

    clock.advance(timedelta(seconds=1))
    replacement = FakeAgentBackend(results=_outputs()[1:])
    resumed = asyncio.run(
        ResearchOrchestrator(repository, replacement, clock, ids, workflows=_workflows()).resume(
            cancelled.id
        )
    )

    assert resumed.state is ResearchRunState.COMPLETED
    assert len(replacement.requests) == 3
    assert replacement.requests[0].stage_type.value == "analyze"
    assert replacement.requests[0].provider_session_id == "fake-session"


def test_backend_change_starts_a_fresh_session_at_the_durable_checkpoint() -> None:
    repository = InMemoryResearchRepository()
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    first = _NamedAgent("codex_cli", results=_outputs(), cancel_on_request=2)
    cancelled = asyncio.run(
        ResearchOrchestrator(repository, first, clock, ids, workflows=_workflows()).start(
            "What changed?", ResearchMandateType.GENERAL_RESEARCH
        )
    )
    assert cancelled.state is ResearchRunState.CANCELLED

    replacement = _NamedAgent("claude_cli", results=_outputs()[1:])
    resumed = asyncio.run(
        ResearchOrchestrator(repository, replacement, clock, ids, workflows=_workflows()).resume(
            cancelled.id
        )
    )

    assert resumed.state is ResearchRunState.COMPLETED
    assert replacement.requests[0].provider_session_id is None
    assert replacement.resume_requests == ["fake-session", "fake-session"]
    assert resumed.agent_metadata is not None
    assert resumed.agent_metadata.provider_name == "claude_cli"


def test_research_gaps_are_bounded_and_remain_durable() -> None:
    repository = InMemoryResearchRepository()
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    backend = FakeAgentBackend(
        results=(
            _outputs()[0],
            _outputs()[1],
            StructuredAgentOutput(
                {
                    "passed": False,
                    "issues": (
                        {
                            "code": "missing_evidence",
                            "message": "missing evidence",
                            "severity": "high",
                            "claim_id": None,
                        },
                    ),
                }
            ),
            _outputs()[1],
            StructuredAgentOutput(
                {
                    "passed": False,
                    "issues": (
                        {
                            "code": "still_missing",
                            "message": "still missing",
                            "severity": "high",
                            "claim_id": None,
                        },
                    ),
                }
            ),
        )
    )

    failed = asyncio.run(
        ResearchOrchestrator(
            repository,
            backend,
            clock,
            ids,
            max_research_iterations=2,
            workflows=_workflows(),
        ).start("What changed?", ResearchMandateType.GENERAL_RESEARCH)
    )

    assert failed.state is ResearchRunState.FAILED
    assert len(backend.requests) == 5
    assert tuple(item.stage for item in failed.stage_checkpoints) == (
        "plan",
        "collect",
        "analyze",
        "verify",
        "collect",
        "analyze",
        "verify",
    )
    assert failed.failure is not None
    assert "bounded research iterations" in failed.failure.message


class _NamedAgent(FakeAgentBackend):
    def __init__(
        self,
        provider_name: str,
        *,
        results: tuple[StructuredAgentOutput, ...],
        cancel_on_request: int | None = None,
    ) -> None:
        super().__init__(results=results, cancel_on_request=cancel_on_request, now=NOW)
        self._provider_name = provider_name
        self.resume_requests: list[str] = []

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(True, True, True, self._provider_name)

    async def execute(
        self, request: AgentStageRequest, on_event: AgentEventHandler | None = None
    ) -> AgentStageResult:
        return replace(await super().execute(request, on_event), provider_name=self._provider_name)

    async def resume(
        self,
        provider_session_id: str,
        request: AgentStageRequest,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult:
        self.resume_requests.append(provider_session_id)
        return await super().resume(provider_session_id, request, on_event)
