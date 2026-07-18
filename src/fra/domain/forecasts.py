"""Immutable forecast, outcome, scoring, and exposure-graph domain models."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from fra.domain.errors import DomainValidationError
from fra.domain.ids import (
    EvidenceId,
    ExposureGraphId,
    ForecastId,
    ForecastScoreId,
    OutcomeId,
    ResearchRunId,
)
from fra.domain.time import as_utc


class ForecastStatus(StrEnum):
    ACTIVE = "active"
    MONITORING = "monitoring"
    INVALIDATED = "invalidated"
    RESOLVED = "resolved"
    SCORED = "scored"


@dataclass(frozen=True, slots=True)
class ForecastTrigger:
    statement: str

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise DomainValidationError("forecast trigger must not be empty")


@dataclass(frozen=True, slots=True)
class InvalidationCondition:
    statement: str

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise DomainValidationError("forecast invalidation condition must not be empty")


@dataclass(frozen=True, slots=True)
class ResolutionRule:
    version: int
    statement: str
    authoritative_source: str

    def __post_init__(self) -> None:
        if self.version < 1 or not self.statement.strip() or not self.authoritative_source.strip():
            raise DomainValidationError("resolution rule fields must not be empty")


@dataclass(frozen=True, slots=True)
class Forecast:
    id: ForecastId
    run_id: ResearchRunId
    question: str
    hypothesis: str
    trigger: ForecastTrigger
    resolution_rule: ResolutionRule
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.question.strip() or not self.hypothesis.strip():
            raise DomainValidationError("forecast requires a question and hypothesis")
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))


@dataclass(frozen=True, slots=True)
class ForecastVersion:
    forecast: Forecast
    version: int
    probability: Decimal
    issued_at: datetime
    knowledge_cutoff_at: datetime
    horizon_end: datetime
    evidence_ids: tuple[EvidenceId, ...]
    invalidation_conditions: tuple[InvalidationCondition, ...]
    transmission_path: str
    alternatives: tuple[str, ...]
    status: ForecastStatus
    supersedes_version: int | None = None
    update_reason: str | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise DomainValidationError("forecast version must be positive")
        if not self.probability.is_finite() or not Decimal(0) <= self.probability <= Decimal(1):
            raise DomainValidationError("forecast probability must be between zero and one")
        for field in ("issued_at", "knowledge_cutoff_at", "horizon_end"):
            object.__setattr__(self, field, as_utc(getattr(self, field), field=field))
        if self.knowledge_cutoff_at > self.issued_at:
            raise DomainValidationError("forecast cutoff cannot follow issuance")
        if self.horizon_end < self.issued_at:
            raise DomainValidationError("forecast horizon cannot precede issuance")
        if not self.evidence_ids or not self.invalidation_conditions:
            raise DomainValidationError("forecast requires evidence and invalidation conditions")
        if not self.transmission_path.strip() or not self.alternatives:
            raise DomainValidationError("forecast requires a transmission path and alternatives")
        if self.version == 1 and self.supersedes_version is not None:
            raise DomainValidationError("first forecast version cannot supersede another version")
        if self.version > 1 and self.supersedes_version != self.version - 1:
            raise DomainValidationError("forecast update must supersede the previous version")
        if self.version > 1 and (self.update_reason is None or not self.update_reason.strip()):
            raise DomainValidationError("forecast update requires a reason")


class ForecastResolutionValue(StrEnum):
    TRUE = "true"
    FALSE = "false"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ForecastOutcome:
    id: OutcomeId
    forecast_id: ForecastId
    forecast_version: int
    resolved_at: datetime
    value: ForecastResolutionValue
    evidence_ids: tuple[EvidenceId, ...]
    rule_version: int
    resolver: str
    ambiguity_notes: str | None = None

    def __post_init__(self) -> None:
        if self.forecast_version < 1 or self.rule_version < 1:
            raise DomainValidationError("outcome versions must be positive")
        if not self.evidence_ids or not self.resolver.strip():
            raise DomainValidationError("outcome requires evidence and a resolver")
        if self.value is ForecastResolutionValue.AMBIGUOUS and (
            self.ambiguity_notes is None or not self.ambiguity_notes.strip()
        ):
            raise DomainValidationError("ambiguous outcome requires notes")
        object.__setattr__(self, "resolved_at", as_utc(self.resolved_at, field="resolved_at"))


@dataclass(frozen=True, slots=True)
class ForecastScore:
    id: ForecastScoreId
    outcome_id: OutcomeId
    forecast_id: ForecastId
    forecast_version: int
    brier_score: Decimal | None
    scored_at: datetime

    def __post_init__(self) -> None:
        if self.forecast_version < 1:
            raise DomainValidationError("score forecast version must be positive")
        if self.brier_score is not None and not Decimal(0) <= self.brier_score <= Decimal(1):
            raise DomainValidationError("Brier score must be between zero and one")
        object.__setattr__(self, "scored_at", as_utc(self.scored_at, field="scored_at"))


class ExposureNodeKind(StrEnum):
    EVENT = "event"
    COUNTRY = "country"
    COMMODITY = "commodity"
    INDUSTRY = "industry"
    COMPANY = "company"
    INSTRUMENT = "instrument"
    TRANSMISSION = "transmission"


@dataclass(frozen=True, slots=True)
class ExposureNode:
    id: str
    kind: ExposureNodeKind
    label: str

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.label.strip():
            raise DomainValidationError("exposure node requires an ID and label")


@dataclass(frozen=True, slots=True)
class ExposureEdge:
    from_node: str
    to_node: str
    relationship: str
    direction: str
    expected_lag: str
    confidence: Decimal
    jurisdiction: str
    evidence_ids: tuple[EvidenceId, ...]
    invalidation_condition: str

    def __post_init__(self) -> None:
        text_fields = (
            self.from_node,
            self.to_node,
            self.relationship,
            self.direction,
            self.expected_lag,
            self.jurisdiction,
            self.invalidation_condition,
        )
        if any(not value.strip() for value in text_fields):
            raise DomainValidationError("exposure edge fields must not be empty")
        if not Decimal(0) <= self.confidence <= Decimal(1):
            raise DomainValidationError("exposure edge confidence must be between zero and one")
        if not self.evidence_ids:
            raise DomainValidationError("exposure edge requires supporting evidence")


@dataclass(frozen=True, slots=True)
class ExposureGraph:
    id: ExposureGraphId
    version: int
    title: str
    nodes: tuple[ExposureNode, ...]
    edges: tuple[ExposureEdge, ...]
    created_at: datetime
    supersedes_version: int | None = None

    def __post_init__(self) -> None:
        if self.version < 1 or not self.title.strip() or not self.nodes or not self.edges:
            raise DomainValidationError(
                "exposure graph requires a version, title, nodes, and edges"
            )
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise DomainValidationError("exposure graph node IDs must be unique")
        if any(
            edge.from_node not in node_ids or edge.to_node not in node_ids for edge in self.edges
        ):
            raise DomainValidationError("exposure graph edge references an unknown node")
        if self.version == 1 and self.supersedes_version is not None:
            raise DomainValidationError("first exposure graph version cannot supersede another")
        if self.version > 1 and self.supersedes_version != self.version - 1:
            raise DomainValidationError("exposure graph update must supersede its previous version")
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))
