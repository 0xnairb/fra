"""Immutable Markdown signal-version repository."""

from __future__ import annotations

import builtins
import os
from pathlib import Path
from typing import Any

from fra.adapters.storage.serialization import decode, encode
from fra.adapters.storage.workspace import Workspace
from fra.domain.errors import (
    RepositoryConflictError,
    RepositoryCorruptError,
    RepositoryNotFoundError,
)
from fra.domain.ids import SignalId
from fra.domain.signals import Signal, SignalStatus


class MarkdownSignalRepository:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def save(self, signal: Signal) -> None:
        signal_id = self._workspace.safe_segment(signal.id)
        path = self._workspace.path(f"signals/{signal_id}/v{signal.version:03d}.md")
        with self._workspace.lock(f"signal-{signal_id}"):
            if path.exists():
                raise RepositoryConflictError(
                    f"signal {signal.id} version {signal.version} is immutable and already exists"
                )
            if signal.version > 1:
                previous = self._workspace.path(f"signals/{signal_id}/v{signal.version - 1:03d}.md")
                if not previous.exists():
                    raise RepositoryConflictError("signal versions must be contiguous")
                if signal.supersedes_version != signal.version - 1:
                    raise RepositoryConflictError(
                        "a signal correction must explicitly supersede the previous version"
                    )
            elif signal.supersedes_version is not None:
                raise RepositoryConflictError("the first signal version cannot supersede a version")
            metadata: dict[str, Any] = {
                "schema": "fra.signal",
                "schema_version": 1,
                "id": str(signal.id),
                "version": signal.version,
                "status": signal.status.value,
                "issued_at": signal.issued_at.isoformat().replace("+00:00", "Z"),
                "created_at": signal.issued_at.isoformat().replace("+00:00", "Z"),
                "updated_at": signal.issued_at.isoformat().replace("+00:00", "Z"),
                "payload": encode(signal),
            }
            evidence_links, run_links = self._artifact_links(signal, path)
            body = (
                f"# Signal {signal.id} v{signal.version:03d}\n\n## Summary\n\n{signal.summary}\n\n"
                "## Evidence and Calculations\n\n"
                + evidence_links
                + "\n## Rationale or Transmission Path\n\n"
                + f"{signal.rationale or 'Not provided.'}\n\n"
                "## Counter-Evidence\n\n- None recorded.\n\n"
                "## Invalidation Conditions\n\n"
                + "\n".join(f"- {item}" for item in signal.invalidation_conditions)
                + "\n\n## Limitations and Warnings\n\n"
                + "\n".join(f"- {item}" for item in (*signal.limitations, *signal.warnings))
                + "\n\n## Research Run and Report\n\n"
                + run_links
            )
            rendered = self._workspace.codec.render(metadata, body)
            self._workspace.writer.write_text(path, rendered)

    def get(self, signal_id: SignalId, version: int | None = None) -> Signal:
        directory = self._workspace.path(f"signals/{self._workspace.safe_segment(signal_id)}")
        if version is None:
            versions = self._version_paths(directory)
            if not versions:
                raise RepositoryNotFoundError(f"signal {signal_id} does not exist")
            path = versions[-1]
        else:
            path = directory / f"v{version:03d}.md"
            if not path.is_file():
                raise RepositoryNotFoundError(
                    f"signal {signal_id} version {version} does not exist"
                )
        signal = self._read(path)
        if signal.id != signal_id:
            raise RepositoryCorruptError(f"signal file {path.name} contains a different ID")
        return signal

    def list(self, statuses: frozenset[SignalStatus] = frozenset()) -> tuple[Signal, ...]:
        result: list[Signal] = []
        signals_root = self._workspace.path("signals")
        if not signals_root.exists():
            return ()
        for directory in signals_root.iterdir():
            if not directory.is_dir():
                continue
            try:
                directory = self._workspace.contain(directory)
            except ValueError as error:
                raise RepositoryCorruptError("signal path escapes the workspace") from error
            paths = self._version_paths(directory)
            if paths:
                result.append(self._read(paths[-1]))
        if statuses:
            result = [signal for signal in result if signal.status in statuses]
        return tuple(sorted(result, key=lambda signal: signal.issued_at, reverse=True))

    def _read(self, path: Path) -> Signal:
        try:
            metadata, _body = self._workspace.codec.parse(
                path.read_text(encoding="utf-8"), expected_schema="fra.signal"
            )
            signal = decode(metadata["payload"])
        except RepositoryCorruptError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise RepositoryCorruptError(f"could not reconstruct {path.name}: {error}") from error
        if not isinstance(signal, Signal):
            raise RepositoryCorruptError(f"{path.name} does not contain a Signal")
        if path.name != f"v{signal.version:03d}.md":
            raise RepositoryCorruptError(f"signal version does not match {path.name}")
        return signal

    @staticmethod
    def _version_paths(directory: Path) -> builtins.list[Path]:
        return sorted(directory.glob("v[0-9][0-9][0-9].md")) if directory.is_dir() else []

    def _artifact_links(self, signal: Signal, signal_path: Path) -> tuple[str, str]:
        run_segment = self._workspace.safe_segment(signal.run_id)
        run_matches = tuple(self._workspace.root.glob(f"runs/*/*/{run_segment}/run.md"))
        if len(run_matches) != 1:
            evidence = [f"- Evidence: {item}" for item in signal.evidence_ids]
            evidence.extend(f"- Calculation: {item}" for item in signal.calculation_ids)
            return (
                "\n".join(evidence) + "\n" if evidence else "- None.\n",
                f"- Run: {signal.run_id} (artifact not present)\n",
            )
        try:
            run_path = self._workspace.contain(run_matches[0])
        except ValueError as error:
            raise RepositoryCorruptError("signal run path escapes the workspace") from error
        run_dir = run_path.parent

        def link(target: Path, label: str) -> str:
            relative = Path(os.path.relpath(target, signal_path.parent)).as_posix()
            return f"- [{label}]({relative})" if target.is_file() else f"- {label} (not present)"

        evidence = [
            link(run_dir / "evidence" / f"{self._workspace.safe_segment(item)}.md", str(item))
            for item in signal.evidence_ids
        ]
        evidence.extend(
            link(
                run_dir / "calculations" / f"{self._workspace.safe_segment(item)}.md",
                str(item),
            )
            for item in signal.calculation_ids
        )
        run_links = "\n".join(
            (link(run_path, f"Research run {signal.run_id}"), link(run_dir / "report.md", "Report"))
        )
        return ("\n".join(evidence) + "\n" if evidence else "- None.\n", run_links + "\n")
