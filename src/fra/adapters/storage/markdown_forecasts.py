"""Append-only Markdown forecast-version repository."""

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
from fra.domain.forecasts import ForecastVersion
from fra.domain.ids import ForecastId


class MarkdownForecastRepository:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def save(self, forecast: ForecastVersion) -> None:
        forecast_id = self._workspace.safe_segment(forecast.forecast.id)
        path = self._workspace.path(f"forecasts/{forecast_id}/v{forecast.version:03d}.md")
        with self._workspace.lock(f"forecast-{forecast_id}"):
            if path.exists():
                raise RepositoryConflictError(
                    f"forecast {forecast.forecast.id} version {forecast.version} is immutable"
                )
            if forecast.version > 1:
                previous = self._workspace.path(
                    f"forecasts/{forecast_id}/v{forecast.version - 1:03d}.md"
                )
                if not previous.is_file():
                    raise RepositoryConflictError("forecast versions must be contiguous")
            metadata: dict[str, Any] = {
                "schema": "fra.forecast",
                "schema_version": 1,
                "id": str(forecast.forecast.id),
                "version": forecast.version,
                "status": forecast.status.value,
                "question": forecast.forecast.question,
                "probability": str(forecast.probability),
                "issued_at": _timestamp(forecast.issued_at),
                "knowledge_cutoff_at": _timestamp(forecast.knowledge_cutoff_at),
                "horizon_end": _timestamp(forecast.horizon_end),
                "supersedes": forecast.supersedes_version,
                "created_at": _timestamp(forecast.issued_at),
                "updated_at": _timestamp(forecast.issued_at),
                "payload": encode(forecast),
            }
            body = (
                f"# Forecast {forecast.forecast.id} v{forecast.version:03d}\n\n"
                f"## Question\n\n{forecast.forecast.question}\n\n"
                f"## Hypothesis\n\n{forecast.forecast.hypothesis}\n\n"
                f"## Probability\n\n{forecast.probability}\n\n"
                f"## Trigger\n\n{forecast.forecast.trigger.statement}\n\n"
                f"## Transmission path\n\n{forecast.transmission_path}\n\n"
                "## Alternatives\n\n"
                + _bullets(forecast.alternatives)
                + "\n## Invalidation conditions\n\n"
                + _bullets(tuple(item.statement for item in forecast.invalidation_conditions))
                + "\n## Evidence snapshot\n\n"
                + _bullets(tuple(str(item) for item in forecast.evidence_ids))
            )
            self._workspace.writer.write_text(path, self._workspace.codec.render(metadata, body))

    def get(self, forecast_id: ForecastId, version: int | None = None) -> ForecastVersion:
        directory = self._workspace.path(f"forecasts/{self._workspace.safe_segment(forecast_id)}")
        paths = _version_paths(directory)
        if version is None:
            if not paths:
                raise RepositoryNotFoundError(f"forecast {forecast_id} does not exist")
            path = paths[-1]
        else:
            path = directory / f"v{version:03d}.md"
            if not path.is_file():
                raise RepositoryNotFoundError(
                    f"forecast {forecast_id} version {version} does not exist"
                )
        result = self._read(path)
        if result.forecast.id != forecast_id:
            raise RepositoryCorruptError(f"forecast file {path.name} contains a different ID")
        return result

    def list(self) -> tuple[ForecastVersion, ...]:
        root = self._workspace.path("forecasts")
        if not root.is_dir():
            return ()
        results = [
            self._read(paths[-1])
            for directory in root.iterdir()
            if directory.is_dir() and (paths := _version_paths(directory))
        ]
        return tuple(sorted(results, key=lambda item: item.issued_at, reverse=True))

    def _read(self, path: Path) -> ForecastVersion:
        try:
            metadata, _body = self._workspace.codec.parse(
                path.read_text(encoding="utf-8"), expected_schema="fra.forecast"
            )
            result = decode(metadata["payload"])
        except RepositoryCorruptError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise RepositoryCorruptError(f"could not reconstruct {path.name}: {error}") from error
        if not isinstance(result, ForecastVersion):
            raise RepositoryCorruptError(f"{path.name} does not contain a ForecastVersion")
        if path.name != f"v{result.version:03d}.md":
            raise RepositoryCorruptError(f"forecast version does not match {path.name}")
        return result


def _version_paths(directory: Path) -> list[Path]:
    return sorted(directory.glob("v[0-9][0-9][0-9].md")) if directory.is_dir() else []


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items) + "\n"
