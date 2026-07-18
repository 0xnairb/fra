from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from fra.adapters.agents.codex_cli import CodexCliAgentAdapter
from fra.adapters.fakes.agent import FakeAgentBackend
from fra.adapters.storage.markdown_research import MarkdownResearchRepository
from fra.adapters.storage.workspace import Workspace
from fra.adapters.system.deterministic import SequenceIdGenerator
from fra.adapters.system.runtime import SystemClock
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
from fra.ports.agent_backend import StructuredAgentOutput
from fra.ports.repositories import ResearchReport

FIXTURE = Path(__file__).parents[2] / "fixtures" / "agent_backends" / "fake_codex.py"


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
                        "description": "collect fixture evidence",
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
                        "description": "The fixture remains available.",
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
    def missing_inputs(self, mandate: object) -> tuple[str, ...]:
        return ()

    async def collect(self, run: ResearchRun, plan: ResearchPlan) -> WorkflowCollection:
        assert plan.data_requirements[0].data_kind is DataKind.DOCUMENT
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
            available_at=run.created_at,
            retrieved_at=run.created_at,
        )
        evidence = Evidence.from_envelope(
            id=EvidenceId("evidence_fixture"),
            run_id=run.id,
            kind=DataKind.DOCUMENT,
            summary="Fixture evidence",
            envelope=envelope,
            knowledge_cutoff_at=run.created_at,
            created_at=run.created_at,
        )
        return WorkflowCollection(
            (cast(Evidence[object], evidence),),
            (),
            {"evidence_ids": (str(evidence.id),)},
        )

    def finalize(self, run: ResearchRun, synthesis: dict[str, object]) -> WorkflowFinalization:
        return WorkflowFinalization(
            ResearchReport(str(synthesis["title"]), str(synthesis["summary"]))
        )


def _workflows() -> ResearchRegistry:
    registry = ResearchRegistry()
    registry.register(ResearchMandateType.GENERAL_RESEARCH, _FixtureWorkflow())
    return registry


def test_process_cancellation_persists_markdown_and_restart_resumes(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    repository = MarkdownResearchRepository(workspace)
    ids = SequenceIdGenerator()
    started_marker = tmp_path / "analyze-started"
    cancelling_backend = CodexCliAgentAdapter(
        binary=str(FIXTURE),
        environment={
            "FAKE_CODEX_MODE": "cancel:fra.agent.analyze.v2",
            "FAKE_CODEX_STARTED_MARKER": str(started_marker),
        },
    )
    orchestrator = ResearchOrchestrator(
        repository,
        cancelling_backend,
        SystemClock(),
        ids,
        working_directory=workspace.root,
        timeout_seconds=10,
        workflows=_workflows(),
    )

    async def cancel_during_analyze() -> ResearchRun:
        task = asyncio.create_task(
            orchestrator.start("What changed?", ResearchMandateType.GENERAL_RESEARCH)
        )
        for _ in range(200):
            if started_marker.is_file():
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("analyze stage did not start before cancellation deadline")
        task.cancel()
        return await task

    cancelled = asyncio.run(cancel_during_analyze())
    assert cancelled.state is ResearchRunState.CANCELLED
    persisted = MarkdownResearchRepository(Workspace(workspace.root)).get(cancelled.id)
    assert tuple(item.stage for item in persisted.stage_checkpoints) == ("plan", "collect")

    replacement = CodexCliAgentAdapter(
        binary=str(FIXTURE), environment={"FAKE_CODEX_MODE": "success"}
    )
    resumed = asyncio.run(
        ResearchOrchestrator(
            MarkdownResearchRepository(Workspace(workspace.root)),
            replacement,
            SystemClock(),
            SequenceIdGenerator(start=100),
            working_directory=workspace.root,
            workflows=_workflows(),
        ).resume(persisted.id)
    )

    assert resumed.state is ResearchRunState.COMPLETED
    assert (next(workspace.root.glob("runs/*/*/*")) / "report.md").is_file()


@pytest.mark.parametrize(
    ("cancel_on_request", "completed_stages"),
    (
        (1, ()),
        (2, ("plan", "collect")),
        (3, ("plan", "collect", "analyze")),
        (4, ("plan", "collect", "analyze", "verify")),
    ),
)
def test_restart_after_every_agent_stage_uses_only_markdown(
    tmp_path: Path,
    cancel_on_request: int,
    completed_stages: tuple[str, ...],
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    repository = MarkdownResearchRepository(workspace)
    ids = SequenceIdGenerator()
    cancelled = asyncio.run(
        ResearchOrchestrator(
            repository,
            FakeAgentBackend(results=_outputs(), cancel_on_request=cancel_on_request),
            SystemClock(),
            ids,
            working_directory=workspace.root,
            workflows=_workflows(),
        ).start("What changed?", ResearchMandateType.GENERAL_RESEARCH)
    )

    assert cancelled.state is ResearchRunState.CANCELLED
    assert tuple(item.stage for item in cancelled.stage_checkpoints) == completed_stages

    reconstructed = MarkdownResearchRepository(Workspace(workspace.root))
    replacement = FakeAgentBackend(results=_outputs()[cancel_on_request - 1 :])
    resumed = asyncio.run(
        ResearchOrchestrator(
            reconstructed,
            replacement,
            SystemClock(),
            SequenceIdGenerator(start=100),
            working_directory=workspace.root,
            workflows=_workflows(),
        ).resume(cancelled.id)
    )

    assert resumed.state is ResearchRunState.COMPLETED
