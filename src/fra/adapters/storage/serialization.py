"""Restricted serializer for FRA-owned dataclass graphs."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from fra.domain.analytics import Calculation
from fra.domain.documents import Document, DocumentRef
from fra.domain.economic import EconomicObservation, EconomicSeries
from fra.domain.forecasts import (
    ExposureEdge,
    ExposureGraph,
    ExposureNode,
    Forecast,
    ForecastOutcome,
    ForecastScore,
    ForecastTrigger,
    ForecastVersion,
    InvalidationCondition,
    ResolutionRule,
)
from fra.domain.ids import (
    CalculationId,
    ClaimId,
    EvidenceId,
    ExposureGraphId,
    ForecastId,
    ForecastScoreId,
    InstrumentId,
    MandateId,
    OutcomeId,
    PlanId,
    PortfolioId,
    ProfileId,
    ResearchRunId,
    ScenarioId,
    SignalId,
    VerificationId,
)
from fra.domain.instruments import Currency
from fra.domain.market_data import MarketBar, MarketObservation, MarketQuote, MarketSeries
from fra.domain.portfolio import InvestorProfile, Portfolio, PortfolioPosition
from fra.domain.regulatory import CompanyFact
from fra.domain.research import (
    AgentRunMetadata,
    Claim,
    Evidence,
    ResearchDataRequirement,
    ResearchMandate,
    ResearchPlan,
    ResearchPlanTask,
    ResearchRun,
    ResearchScenario,
    ResearchStageCheckpoint,
    VerificationIssue,
    VerificationResult,
)
from fra.domain.shared import ArtifactRef, Failure, HealthStatus
from fra.domain.signals import Signal
from fra.domain.sources import DataEnvelope, SourceCacheEntry, SourceDescriptor, SourceStatusRecord
from fra.ports.repositories import ResearchReport

_CLASSES = (
    CalculationId,
    ClaimId,
    EvidenceId,
    ExposureGraphId,
    ForecastId,
    ForecastScoreId,
    InstrumentId,
    MandateId,
    OutcomeId,
    PlanId,
    PortfolioId,
    ProfileId,
    ResearchRunId,
    ScenarioId,
    SignalId,
    VerificationId,
    Currency,
    Document,
    DocumentRef,
    EconomicObservation,
    EconomicSeries,
    CompanyFact,
    MarketBar,
    MarketObservation,
    MarketQuote,
    MarketSeries,
    InvestorProfile,
    PortfolioPosition,
    Portfolio,
    ForecastTrigger,
    InvalidationCondition,
    ResolutionRule,
    Forecast,
    ForecastVersion,
    ForecastOutcome,
    ForecastScore,
    ExposureNode,
    ExposureEdge,
    ExposureGraph,
    Calculation,
    Claim,
    Evidence,
    ResearchDataRequirement,
    ResearchMandate,
    ResearchPlan,
    ResearchPlanTask,
    ResearchRun,
    ResearchScenario,
    AgentRunMetadata,
    ResearchStageCheckpoint,
    VerificationIssue,
    VerificationResult,
    Failure,
    HealthStatus,
    ArtifactRef,
    DataEnvelope,
    SourceDescriptor,
    SourceStatusRecord,
    SourceCacheEntry,
    Signal,
    ResearchReport,
)
_CLASS_BY_TAG = {f"{item.__module__}.{item.__qualname__}": item for item in _CLASSES}


def encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return {
            "$type": "enum",
            "class": f"{type(value).__module__}.{type(value).__qualname__}",
            "value": value.value,
        }
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": value.isoformat().replace("+00:00", "Z")}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {"$type": "timedelta", "seconds": value.total_seconds()}
    if is_dataclass(value) and not isinstance(value, type):
        tag = f"{type(value).__module__}.{type(value).__qualname__}"
        if tag not in _CLASS_BY_TAG:
            raise TypeError(f"unsupported persisted FRA type: {tag}")
        return {
            "$type": "dataclass",
            "class": tag,
            "fields": {field.name: encode(getattr(value, field.name)) for field in fields(value)},
        }
    if isinstance(value, tuple):
        return {"$type": "tuple", "items": [encode(item) for item in value]}
    if isinstance(value, frozenset):
        return {"$type": "frozenset", "items": [encode(item) for item in sorted(value, key=str)]}
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    raise TypeError(f"unsupported persisted value: {type(value).__name__}")


def decode(value: Any) -> Any:
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get("$type")
    if kind is None:
        return {key: decode(item) for key, item in value.items()}
    if kind == "decimal":
        return Decimal(str(value["value"]))
    if kind == "datetime":
        return datetime.fromisoformat(str(value["value"]).replace("Z", "+00:00"))
    if kind == "date":
        return date.fromisoformat(str(value["value"]))
    if kind == "timedelta":
        return timedelta(seconds=float(value["seconds"]))
    if kind in {"tuple", "frozenset"}:
        items = (decode(item) for item in value["items"])
        return tuple(items) if kind == "tuple" else frozenset(items)
    if kind in {"enum", "dataclass"}:
        tag = str(value["class"])
        cls: type[Any] | None = _CLASS_BY_TAG.get(tag)
        if cls is None:
            # Enum classes are resolved only from fields on allowed dataclasses.
            cls = _enum_classes().get(tag)
        if cls is None:
            raise ValueError(f"unsupported persisted FRA class: {tag}")
        if kind == "enum":
            return cls(value["value"])
        fields_value = value["fields"]
        if not isinstance(fields_value, dict):
            raise ValueError(f"persisted fields for {tag} must be a mapping")
        return cls(**{key: decode(item) for key, item in fields_value.items()})
    raise ValueError(f"unsupported persisted value tag: {kind}")


def _enum_classes() -> dict[str, type[Enum]]:
    from fra.domain.forecasts import (
        ExposureNodeKind,
        ForecastResolutionValue,
        ForecastStatus,
    )
    from fra.domain.portfolio import PortfolioKind, RiskTolerance
    from fra.domain.research import (
        ClaimConfidence,
        ClaimMateriality,
        ClaimStatus,
        ResearchMandateType,
        ResearchRunState,
        VerificationSeverity,
    )
    from fra.domain.shared import ArtifactKind, FailureKind, HealthState
    from fra.domain.signals import Confidence, SignalStance, SignalStatus, SignalStrength
    from fra.domain.sources import (
        AuthenticationKind,
        AuthorityClass,
        DataKind,
        RawRetentionPolicy,
        SourceKind,
        SourceRole,
        UsageProfile,
    )

    classes: tuple[type[Enum], ...] = (
        ClaimConfidence,
        ClaimMateriality,
        ClaimStatus,
        ResearchMandateType,
        ResearchRunState,
        VerificationSeverity,
        ForecastStatus,
        ForecastResolutionValue,
        ExposureNodeKind,
        PortfolioKind,
        RiskTolerance,
        FailureKind,
        HealthState,
        ArtifactKind,
        Confidence,
        SignalStance,
        SignalStatus,
        SignalStrength,
        AuthenticationKind,
        AuthorityClass,
        DataKind,
        RawRetentionPolicy,
        SourceKind,
        SourceRole,
        UsageProfile,
    )
    return {f"{item.__module__}.{item.__qualname__}": item for item in classes}
