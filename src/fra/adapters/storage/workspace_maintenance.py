"""Markdown-only export, schema migration, and disposable index operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from fra.adapters.storage.atomic_files import AtomicFileWriter
from fra.adapters.storage.markdown_codec import MarkdownCodec
from fra.adapters.storage.workspace import Workspace
from fra.domain.errors import (
    RepositoryConflictError,
    RepositoryCorruptError,
    RepositoryNotFoundError,
)
from fra.ports.workspace_maintenance import WorkspaceOperationResult


class WorkspaceMaintenanceService:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def export(self, destination: Path) -> WorkspaceOperationResult:
        if not self._workspace.initialized:
            raise RepositoryNotFoundError("workspace must be initialized before export")
        destination = destination.expanduser().resolve()
        _new_destination(destination, self._workspace.root)
        writer = AtomicFileWriter()
        copied = 0
        for source in _markdown_files(self._workspace.root):
            relative = source.relative_to(self._workspace.root)
            writer.write_text(destination / relative, source.read_text(encoding="utf-8"))
            copied += 1
        return WorkspaceOperationResult(destination, copied)

    def migrate(self, destination: Path) -> WorkspaceOperationResult:
        exported = self.export(destination)
        writer = AtomicFileWriter()
        codec = MarkdownCodec()
        migrated = 0
        failed: list[str] = []
        for path in _markdown_files(exported.destination):
            try:
                metadata, body = _front_matter(path)
                version = metadata.get("schema_version")
                if version == 0:
                    metadata["schema_version"] = 1
                    metadata["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
                    writer.write_text(path, codec.render(metadata, body))
                    migrated += 1
                elif version != 1:
                    raise RepositoryCorruptError(f"unsupported schema version {version!r}")
            except (OSError, RepositoryCorruptError, TypeError, ValueError) as error:
                failed.append(f"{path.relative_to(exported.destination)}: {error}")
        report_path = exported.destination / "migration-report.md"
        writer.write_text(
            report_path,
            codec.render(
                {
                    "schema": "fra.migration_report",
                    "schema_version": 1,
                    "id": "migration-report",
                    "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                },
                "# Workspace Migration Report\n\n"
                f"- Copied Markdown files: {exported.copied}\n"
                f"- Migrated schema-v0 files: {migrated}\n"
                f"- Skipped current files: {exported.copied - migrated - len(failed)}\n"
                f"- Failed files: {len(failed)}\n" + "".join(f"  - {item}\n" for item in failed),
            ),
        )
        if failed:
            raise RepositoryCorruptError(
                f"workspace migration failed for {len(failed)} file(s); inspect {report_path}"
            )
        return WorkspaceOperationResult(exported.destination, exported.copied, migrated)

    def rebuild_index(self) -> WorkspaceOperationResult:
        paths = tuple(
            str(path.relative_to(self._workspace.root).as_posix())
            for path in _markdown_files(self._workspace.root)
            if path.name != "index.md"
        )
        destination = self._workspace.path(".indexes/artifacts.json")
        self._workspace.writer.write_text(
            destination,
            json.dumps(
                {"schema": "fra.disposable_index", "schema_version": 1, "paths": paths},
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        links = "\n".join(f"- [{path}]({path})" for path in paths) or "- No artifacts"
        self._workspace.writer.write_text(
            self._workspace.path("index.md"),
            self._workspace.codec.render(
                {
                    "schema": "fra.workspace_index",
                    "schema_version": 1,
                    "id": "workspace-index",
                },
                f"# Disposable Workspace Index\n\n{links}\n",
            ),
        )
        return WorkspaceOperationResult(destination, len(paths))


def _new_destination(destination: Path, source: Path) -> None:
    if destination == source or destination.is_relative_to(source):
        raise RepositoryConflictError("workspace export destination must be outside the source")
    if destination.exists():
        raise RepositoryConflictError("workspace export destination must not already exist")
    destination.mkdir(mode=0o700, parents=True)


def _markdown_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(root.rglob("*.md"))
        if not any(part in {".locks", ".indexes", "cache", "logs"} for part in path.parts)
    )


def _front_matter(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    if len(parts) != 3 or parts[0]:
        raise RepositoryCorruptError(f"{path.name} does not contain YAML front matter")
    loaded = yaml.safe_load(parts[1])
    if not isinstance(loaded, dict):
        raise RepositoryCorruptError(f"{path.name} front matter is not a mapping")
    return {str(key): value for key, value in loaded.items()}, parts[2]
