"""Versioned FRA-owned structured-output boundary models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from fra.domain.errors import StructuredOutputInvalidError
from fra.domain.research import (
    ClaimConfidence,
    ClaimMateriality,
    VerificationSeverity,
)
from fra.domain.sources import DataKind


class _ClosedModel(BaseModel):
    # JSON arrays naturally arrive as lists, while hermetic backends may use the
    # port's immutable tuple representation. Both normalize to JSON lists here.
    model_config = ConfigDict(extra="forbid")


class PlanTaskOutput(_ClosedModel):
    task_id: str
    description: str
    depends_on: list[str]


class PlanDataRequirementOutput(_ClosedModel):
    requirement_id: str
    description: str
    data_kind: DataKind
    subject_ids: list[str] = Field(min_length=1)
    fields: list[str] = Field(min_length=1)
    geography_or_market: str | None
    resolution: str | None
    freshness: str | None


class PlanOutput(_ClosedModel):
    objective: str
    tasks: list[PlanTaskOutput] = Field(min_length=1)
    data_requirements: list[PlanDataRequirementOutput] = Field(min_length=1)


class ClaimOutput(_ClosedModel):
    statement: str
    materiality: ClaimMateriality
    confidence: ClaimConfidence
    evidence_ids: list[str]
    calculation_ids: list[str]
    limitations: list[str]


class ScenarioOutput(_ClosedModel):
    title: str
    description: str
    evidence_ids: list[str] = Field(min_length=1)
    invalidation_conditions: list[str] = Field(min_length=1)


class AnalyzeOutput(_ClosedModel):
    claims: list[ClaimOutput] = Field(min_length=1)
    scenarios: list[ScenarioOutput] = Field(min_length=1)
    open_questions: list[str]


class VerifyIssueOutput(_ClosedModel):
    code: str
    message: str
    severity: VerificationSeverity
    claim_id: str | None


class VerifyOutput(_ClosedModel):
    passed: bool
    issues: list[VerifyIssueOutput]


class SynthesizeOutput(_ClosedModel):
    title: str
    summary: str
    limitations: list[str]


AgentSchemaName = Literal["plan", "analyze", "verify", "synthesize"]


class AgentSchemaRegistry:
    """Generate schemas and validate transport output from one model registry."""

    VERSION = 2
    _MODELS: ClassVar[dict[str, type[_ClosedModel]]] = {
        "plan": PlanOutput,
        "analyze": AnalyzeOutput,
        "verify": VerifyOutput,
        "synthesize": SynthesizeOutput,
    }

    def schema_for(self, stage: str) -> dict[str, Any]:
        model = self._model(stage)
        schema = model.model_json_schema()
        schema["$id"] = f"fra.agent.{stage}.v{self.VERSION}"
        return schema

    def validate(self, stage: str, values: Mapping[str, object]) -> dict[str, object]:
        try:
            model = self._model(stage).model_validate(dict(values))
        except ValidationError as error:
            raise StructuredOutputInvalidError(
                f"{stage} output does not match fra.agent.{stage}.v{self.VERSION}: {error}"
            ) from error
        return model.model_dump(mode="json")

    def _model(self, stage: str) -> type[_ClosedModel]:
        try:
            return self._MODELS[stage]
        except KeyError as error:
            raise ValueError(f"unknown agent schema stage: {stage}") from error
