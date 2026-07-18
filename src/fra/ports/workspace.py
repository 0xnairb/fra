"""Port for workspace lifecycle operations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WorkspaceInitialization:
    root: Path
    created: bool


class WorkspacePort(Protocol):
    @property
    def root(self) -> Path: ...

    def initialize(self) -> WorkspaceInitialization: ...
