"""Application services for workspace lifecycle and read-only queries."""

from dataclasses import dataclass
from pathlib import Path

from fra.domain.ids import ResearchRunId
from fra.domain.research import ResearchRun
from fra.domain.signals import Signal
from fra.ports.repositories import ResearchRepository, ResearchRunSummary, SignalRepository
from fra.ports.workspace import WorkspaceInitialization, WorkspacePort


@dataclass(frozen=True, slots=True)
class WorkspaceService:
    workspace: WorkspacePort

    def initialize(self) -> WorkspaceInitialization:
        return self.workspace.initialize()

    @property
    def root(self) -> Path:
        return self.workspace.root


class ResearchQueryService:
    def __init__(self, repository: ResearchRepository) -> None:
        self._repository = repository

    def list(self) -> tuple[ResearchRunSummary, ...]:
        return self._repository.list()

    def show(self, run_id: ResearchRunId) -> ResearchRun:
        return self._repository.get(run_id)


class SignalQueryService:
    def __init__(self, repository: SignalRepository) -> None:
        self._repository = repository

    def list(self) -> tuple[Signal, ...]:
        return self._repository.list()
