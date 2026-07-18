"""Durable research workflow orchestration independent of agent providers."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from fra.application.agent_schemas import AgentSchemaRegistry
from fra.application.prompt_templates import PromptTemplateRegistry
from fra.application.research_workflows import ResearchRegistry
from fra.application.results import failure_from_error
from fra.application.verification_service import VerificationService
from fra.domain.errors import FRAExpectedError, StructuredOutputInvalidError
from fra.domain.ids import CalculationId, ClaimId, EvidenceId, ResearchRunId
from fra.domain.research import (
    AgentRunMetadata,
    Claim,
    ClaimConfidence,
    ClaimMateriality,
    ClaimStatus,
    ResearchDataRequirement,
    ResearchMandate,
    ResearchMandateType,
    ResearchPlan,
    ResearchPlanTask,
    ResearchRun,
    ResearchRunState,
    ResearchScenario,
    ResearchStageCheckpoint,
    VerificationIssue,
    VerificationSeverity,
)
from fra.domain.shared import Failure, FailureKind
from fra.domain.sources import DataKind
from fra.ports.agent_backend import (
    AgentBackend,
    AgentResultStatus,
    AgentStageRequest,
    AgentStageType,
)
from fra.ports.clock import Clock
from fra.ports.ids import IdGenerator
from fra.ports.repositories import (
    ExposureGraphRepository,
    ForecastRepository,
    PortfolioRepository,
    ProfileRepository,
    ResearchReport,
    ResearchRepository,
    SignalRepository,
)

_AGENT_STAGES = ("plan", "analyze", "verify", "synthesize")
_STATE_FOR_STAGE = {
    "plan": ResearchRunState.PLANNING,
    "collect": ResearchRunState.COLLECTING_EVIDENCE,
    "analyze": ResearchRunState.ANALYZING,
    "verify": ResearchRunState.VERIFYING,
    "synthesize": ResearchRunState.SYNTHESIZING,
}
_TYPE_FOR_STAGE = {
    "plan": AgentStageType.PLAN,
    "analyze": AgentStageType.ANALYZE,
    "verify": AgentStageType.VERIFY,
    "synthesize": AgentStageType.SYNTHESIZE,
}


class ResearchOrchestrator:
    """Execute and checkpoint the shared five-stage research skeleton."""

    def __init__(
        self,
        repository: ResearchRepository,
        agent_backend: AgentBackend,
        clock: Clock,
        ids: IdGenerator,
        *,
        schemas: AgentSchemaRegistry | None = None,
        prompts: PromptTemplateRegistry | None = None,
        working_directory: Path | None = None,
        timeout_seconds: int = 900,
        max_repairs: int = 1,
        max_research_iterations: int = 2,
        workflows: ResearchRegistry | None = None,
        signal_repository: SignalRepository | None = None,
        forecast_repository: ForecastRepository | None = None,
        exposure_graph_repository: ExposureGraphRepository | None = None,
        profile_repository: ProfileRepository | None = None,
        portfolio_repository: PortfolioRepository | None = None,
        verification_service: VerificationService | None = None,
    ) -> None:
        self._repository = repository
        self._agent = agent_backend
        self._clock = clock
        self._ids = ids
        self._schemas = schemas or AgentSchemaRegistry()
        self._prompts = prompts or PromptTemplateRegistry()
        self._working_directory = working_directory or Path.cwd()
        self._timeout_seconds = timeout_seconds
        if max_repairs < 0 or max_research_iterations <= 0:
            raise ValueError("orchestration bounds must be non-negative and non-zero")
        self._max_repairs = max_repairs
        self._max_research_iterations = max_research_iterations
        self._workflows = workflows or ResearchRegistry()
        self._signals = signal_repository
        self._forecasts = forecast_repository
        self._graphs = exposure_graph_repository
        self._profiles = profile_repository
        self._portfolios = portfolio_repository
        self._verification = verification_service or VerificationService(repository, clock, ids)

    async def start(
        self,
        question: str,
        mandate_type: ResearchMandateType,
        *,
        user_facts: tuple[str, ...] = (),
        assumptions: tuple[str, ...] = (),
        unresolved_questions: tuple[str, ...] = (),
        exclusions: tuple[str, ...] = (),
        horizon: str | None = None,
        parameters: tuple[tuple[str, str], ...] = (),
    ) -> ResearchRun:
        now = self._clock.now()
        mandate = ResearchMandate(
            id=self._ids.mandate_id(),
            kind=mandate_type,
            question=question,
            created_at=now,
            user_facts=user_facts,
            assumptions=assumptions,
            unresolved_questions=unresolved_questions,
            exclusions=exclusions,
            horizon=horizon,
            parameters=parameters,
        )
        run = ResearchRun.create(self._ids.research_run_id(), mandate, now)
        self._repository.create(run)
        workflow = self._workflows.get(mandate_type)
        if workflow is not None and (missing := workflow.missing_inputs(mandate)):
            failure = Failure(
                FailureKind.NEEDS_USER_INPUT,
                f"Missing required {mandate_type.value} research inputs: " + ", ".join(missing),
            )
            run = run.transition(
                ResearchRunState.NEEDS_USER_INPUT,
                self._clock.now(),
                failure=failure,
            )
            self._repository.save(run)
            self._save_limitation(run, failure)
            return run
        if not self._agent.capabilities().structured_output:
            failure = Failure(
                FailureKind.CAPABILITY_UNSUPPORTED,
                "selected agent does not support schema-constrained output",
                provider_id=self._agent.capabilities().provider_name,
            )
            run = run.transition(ResearchRunState.FAILED, self._clock.now(), failure=failure)
            self._repository.save(run)
            return run
        return await self._continue(run)

    async def resume(self, run_id: ResearchRunId) -> ResearchRun:
        run = self._repository.get(run_id)
        if run.state is ResearchRunState.COMPLETED:
            return run
        next_stage = self._next_stage(run)
        if next_stage is None:
            return run
        target = _STATE_FOR_STAGE[next_stage]
        if run.state in {
            ResearchRunState.FAILED,
            ResearchRunState.CANCELLED,
            ResearchRunState.NEEDS_USER_INPUT,
        }:
            run = run.resume(target, self._clock.now())
            self._repository.save(run)
        return await self._continue(run)

    async def _continue(self, run: ResearchRun) -> ResearchRun:
        workflow = self._workflows.get(run.mandate.kind)
        while (stage := self._next_stage(run)) is not None:
            target = _STATE_FOR_STAGE[stage]
            if stage == "collect" and run.state is ResearchRunState.VERIFYING:
                run = run.transition(ResearchRunState.NEEDS_RESEARCH, self._clock.now())
                self._repository.save(run)
            if run.state is not target:
                run = run.transition(target, self._clock.now())
                self._repository.save(run)

            if stage == "collect":
                if workflow is None:
                    return self._fail_run(
                        run,
                        Failure(
                            FailureKind.CAPABILITY_UNAVAILABLE,
                            f"no evidence workflow is registered for {run.mandate.kind.value}",
                        ),
                    )
                try:
                    collection = await workflow.collect(run, self._repository.get_plan(run.id))
                except FRAExpectedError as error:
                    return self._fail_run(run, failure_from_error(error))
                for item in collection.evidence:
                    self._repository.add_evidence(run.id, item)
                for calculation in collection.calculations:
                    self._repository.add_calculation(run.id, calculation)
                run = self._checkpoint(run, stage, collection.durable_result)
                continue

            run, output = await self._execute_agent_stage(run, stage)
            if output is None:
                return run

            try:
                if stage == "plan":
                    plan = self._plan(run, output)
                    self._repository.save_plan(run.id, plan)
                    output = {**output, "plan_id": str(plan.id)}
                elif stage == "analyze":
                    output = self._persist_analysis(run, output)
                elif stage == "verify":
                    output = self._verify(run, output)
            except FRAExpectedError as error:
                return self._fail_run(run, failure_from_error(error))

            if stage == "synthesize":
                if workflow is not None:
                    try:
                        finalization = workflow.finalize(run, output)
                    except FRAExpectedError as error:
                        return self._fail_run(run, failure_from_error(error))
                    if finalization.signal is not None:
                        if self._signals is None:
                            failure = Failure(
                                FailureKind.CAPABILITY_UNAVAILABLE,
                                "workflow produced a signal without a signal repository",
                            )
                            return self._fail_run(run, failure)
                        self._signals.save(finalization.signal)
                    if finalization.forecasts:
                        if self._forecasts is None:
                            return self._fail_run(
                                run,
                                Failure(
                                    FailureKind.CAPABILITY_UNAVAILABLE,
                                    "workflow produced forecasts without a forecast repository",
                                ),
                            )
                        for forecast in finalization.forecasts:
                            self._forecasts.save(forecast)
                    if finalization.exposure_graphs:
                        if self._graphs is None:
                            return self._fail_run(
                                run,
                                Failure(
                                    FailureKind.CAPABILITY_UNAVAILABLE,
                                    "workflow produced exposure graphs without a graph repository",
                                ),
                            )
                        for graph in finalization.exposure_graphs:
                            self._graphs.save(graph)
                    if finalization.profiles:
                        if self._profiles is None:
                            return self._fail_run(
                                run,
                                Failure(
                                    FailureKind.CAPABILITY_UNAVAILABLE,
                                    "workflow produced profiles without a profile repository",
                                ),
                            )
                        for profile in finalization.profiles:
                            self._profiles.save(profile)
                    if finalization.portfolios:
                        if self._portfolios is None:
                            return self._fail_run(
                                run,
                                Failure(
                                    FailureKind.CAPABILITY_UNAVAILABLE,
                                    "workflow produced portfolios without a portfolio repository",
                                ),
                            )
                        for portfolio in finalization.portfolios:
                            self._portfolios.save(portfolio)
                    self._repository.save_report(run.id, finalization.report)
                else:
                    limitations = output.get("limitations", [])
                    if not isinstance(limitations, list):
                        raise StructuredOutputInvalidError("synthesize limitations must be a list")
                    body = f"# {output['title']}\n\n{output['summary']}\n\n## Limitations\n\n"
                    body += "\n".join(f"- {item}" for item in limitations) or "- None"
                    self._repository.save_report(
                        run.id, ResearchReport(title=str(output["title"]), body=body)
                    )
            run = self._checkpoint(run, stage, output)
            if stage == "verify" and not bool(output["passed"]):
                verification_iterations = sum(
                    item.stage == "verify" for item in run.stage_checkpoints
                )
                if verification_iterations >= self._max_research_iterations:
                    failure = Failure(
                        FailureKind.INCOMPLETE,
                        "verification gaps remain after the bounded research iterations",
                    )
                    return self._fail_run(run, failure)

        if run.state is ResearchRunState.SYNTHESIZING:
            run = run.transition(ResearchRunState.COMPLETED, self._clock.now())
            self._repository.save(run)
        return run

    def _plan(self, run: ResearchRun, output: dict[str, object]) -> ResearchPlan:
        raw_tasks = output.get("tasks")
        raw_requirements = output.get("data_requirements")
        if not isinstance(raw_tasks, list) or not isinstance(raw_requirements, list):
            raise StructuredOutputInvalidError("plan tasks and data requirements must be lists")
        tasks = tuple(
            ResearchPlanTask(
                str(item["task_id"]),
                str(item["description"]),
                tuple(str(value) for value in item.get("depends_on", [])),
            )
            for item in raw_tasks
            if isinstance(item, dict)
        )
        requirements = tuple(
            ResearchDataRequirement(
                str(item["requirement_id"]),
                str(item["description"]),
                _data_kind(item["data_kind"]),
                tuple(str(value) for value in item["subject_ids"]),
                tuple(str(value) for value in item["fields"]),
                _optional_string(item.get("geography_or_market")),
                _optional_string(item.get("resolution")),
                _optional_string(item.get("freshness")),
            )
            for item in raw_requirements
            if isinstance(item, dict)
        )
        if len(tasks) != len(raw_tasks) or len(requirements) != len(raw_requirements):
            raise StructuredOutputInvalidError("plan contains an invalid task or data requirement")
        return ResearchPlan(
            self._ids.plan_id(),
            run.id,
            str(output["objective"]),
            tasks,
            requirements,
            self._clock.now(),
        )

    def _persist_analysis(self, run: ResearchRun, output: dict[str, object]) -> dict[str, object]:
        raw_claims = output.get("claims")
        raw_scenarios = output.get("scenarios")
        if not isinstance(raw_claims, list) or not isinstance(raw_scenarios, list):
            raise StructuredOutputInvalidError("analysis claims and scenarios must be lists")
        claim_ids: list[str] = []
        for value in raw_claims:
            if not isinstance(value, dict):
                raise StructuredOutputInvalidError("analysis claim must be an object")
            claim = Claim(
                self._ids.claim_id(),
                run.id,
                str(value["statement"]),
                ClaimMateriality(str(value["materiality"])),
                ClaimStatus.PROPOSED,
                ClaimConfidence(str(value["confidence"])),
                tuple(EvidenceId(str(item)) for item in value["evidence_ids"]),
                self._clock.now(),
                tuple(str(item) for item in value.get("limitations", [])),
                tuple(CalculationId(str(item)) for item in value["calculation_ids"]),
            )
            self._repository.add_claim(run.id, claim)
            claim_ids.append(str(claim.id))
        scenario_ids: list[str] = []
        for value in raw_scenarios:
            if not isinstance(value, dict):
                raise StructuredOutputInvalidError("analysis scenario must be an object")
            scenario = ResearchScenario(
                self._ids.scenario_id(),
                run.id,
                str(value["title"]),
                str(value["description"]),
                tuple(EvidenceId(str(item)) for item in value["evidence_ids"]),
                tuple(str(item) for item in value["invalidation_conditions"]),
                self._clock.now(),
            )
            self._repository.add_scenario(run.id, scenario)
            scenario_ids.append(str(scenario.id))
        return {**output, "claim_ids": claim_ids, "scenario_ids": scenario_ids}

    def _verify(self, run: ResearchRun, output: dict[str, object]) -> dict[str, object]:
        analysis = next(
            (item for item in reversed(run.stage_checkpoints) if item.stage == "analyze"),
            None,
        )
        if analysis is None:
            raise StructuredOutputInvalidError(
                "verification requires a durable analysis checkpoint"
            )
        analysis_output = json.loads(analysis.result_json)
        raw_claim_ids = analysis_output.get("claim_ids")
        raw_issues = output.get("issues")
        if not isinstance(raw_claim_ids, list) or not isinstance(raw_issues, list):
            raise StructuredOutputInvalidError("verification contract is incomplete")
        claims = tuple(
            self._repository.get_claim(run.id, _claim_id(value)) for value in raw_claim_ids
        )
        agent_issues = tuple(
            VerificationIssue(
                str(item["code"]),
                str(item["message"]),
                VerificationSeverity(str(item["severity"])),
                _claim_id(item["claim_id"]) if item.get("claim_id") is not None else None,
            )
            for item in raw_issues
            if isinstance(item, dict)
        )
        if len(agent_issues) != len(raw_issues):
            raise StructuredOutputInvalidError("verification issue must be an object")
        result = self._verification.verify(
            run,
            claims,
            agent_passed=bool(output["passed"]),
            agent_issues=agent_issues,
        )
        return {
            "passed": result.passed,
            "deterministic_passed": result.deterministic_passed,
            "agent_passed": result.agent_passed,
            "verification_id": str(result.id),
            "issues": [
                {
                    "code": item.code,
                    "message": item.message,
                    "severity": item.severity.value,
                    "claim_id": str(item.claim_id) if item.claim_id is not None else None,
                }
                for item in result.issues
            ],
        }

    async def _execute_agent_stage(
        self, run: ResearchRun, stage: str
    ) -> tuple[ResearchRun, dict[str, object] | None]:
        durable = self._durable_results(run)
        validation_error: str | None = None
        for repair_number in range(self._max_repairs + 1):
            run = self._record_attempt(run, stage)
            same_backend = (
                run.agent_metadata is not None
                and run.agent_metadata.provider_name == self._agent.capabilities().provider_name
            )
            instructions = self._prompts.render(
                stage,
                question=run.mandate.question,
                durable_results=durable,
                repair_error=validation_error if repair_number else None,
                workflow=run.mandate.kind.value,
            )
            request = AgentStageRequest(
                run_id=run.id,
                stage_id=self._ids.stage_id(),
                stage_type=_TYPE_FOR_STAGE[stage],
                instructions=instructions,
                evidence_ids=(),
                timeout_seconds=self._timeout_seconds,
                output_schema=self._schemas.schema_for(stage),
                provider_session_id=(
                    run.agent_metadata.provider_session_id
                    if run.agent_metadata and same_backend
                    else None
                ),
                working_directory=self._working_directory,
            )
            if (
                request.provider_session_id
                and same_backend
                and self._agent.capabilities().session_resume
            ):
                result = await self._agent.resume(request.provider_session_id, request)
            else:
                result = await self._agent.execute(request)
            run = self._record_agent_metadata(run, stage, result)

            if result.status is AgentResultStatus.CANCELLED:
                run = run.transition(ResearchRunState.CANCELLED, self._clock.now())
                self._repository.save(run)
                self._save_limitation(
                    run,
                    Failure(FailureKind.CANCELLED, f"agent {stage} stage was cancelled"),
                )
                return run, None
            if (
                result.failure is not None
                and result.failure.kind is FailureKind.STRUCTURED_OUTPUT_INVALID
                and repair_number < self._max_repairs
            ):
                validation_error = result.failure.message
                continue
            if result.status is not AgentResultStatus.COMPLETED or result.output is None:
                failure = result.failure or Failure(
                    FailureKind.INCOMPLETE,
                    f"agent {stage} stage did not complete",
                    retryable=True,
                    provider_id=result.provider_name,
                )
                return self._fail_run(run, failure), None
            try:
                return run, self._schemas.validate(stage, result.output.values)
            except StructuredOutputInvalidError as error:
                validation_error = str(error)

        assert validation_error is not None
        failure = failure_from_error(StructuredOutputInvalidError(validation_error))
        return self._fail_run(run, failure), None

    def _fail_run(self, run: ResearchRun, failure: Failure) -> ResearchRun:
        run = run.transition(ResearchRunState.FAILED, self._clock.now(), failure=failure)
        self._repository.save(run)
        self._save_limitation(run, failure)
        return run

    def _save_limitation(self, run: ResearchRun, failure: Failure) -> None:
        body = (
            f"# Research Limitation\n\nRun `{run.id}` did not complete.\n\n"
            f"## Typed status\n\n- Kind: {failure.kind.value}\n"
            f"- Detail: {failure.message}\n"
        )
        self._repository.save_limitation(
            run.id,
            ResearchReport(title="Research Limitation", body=body),
        )

    def _checkpoint(self, run: ResearchRun, stage: str, output: dict[str, object]) -> ResearchRun:
        checkpoint = ResearchStageCheckpoint(
            stage=stage,
            stage_id=str(self._ids.stage_id()),
            completed_at=self._clock.now(),
            result_json=json.dumps(output, sort_keys=True, separators=(",", ":")),
        )
        run = replace(
            run,
            updated_at=self._clock.now(),
            stage_checkpoints=(*run.stage_checkpoints, checkpoint),
        )
        self._repository.save(run)
        return run

    def _record_attempt(self, run: ResearchRun, stage: str) -> ResearchRun:
        attempts = dict(run.stage_attempts)
        attempts[stage] = attempts.get(stage, 0) + 1
        run = replace(
            run,
            updated_at=self._clock.now(),
            stage_attempts=tuple(
                (name, attempts[name]) for name in _AGENT_STAGES if name in attempts
            ),
        )
        self._repository.save(run)
        return run

    def _record_agent_metadata(self, run: ResearchRun, stage: str, result: object) -> ResearchRun:
        from fra.ports.agent_backend import AgentStageResult

        assert isinstance(result, AgentStageResult)
        prior = run.agent_metadata
        prompt_versions = dict(prior.prompt_versions) if prior else {}
        schema_versions = dict(prior.output_schema_versions) if prior else {}
        prompt_versions[stage] = self._prompts.VERSION
        schema_versions[stage] = self._schemas.VERSION
        metadata = AgentRunMetadata(
            provider_name=result.provider_name,
            adapter_version=str(getattr(self._agent, "adapter_version", "1")),
            cli_version=result.cli_version or (prior.cli_version if prior else None),
            model=result.model or (prior.model if prior else None),
            provider_session_id=result.provider_session_id
            or (prior.provider_session_id if prior else None),
            prompt_versions=tuple(
                (name, prompt_versions[name]) for name in _AGENT_STAGES if name in prompt_versions
            ),
            output_schema_versions=tuple(
                (name, schema_versions[name]) for name in _AGENT_STAGES if name in schema_versions
            ),
        )
        run = replace(run, updated_at=self._clock.now(), agent_metadata=metadata)
        self._repository.save(run)
        return run

    @staticmethod
    def _durable_results(run: ResearchRun) -> dict[str, object]:
        return {item.stage: json.loads(item.result_json) for item in run.stage_checkpoints}

    @staticmethod
    def _next_stage(run: ResearchRun) -> str | None:
        if not run.stage_checkpoints:
            return "plan"
        latest = run.stage_checkpoints[-1]
        if latest.stage == "plan":
            return "collect"
        if latest.stage == "collect":
            return "analyze"
        if latest.stage == "analyze":
            return "verify"
        if latest.stage == "verify":
            output = json.loads(latest.result_json)
            return "synthesize" if output.get("passed") is True else "collect"
        if latest.stage == "synthesize":
            return None
        raise ValueError(f"unknown persisted research stage: {latest.stage}")


def _data_kind(value: object) -> DataKind:
    try:
        return DataKind(str(value))
    except ValueError as error:
        raise StructuredOutputInvalidError(f"unknown planned data kind: {value}") from error


def _claim_id(value: object) -> ClaimId:
    return ClaimId(str(value))


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)
