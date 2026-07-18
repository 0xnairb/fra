"""Versioned Markdown exposure-graph repository."""

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
from fra.domain.forecasts import ExposureGraph
from fra.domain.ids import ExposureGraphId


class MarkdownExposureGraphRepository:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def save(self, graph: ExposureGraph) -> None:
        graph_id = self._workspace.safe_segment(graph.id)
        path = self._workspace.path(f"exposure-graphs/{graph_id}/v{graph.version:03d}.md")
        with self._workspace.lock(f"graph-{graph_id}"):
            if path.exists():
                raise RepositoryConflictError(
                    f"exposure graph {graph.id} version {graph.version} is immutable"
                )
            if (
                graph.version > 1
                and not self._workspace.path(
                    f"exposure-graphs/{graph_id}/v{graph.version - 1:03d}.md"
                ).is_file()
            ):
                raise RepositoryConflictError("exposure graph versions must be contiguous")
            metadata: dict[str, Any] = {
                "schema": "fra.exposure_graph",
                "schema_version": 1,
                "id": str(graph.id),
                "version": graph.version,
                "created_at": _timestamp(graph.created_at),
                "updated_at": _timestamp(graph.created_at),
                "payload": encode(graph),
            }
            nodes = "\n".join(
                f"| {node.id} | {node.kind.value} | {node.label} |" for node in graph.nodes
            )
            edges = "\n".join(
                f"| {edge.from_node} | {edge.to_node} | {edge.relationship} | "
                f"{edge.direction} | {edge.expected_lag} | {edge.confidence} | "
                f"{edge.jurisdiction} | {', '.join(map(str, edge.evidence_ids))} | "
                f"{edge.invalidation_condition} |"
                for edge in graph.edges
            )
            body = (
                f"# Exposure Graph: {graph.title}\n\n## Nodes\n\n"
                "| ID | Kind | Label |\n| --- | --- | --- |\n"
                f"{nodes}\n\n## Edges\n\n"
                "| From | To | Relationship | Direction | Lag | Confidence | Jurisdiction | "
                "Evidence | Invalidation |\n"
                "| --- | --- | --- | --- | --- | ---: | --- | --- | --- |\n"
                f"{edges}\n"
            )
            self._workspace.writer.write_text(path, self._workspace.codec.render(metadata, body))

    def get(self, graph_id: ExposureGraphId, version: int | None = None) -> ExposureGraph:
        directory = self._workspace.path(
            f"exposure-graphs/{self._workspace.safe_segment(graph_id)}"
        )
        paths = _version_paths(directory)
        if version is None:
            if not paths:
                raise RepositoryNotFoundError(f"exposure graph {graph_id} does not exist")
            path = paths[-1]
        else:
            path = directory / f"v{version:03d}.md"
            if not path.is_file():
                raise RepositoryNotFoundError(
                    f"exposure graph {graph_id} version {version} does not exist"
                )
        result = self._read(path)
        if result.id != graph_id:
            raise RepositoryCorruptError("exposure graph file contains a different ID")
        return result

    def list(self) -> tuple[ExposureGraph, ...]:
        root = self._workspace.path("exposure-graphs")
        if not root.is_dir():
            return ()
        return tuple(
            self._read(paths[-1])
            for directory in sorted(root.iterdir())
            if directory.is_dir() and (paths := _version_paths(directory))
        )

    def _read(self, path: Path) -> ExposureGraph:
        try:
            metadata, _body = self._workspace.codec.parse(
                path.read_text(encoding="utf-8"), expected_schema="fra.exposure_graph"
            )
            result = decode(metadata["payload"])
        except RepositoryCorruptError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise RepositoryCorruptError(f"could not reconstruct {path.name}: {error}") from error
        if not isinstance(result, ExposureGraph):
            raise RepositoryCorruptError(f"{path.name} does not contain an ExposureGraph")
        return result


def _version_paths(directory: Path) -> list[Path]:
    return sorted(directory.glob("v[0-9][0-9][0-9].md")) if directory.is_dir() else []


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
