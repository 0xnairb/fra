"""Workspace maintenance boundary."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WorkspaceOperationResult:
    destination: Path
    copied: int
    migrated: int = 0


class WorkspaceMaintenance(Protocol):
    def export(self, destination: Path) -> WorkspaceOperationResult: ...

    def migrate(self, destination: Path) -> WorkspaceOperationResult: ...

    def rebuild_index(self) -> WorkspaceOperationResult: ...
