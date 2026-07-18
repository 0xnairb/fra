"""Markdown repositories for explicit source status and disposable cache records."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fra.adapters.storage.serialization import decode, encode
from fra.adapters.storage.workspace import Workspace
from fra.domain.errors import (
    RepositoryConflictError,
    RepositoryCorruptError,
    RepositoryNotFoundError,
)
from fra.domain.sources import SourceCacheEntry, SourceStatusRecord


class MarkdownSourceStatusRepository:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def save(self, status: SourceStatusRecord) -> None:
        provider_id = self._workspace.safe_segment(status.provider_id)
        path = self._workspace.path(f"source-status/{provider_id}.md")
        warning_lines = (*status.capability_warnings, *status.health.warnings)
        body = (
            f"# Source Status: {provider_id}\n\n"
            f"## Health\n\n{status.health.state.value}: {status.health.summary}\n\n"
            "## Capability Warnings\n\n"
            + _bullets(warning_lines)
            + "\n## Quota or Limit Warning\n\n"
            + (status.quota_warning or "None")
            + "\n"
        )
        metadata = {
            "schema": "fra.source_status",
            "schema_version": 1,
            "id": provider_id,
            "provider_id": provider_id,
            "checked_at": _timestamp(status.checked_at),
            "created_at": _timestamp(status.checked_at),
            "updated_at": _timestamp(status.checked_at),
            "payload": encode(status),
        }
        with self._workspace.lock(f"source-status-{provider_id}"):
            if path.is_file():
                existing = _read(
                    self._workspace,
                    path,
                    "fra.source_status",
                    SourceStatusRecord,
                )
                if status.checked_at < existing.checked_at:
                    raise RepositoryConflictError(f"source status {provider_id} update is stale")
            self._workspace.writer.write_text(path, self._workspace.codec.render(metadata, body))

    def get(self, provider_id: str) -> SourceStatusRecord:
        segment = self._workspace.safe_segment(provider_id)
        path = self._workspace.path(f"source-status/{segment}.md")
        if not path.is_file():
            raise RepositoryNotFoundError(f"source status {provider_id} does not exist")
        result = _read(self._workspace, path, "fra.source_status", SourceStatusRecord)
        if result.provider_id != provider_id:
            raise RepositoryCorruptError("source status provider ID does not match its path")
        return result

    def list(self) -> tuple[SourceStatusRecord, ...]:
        root = self._workspace.path("source-status")
        if not root.is_dir():
            return ()
        return tuple(
            sorted(
                (
                    _read(self._workspace, path, "fra.source_status", SourceStatusRecord)
                    for path in root.glob("*.md")
                ),
                key=lambda item: item.provider_id,
            )
        )


class MarkdownSourceCacheRepository:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def initialize_workspace(self) -> None:
        self._workspace.initialize()

    def save(self, entry: SourceCacheEntry) -> None:
        path = self._path(entry.provider_id, entry.request_fingerprint)
        body = (
            f"# Source Cache: {entry.provider_id}\n\n"
            f"Request fingerprint: `{entry.request_fingerprint}`\n\n"
            f"Content hash: `{entry.content_hash}`\n"
        )
        metadata: dict[str, Any] = {
            "schema": "fra.source_cache",
            "schema_version": 1,
            "id": entry.request_fingerprint,
            "provider_id": entry.provider_id,
            "retrieved_at": _timestamp(entry.retrieved_at),
            "available_at": _timestamp(entry.available_at),
            "expires_at": _timestamp(entry.expires_at),
            "usage_profile": entry.usage_profile.value,
            "raw_retention": entry.raw_retention.value,
            "content_hash": entry.content_hash,
            "created_at": _timestamp(entry.retrieved_at),
            "updated_at": _timestamp(entry.retrieved_at),
            "payload": encode(entry),
        }
        with self._workspace.lock(f"cache-{entry.provider_id}-{entry.request_fingerprint}"):
            self._workspace.writer.write_text(path, self._workspace.codec.render(metadata, body))

    def get(self, provider_id: str, request_fingerprint: str) -> SourceCacheEntry | None:
        path = self._path(provider_id, request_fingerprint)
        if not path.is_file():
            return None
        entry = _read(self._workspace, path, "fra.source_cache", SourceCacheEntry)
        if entry.provider_id != provider_id or entry.request_fingerprint != request_fingerprint:
            raise RepositoryCorruptError("source cache identity does not match its path")
        return entry

    def _path(self, provider_id: str, fingerprint: str) -> Path:
        provider = self._workspace.safe_segment(provider_id)
        if not fingerprint.startswith("sha256:"):
            raise ValueError("cache request fingerprint must use sha256")
        digest = fingerprint.removeprefix("sha256:")
        if not digest or not digest.isalnum():
            raise ValueError("cache request fingerprint is not path-safe")
        return self._workspace.path(f"cache/{provider}/{digest}.md")


def _read[T](workspace: Workspace, path: Path, schema: str, expected: type[T]) -> T:
    try:
        metadata, _body = workspace.codec.parse(
            path.read_text(encoding="utf-8"), expected_schema=schema
        )
        result = decode(metadata["payload"])
    except RepositoryCorruptError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise RepositoryCorruptError(f"could not reconstruct {path.name}: {error}") from error
    if not isinstance(result, expected):
        raise RepositoryCorruptError(f"{path.name} does not contain {expected.__name__}")
    return result


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None"
