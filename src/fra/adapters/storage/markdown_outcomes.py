"""Markdown outcome and deterministic score repository."""

from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from fra.adapters.storage.serialization import decode, encode
from fra.adapters.storage.workspace import Workspace
from fra.domain.errors import (
    RepositoryConflictError,
    RepositoryCorruptError,
    RepositoryNotFoundError,
)
from fra.domain.forecasts import ForecastOutcome, ForecastScore
from fra.domain.ids import OutcomeId

_T = TypeVar("_T")


class MarkdownOutcomeRepository:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def save(self, outcome: ForecastOutcome) -> None:
        outcome_id = self._workspace.safe_segment(outcome.id)
        path = self._workspace.path(f"outcomes/{outcome_id}.md")
        with self._workspace.lock(f"outcome-{outcome_id}"):
            if path.exists():
                raise RepositoryConflictError(f"outcome {outcome.id} already exists")
            metadata: dict[str, Any] = {
                "schema": "fra.forecast_outcome",
                "schema_version": 1,
                "id": str(outcome.id),
                "forecast_id": str(outcome.forecast_id),
                "forecast_version": outcome.forecast_version,
                "value": outcome.value.value,
                "resolved_at": _timestamp(outcome.resolved_at),
                "created_at": _timestamp(outcome.resolved_at),
                "updated_at": _timestamp(outcome.resolved_at),
                "payload": encode(outcome),
            }
            body = (
                f"# Forecast Outcome {outcome.id}\n\n"
                f"- Forecast: {outcome.forecast_id} v{outcome.forecast_version:03d}\n"
                f"- Value: {outcome.value.value}\n"
                f"- Resolver: {outcome.resolver}\n"
                f"- Rule version: {outcome.rule_version}\n\n"
                "## Resolution evidence\n\n"
                + _bullets(tuple(str(item) for item in outcome.evidence_ids))
                + "\n## Ambiguity\n\n"
                + (outcome.ambiguity_notes or "None")
                + "\n"
            )
            self._workspace.writer.write_text(path, self._workspace.codec.render(metadata, body))

    def get(self, outcome_id: OutcomeId) -> ForecastOutcome:
        path = self._workspace.path(f"outcomes/{self._workspace.safe_segment(outcome_id)}.md")
        if not path.is_file():
            raise RepositoryNotFoundError(f"outcome {outcome_id} does not exist")
        result = self._read(path, "fra.forecast_outcome", ForecastOutcome)
        if result.id != outcome_id:
            raise RepositoryCorruptError(f"outcome file contains a different ID: {outcome_id}")
        return result

    def list(self) -> tuple[ForecastOutcome, ...]:
        root = self._workspace.path("outcomes")
        if not root.is_dir():
            return ()
        results = [
            self._read(path, "fra.forecast_outcome", ForecastOutcome)
            for path in root.glob("*.md")
            if not path.name.endswith("-score.md")
        ]
        return tuple(sorted(results, key=lambda item: item.resolved_at, reverse=True))

    def save_score(self, score: ForecastScore) -> None:
        self.get(score.outcome_id)
        outcome_id = self._workspace.safe_segment(score.outcome_id)
        path = self._workspace.path(f"outcomes/{outcome_id}-score.md")
        with self._workspace.lock(f"outcome-{outcome_id}"):
            if path.exists():
                raise RepositoryConflictError(f"outcome {score.outcome_id} already has a score")
            metadata: dict[str, Any] = {
                "schema": "fra.forecast_score",
                "schema_version": 1,
                "id": str(score.id),
                "outcome_id": str(score.outcome_id),
                "brier_score": str(score.brier_score) if score.brier_score is not None else None,
                "created_at": _timestamp(score.scored_at),
                "updated_at": _timestamp(score.scored_at),
                "payload": encode(score),
            }
            displayed = (
                "unscored (ambiguous)" if score.brier_score is None else str(score.brier_score)
            )
            body = f"# Forecast Score {score.id}\n\n- Brier score: {displayed}\n"
            self._workspace.writer.write_text(path, self._workspace.codec.render(metadata, body))

    def get_score(self, outcome_id: OutcomeId) -> ForecastScore | None:
        path = self._workspace.path(f"outcomes/{self._workspace.safe_segment(outcome_id)}-score.md")
        if not path.is_file():
            return None
        result = self._read(path, "fra.forecast_score", ForecastScore)
        if result.outcome_id != outcome_id:
            raise RepositoryCorruptError("forecast score belongs to a different outcome")
        return result

    def _read(self, path: Path, schema: str, expected: type[_T]) -> _T:
        try:
            metadata, _body = self._workspace.codec.parse(
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
    return "\n".join(f"- {item}" for item in items) + "\n"
