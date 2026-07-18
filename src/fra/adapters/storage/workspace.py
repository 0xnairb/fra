"""Workspace lifecycle, containment, and permission policy."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from fra.adapters.storage.atomic_files import AggregateLock, AtomicFileWriter
from fra.adapters.storage.markdown_codec import MarkdownCodec
from fra.ports.workspace import WorkspaceInitialization

_DIRECTORIES = (
    "profiles",
    "portfolios",
    "signals",
    "source-status",
    "forecasts",
    "outcomes",
    "exposure-graphs",
    "runs",
    "cache",
    "logs",
    ".indexes",
    ".locks",
)


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.writer = AtomicFileWriter()
        self.codec = MarkdownCodec()

    @property
    def initialized(self) -> bool:
        return (self.root / "workspace.md").is_file()

    def initialize(self) -> WorkspaceInitialization:
        created = not self.initialized
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._owner_only(self.root, directory=True)
        for name in _DIRECTORIES:
            directory = self.path(name)
            directory.mkdir(mode=0o700, exist_ok=True)
            self._owner_only(directory, directory=True)
        marker = self.path("workspace.md")
        if not marker.exists():
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            content = self.codec.render(
                {
                    "schema": "fra.workspace",
                    "schema_version": 1,
                    "id": "workspace",
                    "created_at": now,
                    "updated_at": now,
                },
                "# FRA Workspace\n\nMarkdown files in this directory are FRA's system of record.\n",
            )
            self.writer.write_text(marker, content)
        return WorkspaceInitialization(root=self.root, created=created)

    def path(self, location: str) -> Path:
        relative = PurePosixPath(location)
        if relative.is_absolute() or ".." in relative.parts or str(relative) in {"", "."}:
            raise ValueError("workspace path must be a contained relative path")
        return self.contain(self.root / Path(*relative.parts))

    def contain(self, candidate: Path) -> Path:
        candidate = candidate.resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("workspace path must be contained by the workspace root")
        return candidate

    def lock(self, aggregate: str) -> AggregateLock:
        safe = self.safe_segment(aggregate)
        return AggregateLock(self.path(f".locks/{safe}.lock"))

    @staticmethod
    def safe_segment(value: object) -> str:
        segment = str(value)
        if not segment or segment in {".", ".."} or "/" in segment or "\\" in segment:
            raise ValueError("aggregate ID is not a safe workspace path segment")
        return segment

    @staticmethod
    def _owner_only(path: Path, *, directory: bool) -> None:
        try:
            os.chmod(path, 0o700 if directory else 0o600)
        except OSError:
            # Some filesystems do not support POSIX permissions.
            return
