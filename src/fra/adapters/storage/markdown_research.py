"""Markdown implementation of the research repository port."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar, cast

from fra.adapters.storage.serialization import decode, encode
from fra.adapters.storage.workspace import Workspace
from fra.domain.analytics import Calculation
from fra.domain.errors import (
    RepositoryConflictError,
    RepositoryCorruptError,
    RepositoryNotFoundError,
)
from fra.domain.ids import (
    CalculationId,
    ClaimId,
    EvidenceId,
    PlanId,
    ResearchRunId,
    ScenarioId,
)
from fra.domain.research import (
    Claim,
    Evidence,
    ResearchPlan,
    ResearchRun,
    ResearchScenario,
    VerificationResult,
)
from fra.domain.shared import ArtifactKind, ArtifactRef
from fra.ports.repositories import ResearchReport, ResearchRunQuery, ResearchRunSummary

_T = TypeVar("_T")


class MarkdownResearchRepository:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def create(self, run: ResearchRun) -> None:
        run_dir = self._run_directory(run)
        run_file = self._workspace.contain(run_dir / "run.md")
        with self._workspace.lock(str(run.id)):
            if run_file.exists() or self._find_run_file(run.id) is not None:
                raise RepositoryConflictError(f"research run {run.id} already exists")
            self._write_mandate(self._workspace.contain(run_dir / "mandate.md"), run)
            self._write_run(run_file, run)

    def get(self, run_id: ResearchRunId) -> ResearchRun:
        path = self._required_run_file(run_id)
        return self._read(path, "fra.research_run", ResearchRun)

    def save(self, run: ResearchRun) -> None:
        with self._workspace.lock(str(run.id)):
            path = self._required_run_file(run.id)
            existing = self._read(path, "fra.research_run", ResearchRun)
            if run.updated_at < existing.updated_at:
                raise RepositoryConflictError(f"research run {run.id} update is stale")
            self._write_run(path, run)

    def save_plan(self, run_id: ResearchRunId, plan: ResearchPlan) -> None:
        if plan.run_id != run_id:
            raise RepositoryConflictError("research plan run ID does not match its aggregate")
        with self._workspace.lock(str(run_id)):
            run_dir = self._required_run_file(run_id).parent
            path = self._workspace.contain(run_dir / "plan.md")
            if path.exists():
                existing = self._read(path, "fra.research_plan", ResearchPlan)
                if existing != plan:
                    raise RepositoryConflictError(f"research plan for {run_id} is immutable")
                return
            task_rows = "\n".join(
                f"| {task.task_id} | {task.description} | {', '.join(task.depends_on) or '—'} |"
                for task in plan.tasks
            )
            requirement_rows = "\n".join(
                f"| {item.requirement_id} | {item.data_kind.value} | "
                f"{', '.join(item.subject_ids)} | {', '.join(item.fields)} | "
                f"{item.freshness or 'unspecified'} |"
                for item in plan.data_requirements
            )
            body = (
                f"# Research Plan\n\n## Objective\n\n{plan.objective}\n\n"
                "## Tasks\n\n| ID | Task | Depends on |\n| --- | --- | --- |\n"
                f"{task_rows}\n\n## Data Requirements\n\n"
                "| ID | Kind | Subjects | Fields | Freshness |\n"
                "| --- | --- | --- | --- | --- |\n"
                f"{requirement_rows}\n"
            )
            self._write(
                path,
                "fra.research_plan",
                str(plan.id),
                plan,
                body,
                created_at=plan.created_at,
                updated_at=plan.created_at,
            )

    def get_plan(self, run_id: ResearchRunId, plan_id: PlanId | None = None) -> ResearchPlan:
        path = self._workspace.contain(self._required_run_file(run_id).parent / "plan.md")
        if not path.is_file():
            raise RepositoryNotFoundError(f"research plan for {run_id} does not exist")
        plan = self._read(path, "fra.research_plan", ResearchPlan)
        if plan.run_id != run_id or (plan_id is not None and plan.id != plan_id):
            raise RepositoryCorruptError("research plan identity does not match its aggregate")
        return plan

    def list(self, query: ResearchRunQuery | None = None) -> tuple[ResearchRunSummary, ...]:
        query = query or ResearchRunQuery()
        runs: list[tuple[ResearchRun, Path]] = []
        for candidate in self._workspace.root.glob("runs/*/*/*/run.md"):
            try:
                path = self._workspace.contain(candidate)
            except ValueError as error:
                raise RepositoryCorruptError("research run path escapes the workspace") from error
            runs.append((self._read(path, "fra.research_run", ResearchRun), path))
        runs.sort(key=lambda item: item[0].updated_at, reverse=True)
        if query.states:
            runs = [item for item in runs if item[0].state in query.states]
        if query.limit is not None:
            runs = runs[: query.limit]
        return tuple(
            ResearchRunSummary(
                id=run.id,
                question=run.mandate.question,
                state=run.state,
                created_at=run.created_at,
                updated_at=run.updated_at,
                artifact=self._artifact(ArtifactKind.RESEARCH_RUN, path),
            )
            for run, path in runs
        )

    def add_evidence(self, run_id: ResearchRunId, item: Evidence[object]) -> None:
        if item.run_id != run_id:
            raise RepositoryConflictError("evidence run ID does not match its aggregate")
        with self._workspace.lock(str(run_id)):
            run_dir = self._required_run_file(run_id).parent
            path = self._workspace.contain(
                run_dir / "evidence" / f"{self._workspace.safe_segment(item.id)}.md"
            )
            if path.exists():
                raise RepositoryConflictError(f"evidence {item.id} already exists")
            body = f"# Evidence {item.id}\n\n## Summary\n\n{item.summary}\n"
            self._write(
                path,
                "fra.evidence",
                str(item.id),
                item,
                body,
                created_at=item.created_at,
                updated_at=item.created_at,
            )

    def get_evidence(self, run_id: ResearchRunId, evidence_id: EvidenceId) -> Evidence[object]:
        run_dir = self._required_run_file(run_id).parent
        path = self._workspace.contain(
            run_dir / "evidence" / f"{self._workspace.safe_segment(evidence_id)}.md"
        )
        if not path.is_file():
            raise RepositoryNotFoundError(f"evidence {evidence_id} does not exist")
        item = self._read(path, "fra.evidence", Evidence)
        if item.run_id != run_id:
            raise RepositoryCorruptError(f"evidence {evidence_id} belongs to another run")
        return cast(Evidence[object], item)

    def add_claim(self, run_id: ResearchRunId, claim: Claim) -> None:
        if claim.run_id != run_id:
            raise RepositoryConflictError("claim run ID does not match its aggregate")
        with self._workspace.lock(str(run_id)):
            run_dir = self._required_run_file(run_id).parent
            path = self._workspace.contain(
                run_dir / "claims" / f"{self._workspace.safe_segment(claim.id)}.md"
            )
            if path.exists():
                raise RepositoryConflictError(f"claim {claim.id} already exists")
            body = _claim_body(claim)
            self._write(
                path,
                "fra.claim",
                str(claim.id),
                claim,
                body,
                created_at=claim.created_at,
                updated_at=claim.created_at,
            )

    def get_claim(self, run_id: ResearchRunId, claim_id: ClaimId) -> Claim:
        run_dir = self._required_run_file(run_id).parent
        path = self._workspace.contain(
            run_dir / "claims" / f"{self._workspace.safe_segment(claim_id)}.md"
        )
        if not path.is_file():
            raise RepositoryNotFoundError(f"claim {claim_id} does not exist")
        claim = self._read(path, "fra.claim", Claim)
        if claim.run_id != run_id:
            raise RepositoryCorruptError(f"claim {claim_id} belongs to another run")
        return claim

    def save_claim(self, run_id: ResearchRunId, claim: Claim) -> None:
        if claim.run_id != run_id:
            raise RepositoryConflictError("claim run ID does not match its aggregate")
        with self._workspace.lock(str(run_id)):
            run_dir = self._required_run_file(run_id).parent
            path = self._workspace.contain(
                run_dir / "claims" / f"{self._workspace.safe_segment(claim.id)}.md"
            )
            if not path.is_file():
                raise RepositoryNotFoundError(f"claim {claim.id} does not exist")
            existing = self._read(path, "fra.claim", Claim)
            self._write(
                path,
                "fra.claim",
                str(claim.id),
                claim,
                _claim_body(claim),
                created_at=existing.created_at,
                updated_at=claim.created_at,
            )

    def add_scenario(self, run_id: ResearchRunId, scenario: ResearchScenario) -> None:
        if scenario.run_id != run_id:
            raise RepositoryConflictError("scenario run ID does not match its aggregate")
        with self._workspace.lock(str(run_id)):
            run_dir = self._required_run_file(run_id).parent
            path = self._workspace.contain(
                run_dir / "scenarios" / f"{self._workspace.safe_segment(scenario.id)}.md"
            )
            if path.exists():
                raise RepositoryConflictError(f"scenario {scenario.id} already exists")
            evidence = "\n".join(
                f"- [{item}](../evidence/{item}.md)" for item in scenario.evidence_ids
            )
            body = (
                f"# Scenario: {scenario.title}\n\n{scenario.description}\n\n"
                f"## Evidence\n\n{evidence}\n\n## Invalidation Conditions\n\n"
                f"{_bullets(scenario.invalidation_conditions)}"
            )
            self._write(
                path,
                "fra.scenario",
                str(scenario.id),
                scenario,
                body,
                created_at=scenario.created_at,
                updated_at=scenario.created_at,
            )

    def get_scenario(self, run_id: ResearchRunId, scenario_id: ScenarioId) -> ResearchScenario:
        run_dir = self._required_run_file(run_id).parent
        path = self._workspace.contain(
            run_dir / "scenarios" / f"{self._workspace.safe_segment(scenario_id)}.md"
        )
        if not path.is_file():
            raise RepositoryNotFoundError(f"scenario {scenario_id} does not exist")
        scenario = self._read(path, "fra.scenario", ResearchScenario)
        if scenario.run_id != run_id:
            raise RepositoryCorruptError(f"scenario {scenario_id} belongs to another run")
        return scenario

    def save_verification(self, run_id: ResearchRunId, verification: VerificationResult) -> None:
        if verification.run_id != run_id:
            raise RepositoryConflictError("verification run ID does not match its aggregate")
        with self._workspace.lock(str(run_id)):
            run_dir = self._required_run_file(run_id).parent
            path = self._workspace.contain(run_dir / "verification.md")
            issue_rows = (
                "\n".join(
                    f"| {item.severity.value} | {item.code} | {item.claim_id or '—'} | "
                    f"{item.message} |"
                    for item in verification.issues
                )
                or "| — | none | — | No verification issues |"
            )
            body = (
                "# Research Verification\n\n"
                f"- Passed: {str(verification.passed).lower()}\n"
                f"- Deterministic checks passed: "
                f"{str(verification.deterministic_passed).lower()}\n"
                f"- Agent critique passed: {str(verification.agent_passed).lower()}\n\n"
                "## Issues\n\n| Severity | Code | Claim | Detail |\n"
                "| --- | --- | --- | --- |\n"
                f"{issue_rows}\n"
            )
            self._write(
                path,
                "fra.verification",
                str(verification.id),
                verification,
                body,
                created_at=verification.checked_at,
                updated_at=verification.checked_at,
            )

    def get_verification(self, run_id: ResearchRunId) -> VerificationResult:
        path = self._workspace.contain(self._required_run_file(run_id).parent / "verification.md")
        if not path.is_file():
            raise RepositoryNotFoundError(f"verification for {run_id} does not exist")
        verification = self._read(path, "fra.verification", VerificationResult)
        if verification.run_id != run_id:
            raise RepositoryCorruptError("verification belongs to another run")
        return verification

    def add_calculation(self, run_id: ResearchRunId, calculation: Calculation) -> None:
        if calculation.run_id != run_id:
            raise RepositoryConflictError("calculation run ID does not match its aggregate")
        with self._workspace.lock(str(run_id)):
            run_dir = self._required_run_file(run_id).parent
            path = self._workspace.contain(
                run_dir / "calculations" / f"{self._workspace.safe_segment(calculation.id)}.md"
            )
            if path.exists():
                raise RepositoryConflictError(f"calculation {calculation.id} already exists")
            result_rows = "\n".join(f"| {name} | {value} |" for name, value in calculation.results)
            body = (
                f"# Calculation {calculation.id}\n\n## Formula\n\n"
                f"{calculation.name} v{calculation.formula_version}\n\n"
                "## Results\n\n| Metric | Value |\n| --- | ---: |\n"
                f"{result_rows}\n"
            )
            self._write(
                path,
                "fra.calculation",
                str(calculation.id),
                calculation,
                body,
                created_at=calculation.created_at,
                updated_at=calculation.created_at,
            )

    def get_calculation(self, run_id: ResearchRunId, calculation_id: CalculationId) -> Calculation:
        run_dir = self._required_run_file(run_id).parent
        path = self._workspace.contain(
            run_dir / "calculations" / f"{self._workspace.safe_segment(calculation_id)}.md"
        )
        if not path.is_file():
            raise RepositoryNotFoundError(f"calculation {calculation_id} does not exist")
        calculation = self._read(path, "fra.calculation", Calculation)
        if calculation.run_id != run_id:
            raise RepositoryCorruptError(f"calculation {calculation_id} belongs to another run")
        return calculation

    def save_report(self, run_id: ResearchRunId, report: ResearchReport) -> None:
        with self._workspace.lock(str(run_id)):
            run_dir = self._required_run_file(run_id).parent
            path = self._workspace.contain(run_dir / "report.md")
            if path.exists():
                raise RepositoryConflictError(f"report for {run_id} already exists")
            stored = ResearchReport(
                title=report.title,
                body=report.body,
                artifact=self._artifact(ArtifactKind.REPORT, path),
            )
            run = self.get(run_id)
            self._write(
                path,
                "fra.research_report",
                str(run_id),
                stored,
                report.body,
                created_at=run.updated_at,
                updated_at=run.updated_at,
            )

    def save_limitation(self, run_id: ResearchRunId, report: ResearchReport) -> None:
        with self._workspace.lock(str(run_id)):
            run_dir = self._required_run_file(run_id).parent
            path = self._workspace.contain(run_dir / "limitation.md")
            stored = ResearchReport(
                title=report.title,
                body=report.body,
                artifact=self._artifact(ArtifactKind.REPORT, path),
            )
            run = self.get(run_id)
            self._write(
                path,
                "fra.research_limitation",
                str(run_id),
                stored,
                report.body,
                created_at=run.updated_at,
                updated_at=run.updated_at,
            )

    def _run_directory(self, run: ResearchRun) -> Path:
        segment = self._workspace.safe_segment(run.id)
        return self._workspace.path(
            f"runs/{run.created_at.year:04d}/{run.created_at.month:02d}/{segment}"
        )

    def _find_run_file(self, run_id: ResearchRunId) -> Path | None:
        segment = self._workspace.safe_segment(run_id)
        try:
            matches = tuple(
                self._workspace.contain(path)
                for path in self._workspace.root.glob(f"runs/*/*/{segment}/run.md")
            )
        except ValueError as error:
            raise RepositoryCorruptError(f"research run {run_id} escapes the workspace") from error
        if len(matches) > 1:
            raise RepositoryCorruptError(f"research run {run_id} exists in multiple locations")
        return matches[0] if matches else None

    def _required_run_file(self, run_id: ResearchRunId) -> Path:
        path = self._find_run_file(run_id)
        if path is None:
            raise RepositoryNotFoundError(f"research run {run_id} does not exist")
        return path

    def _write_run(self, path: Path, run: ResearchRun) -> None:
        body = (
            f"# Research Run: {run.id}\n\n## Question\n\n{run.mandate.question}\n\n"
            f"## Status\n\n{run.state.value}\n\n## Artifact Links\n\n"
            "- [Mandate](mandate.md)\n- [Plan](plan.md)\n"
            "- [Verification](verification.md)\n- [Final report](report.md)\n"
        )
        self._write(
            path,
            "fra.research_run",
            str(run.id),
            run,
            body,
            created_at=run.created_at,
            updated_at=run.updated_at,
            extra_metadata=_run_metadata(run),
        )

    def _write_mandate(self, path: Path, run: ResearchRun) -> None:
        mandate = run.mandate
        body = (
            f"# Research Mandate: {mandate.id}\n\n## Question\n\n{mandate.question}\n\n"
            "## User Facts\n\n"
            + _bullets(mandate.user_facts)
            + "\n## Assumptions\n\n"
            + _bullets(mandate.assumptions)
            + "\n## Unresolved Questions\n\n"
            + _bullets(mandate.unresolved_questions)
            + "\n## Exclusions\n\n"
            + _bullets(mandate.exclusions)
        )
        self._write(
            path,
            "fra.research_mandate",
            str(mandate.id),
            mandate,
            body,
            created_at=mandate.created_at,
            updated_at=mandate.created_at,
        )

    def _write(
        self,
        path: Path,
        schema: str,
        item_id: str,
        item: object,
        body: str,
        *,
        created_at: datetime,
        updated_at: datetime,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata: dict[str, Any] = {
            "schema": schema,
            "schema_version": 1,
            "id": item_id,
            "created_at": _timestamp(created_at),
            "updated_at": _timestamp(updated_at),
            "payload": encode(item),
        }
        metadata.update(extra_metadata or {})
        rendered = self._workspace.codec.render(metadata, body)
        self._workspace.writer.write_text(path, rendered)

    def _read(self, path: Path, schema: str, expected: type[_T]) -> _T:
        try:
            metadata, _body = self._workspace.codec.parse(
                path.read_text(encoding="utf-8"), expected_schema=schema
            )
            value = decode(metadata["payload"])
        except RepositoryCorruptError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise RepositoryCorruptError(f"could not reconstruct {path.name}: {error}") from error
        if not isinstance(value, expected):
            raise RepositoryCorruptError(f"{path.name} does not contain {expected.__name__}")
        return value

    def _artifact(self, kind: ArtifactKind, path: Path) -> ArtifactRef:
        return ArtifactRef(kind=kind, location=path.relative_to(self._workspace.root).as_posix())


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items) + "\n" if items else "- None\n"


def _claim_body(claim: Claim) -> str:
    support = (
        *(f"- [{item}](../evidence/{item}.md)" for item in claim.evidence_ids),
        *(f"- [{item}](../calculations/{item}.md)" for item in claim.calculation_ids),
    )
    return (
        f"# Claim {claim.id}\n\n{claim.statement}\n\n"
        f"- Status: {claim.status.value}\n"
        f"- Materiality: {claim.materiality.value}\n"
        f"- Confidence: {claim.confidence.value}\n\n"
        "## Support\n\n"
        + ("\n".join(support) if support else "- None")
        + "\n\n## Limitations\n\n"
        + _bullets(claim.limitations)
    )


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _run_metadata(run: ResearchRun) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "workflow": run.mandate.kind.value,
        "status": run.state.value,
        "completed_stages": [item.stage for item in run.stage_checkpoints],
        "attempts": dict(run.stage_attempts),
    }
    if run.agent_metadata is not None:
        agent = run.agent_metadata
        metadata.update(
            {
                "agent_adapter": agent.provider_name,
                "agent_adapter_version": agent.adapter_version,
                "agent_cli_version": agent.cli_version,
                "agent_model": agent.model,
                "agent_session_id": agent.provider_session_id,
                "prompt_versions": dict(agent.prompt_versions),
                "output_schema_versions": dict(agent.output_schema_versions),
            }
        )
    return metadata
