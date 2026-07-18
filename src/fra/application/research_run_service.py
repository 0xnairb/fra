"""Small WP1 use case for creating and transitioning research runs."""

from fra.application.results import ApplicationResult, failure_from_error
from fra.domain.errors import (
    DomainValidationError,
    InvalidStateTransitionError,
    RepositoryConflictError,
    RepositoryNotFoundError,
)
from fra.domain.ids import ResearchRunId
from fra.domain.research import (
    ResearchMandate,
    ResearchMandateType,
    ResearchRun,
    ResearchRunState,
)
from fra.ports.clock import Clock
from fra.ports.ids import IdGenerator
from fra.ports.repositories import ResearchRepository

_SERVICE_ERRORS = (
    DomainValidationError,
    InvalidStateTransitionError,
    RepositoryConflictError,
    RepositoryNotFoundError,
)


class ResearchRunService:
    def __init__(
        self,
        repository: ResearchRepository,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._ids = ids

    def start(
        self,
        question: str,
        mandate_type: ResearchMandateType,
        *,
        user_facts: tuple[str, ...] = (),
        assumptions: tuple[str, ...] = (),
        unresolved_questions: tuple[str, ...] = (),
        exclusions: tuple[str, ...] = (),
        horizon: str | None = None,
    ) -> ApplicationResult[ResearchRun]:
        try:
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
            )
            run = ResearchRun.create(self._ids.research_run_id(), mandate, now)
            self._repository.create(run)
        except _SERVICE_ERRORS as error:
            return ApplicationResult.failed(failure_from_error(error))
        return ApplicationResult.success(run)

    def transition(
        self,
        run_id: ResearchRunId,
        target: ResearchRunState,
    ) -> ApplicationResult[ResearchRun]:
        try:
            run = self._repository.get(run_id)
            updated = run.transition(target, self._clock.now())
            self._repository.save(updated)
        except _SERVICE_ERRORS as error:
            return ApplicationResult.failed(failure_from_error(error))
        return ApplicationResult.success(updated)
