"""Provider-independent workflow hooks used by the shared research orchestrator."""

from dataclasses import dataclass
from typing import Protocol

from fra.domain.analytics import Calculation
from fra.domain.forecasts import ExposureGraph, ForecastVersion
from fra.domain.portfolio import InvestorProfile, Portfolio
from fra.domain.research import (
    Evidence,
    ResearchMandate,
    ResearchMandateType,
    ResearchPlan,
    ResearchRun,
)
from fra.domain.signals import Signal
from fra.ports.repositories import ResearchReport


@dataclass(frozen=True, slots=True)
class WorkflowCollection:
    evidence: tuple[Evidence[object], ...]
    calculations: tuple[Calculation, ...]
    durable_result: dict[str, object]


@dataclass(frozen=True, slots=True)
class WorkflowFinalization:
    report: ResearchReport
    signal: Signal | None = None
    forecasts: tuple[ForecastVersion, ...] = ()
    exposure_graphs: tuple[ExposureGraph, ...] = ()
    profiles: tuple[InvestorProfile, ...] = ()
    portfolios: tuple[Portfolio, ...] = ()


class ResearchWorkflow(Protocol):
    def missing_inputs(self, mandate: ResearchMandate) -> tuple[str, ...]: ...

    async def collect(self, run: ResearchRun, plan: ResearchPlan) -> WorkflowCollection: ...

    def finalize(self, run: ResearchRun, synthesis: dict[str, object]) -> WorkflowFinalization: ...


class ResearchRegistry:
    def __init__(self) -> None:
        self._workflows: dict[ResearchMandateType, ResearchWorkflow] = {}

    def register(self, kind: ResearchMandateType, workflow: ResearchWorkflow) -> None:
        if kind in self._workflows:
            raise ValueError(f"research workflow already registered: {kind.value}")
        self._workflows[kind] = workflow

    def get(self, kind: ResearchMandateType) -> ResearchWorkflow | None:
        return self._workflows.get(kind)
