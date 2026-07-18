"""Suitability-aware, deterministic multi-asset allocation workflow."""

import json
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import cast

from fra.application.research_orchestrator import ResearchOrchestrator
from fra.application.research_workflows import WorkflowCollection, WorkflowFinalization
from fra.application.source_platform import SourceRouter
from fra.domain.analytics import Calculation, crypto_market_metrics
from fra.domain.errors import CapabilityUnavailableError, DomainValidationError
from fra.domain.ids import CalculationId, EvidenceId, InstrumentId, ProfileId
from fra.domain.instruments import Currency, InstrumentRef
from fra.domain.market_data import HistoryRequest, InstrumentQuery, MarketSeries
from fra.domain.portfolio import (
    AllocationCandidate,
    InvestorProfile,
    Portfolio,
    PortfolioKind,
    PortfolioPosition,
    RiskTolerance,
    propose_allocation,
)
from fra.domain.research import (
    Evidence,
    ResearchMandate,
    ResearchMandateType,
    ResearchPlan,
    ResearchRun,
)
from fra.domain.signals import (
    Confidence,
    Signal,
    SignalStance,
    SignalStatus,
    SignalStrength,
)
from fra.domain.sources import DataEnvelope, DataKind, EvidenceRequirement, UsageProfile
from fra.ports.clock import Clock
from fra.ports.ids import IdGenerator
from fra.ports.market_data import MarketDataProvider
from fra.ports.repositories import ResearchReport


@dataclass(frozen=True, slots=True)
class AllocationResearchRequest:
    horizon_years: int | None
    risk_tolerance: RiskTolerance | None
    maximum_loss: Decimal | None
    liquidity_need: Decimal | None
    tax_jurisdiction: str | None
    investment_objective: str | None = None
    risk_capacity: RiskTolerance | None = None
    maximum_asset_weight: Decimal = Decimal("0.5")
    minimum_cash_weight: Decimal = Decimal("0.1")
    base_currency: Currency = field(default_factory=lambda: Currency("USD"))

    def __post_init__(self) -> None:
        if self.horizon_years is not None and self.horizon_years < 1:
            raise DomainValidationError("allocation horizon must be positive")
        for name in ("maximum_loss", "liquidity_need"):
            value = getattr(self, name)
            if value is not None and not Decimal(0) <= value <= Decimal(1):
                raise DomainValidationError(f"allocation {name} must be zero to one")


class AllocationResearchService:
    def __init__(self, orchestrator: ResearchOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def start(self, request: AllocationResearchRequest) -> ResearchRun:
        values = {
            "horizon_years": request.horizon_years,
            "risk_tolerance": request.risk_tolerance.value if request.risk_tolerance else None,
            "maximum_loss": request.maximum_loss,
            "liquidity_need": request.liquidity_need,
            "tax_jurisdiction": request.tax_jurisdiction,
            "investment_objective": request.investment_objective,
            "risk_capacity": request.risk_capacity.value if request.risk_capacity else None,
            "maximum_asset_weight": request.maximum_asset_weight,
            "minimum_cash_weight": request.minimum_cash_weight,
            "base_currency": request.base_currency.code,
        }
        missing = tuple(name.replace("_", " ") for name, value in values.items() if value is None)
        parameters = tuple(
            (name, str(value)) for name, value in values.items() if value is not None
        )
        return await self._orchestrator.start(
            "Propose a constraint-bound research allocation for the declared profile.",
            ResearchMandateType.ASSET_ALLOCATION,
            unresolved_questions=missing,
            horizon=f"{request.horizon_years} years" if request.horizon_years else None,
            parameters=parameters,
        )


class AllocationResearchWorkflow:
    def __init__(self, router: SourceRouter, clock: Clock, ids: IdGenerator) -> None:
        self._router = router
        self._clock = clock
        self._ids = ids

    def missing_inputs(self, mandate: ResearchMandate) -> tuple[str, ...]:
        parameters = dict(mandate.parameters)
        required = (
            "horizon_years",
            "risk_tolerance",
            "maximum_loss",
            "liquidity_need",
            "tax_jurisdiction",
            "investment_objective",
            "risk_capacity",
        )
        return tuple(name.replace("_", " ") for name in required if name not in parameters)

    async def collect(self, run: ResearchRun, plan: ResearchPlan) -> WorkflowCollection:
        if not any(item.data_kind is DataKind.MARKET_SERIES for item in plan.data_requirements):
            raise CapabilityUnavailableError(
                "allocation plan requires typed market-series evidence"
            )
        parameters = dict(run.mandate.parameters)
        now = self._clock.now()
        requirement = EvidenceRequirement(
            DataKind.MARKET_SERIES,
            tuple(InstrumentId(f"etf:{symbol.lower()}") for symbol in ("SPY", "BND", "GLD")),
            UsageProfile.LOCAL_PERSONAL_RESEARCH,
            fields=("adjusted_close",),
            start_at=now - timedelta(days=365),
            end_at=now,
            resolution="daily",
        )
        evidence: list[Evidence[object]] = []
        candidates: list[AllocationCandidate] = []
        evidence_ids: list[EvidenceId] = []
        source_warnings: set[str] = set()
        for symbol in ("SPY", "BND", "GLD"):

            async def fetch(
                adapter: object, symbol: str = symbol
            ) -> tuple[InstrumentRef, DataEnvelope[MarketSeries]]:
                provider = cast(MarketDataProvider, adapter)
                matches = await provider.resolve_instrument(InstrumentQuery(symbol))
                if len(matches) != 1:
                    raise CapabilityUnavailableError(
                        f"could not resolve allocation candidate {symbol}"
                    )
                instrument = matches[0].instrument
                envelope = await provider.history(
                    HistoryRequest(instrument, now - timedelta(days=365), now, "daily")
                )
                return instrument, envelope

            execution = await self._router.execute(requirement, fetch)
            chosen: tuple[InstrumentRef, DataEnvelope[MarketSeries]] | None = None
            for routed in execution.values:
                instrument, envelope = routed.value
                evidence_id = self._ids.evidence_id()
                evidence.append(
                    cast(
                        Evidence[object],
                        Evidence.from_envelope(
                            id=evidence_id,
                            run_id=run.id,
                            kind=DataKind.MARKET_SERIES,
                            summary=f"{routed.provider_id} adjusted {symbol} history",
                            envelope=envelope,
                            knowledge_cutoff_at=now,
                            created_at=now,
                        ),
                    )
                )
                if envelope.descriptor.required_attribution:
                    source_warnings.add(envelope.descriptor.required_attribution)
                if chosen is not None:
                    continue
                chosen = instrument, envelope
                evidence_ids.append(evidence_id)
            if chosen is None:
                raise CapabilityUnavailableError(
                    f"routing produced no usable allocation history for {symbol}"
                )
            instrument, envelope = chosen
            volatility = min(
                Decimal(1),
                crypto_market_metrics(
                    envelope.value, annualization_periods=252
                ).annualized_volatility,
            )
            candidates.append(
                AllocationCandidate(
                    instrument.id,
                    symbol,
                    instrument.currency or Currency(parameters["base_currency"]),
                    volatility,
                    -min(Decimal("0.8"), volatility * Decimal(2)),
                )
            )
        profile = _profile(parameters, self._ids, now)
        allocation = propose_allocation(profile, tuple(candidates))
        if allocation.stress_loss < -profile.maximum_loss:
            raise DomainValidationError(
                "deterministic stress loss exceeds the declared maximum loss"
            )
        calculation_id = self._ids.calculation_id()
        calculation = Calculation(
            calculation_id,
            run.id,
            "constraint_bound_allocation",
            1,
            tuple(evidence_ids),
            tuple(sorted(parameters.items())),
            (
                ("concentration_hhi", allocation.concentration),
                ("stress_loss", allocation.stress_loss),
                *((f"weight_{item.symbol}", item.weight) for item in allocation.positions),
            ),
            now,
        )
        return WorkflowCollection(
            tuple(evidence),
            (calculation,),
            {
                "profile": _profile_record(profile),
                "positions": [
                    {
                        "instrument_id": str(item.instrument_id),
                        "symbol": item.symbol,
                        "weight": str(item.weight),
                        "currency": item.currency.code,
                    }
                    for item in allocation.positions
                ],
                "concentration": str(allocation.concentration),
                "concentration_method": (
                    "Herfindahl-Hirschman index: sum of squared proposed weights, including cash."
                ),
                "stress_loss": str(allocation.stress_loss),
                "stress_method": (
                    "For each risky asset, stress loss is negative twice annualized volatility, "
                    "capped at an 80% loss; portfolio stress is the weight-summed asset stress."
                ),
                "maximum_loss_semantics": (
                    "Maximum loss is the largest tolerated fractional portfolio loss under this "
                    "deterministic stress proxy; it is not a VaR confidence level or forecast."
                ),
                "evidence_ids": [str(item) for item in evidence_ids],
                "calculation_id": str(calculation_id),
                "source_warning": "; ".join(sorted(source_warnings)) or "No attribution supplied",
            },
        )

    def finalize(self, run: ResearchRun, synthesis: dict[str, object]) -> WorkflowFinalization:
        value = _collection(run)
        profile = _profile_from_record(cast(dict[str, object], value["profile"]))
        positions = tuple(
            PortfolioPosition(
                InstrumentId(str(item["instrument_id"])),
                str(item["symbol"]),
                Decimal(str(item["weight"])),
                Currency(str(item["currency"])),
            )
            for item in cast(list[dict[str, object]], value["positions"])
        )
        evidence_ids = tuple(
            EvidenceId(str(item)) for item in cast(list[object], value["evidence_ids"])
        )
        calculation_id = CalculationId(str(value["calculation_id"]))
        portfolio = Portfolio(
            self._ids.portfolio_id(),
            1,
            PortfolioKind.PROPOSED,
            profile.id,
            positions,
            self._clock.now(),
            evidence_ids,
            (calculation_id,),
        )
        signal = Signal(
            self._ids.signal_id(),
            1,
            run.id,
            tuple(str(item.instrument_id) for item in positions),
            "Constraint-bound research allocation; no order or account action was performed.",
            SignalStance.NEUTRAL,
            SignalStrength.MODERATE,
            Confidence.MEDIUM,
            run.mandate.horizon or "unspecified",
            self._clock.now(),
            self._clock.now(),
            evidence_ids,
            ("Suitability inputs change", "Stress loss exceeds declared maximum loss"),
            SignalStatus.ACTIVE,
            (str(calculation_id),),
            limitations=(
                "yfinance is unofficial and personal-use-only.",
                "Weights are deterministic research outputs, not personalized financial advice.",
            ),
        )
        report = ResearchReport(
            "Suitability-Aware Allocation Research",
            _report(run, value, profile, portfolio, synthesis),
        )
        return WorkflowFinalization(
            report=report,
            signal=signal,
            profiles=(profile,),
            portfolios=(portfolio,),
        )


def _profile(parameters: dict[str, str], ids: IdGenerator, now: object) -> InvestorProfile:
    from datetime import datetime

    assert isinstance(now, datetime)
    return InvestorProfile(
        ids.profile_id(),
        int(parameters["horizon_years"]),
        RiskTolerance(parameters["risk_tolerance"]),
        parameters["investment_objective"],
        RiskTolerance(parameters["risk_capacity"]),
        Decimal(parameters["maximum_loss"]),
        Decimal(parameters["liquidity_need"]),
        parameters["tax_jurisdiction"],
        Currency(parameters["base_currency"]),
        Decimal(parameters["maximum_asset_weight"]),
        Decimal(parameters["minimum_cash_weight"]),
        (),
        now,
    )


def _profile_record(profile: InvestorProfile) -> dict[str, object]:
    return {
        "id": str(profile.id),
        "horizon_years": profile.horizon_years,
        "risk_tolerance": profile.risk_tolerance.value,
        "investment_objective": profile.investment_objective,
        "risk_capacity": profile.risk_capacity.value,
        "maximum_loss": str(profile.maximum_loss),
        "liquidity_need": str(profile.liquidity_need),
        "tax_jurisdiction": profile.tax_jurisdiction,
        "base_currency": profile.base_currency.code,
        "maximum_asset_weight": str(profile.maximum_asset_weight),
        "minimum_cash_weight": str(profile.minimum_cash_weight),
        "confirmed_at": profile.confirmed_at.isoformat(),
    }


def _profile_from_record(value: dict[str, object]) -> InvestorProfile:
    from datetime import datetime

    return InvestorProfile(
        ProfileId(str(value["id"])),
        int(str(value["horizon_years"])),
        RiskTolerance(str(value["risk_tolerance"])),
        str(value["investment_objective"]),
        RiskTolerance(str(value["risk_capacity"])),
        Decimal(str(value["maximum_loss"])),
        Decimal(str(value["liquidity_need"])),
        str(value["tax_jurisdiction"]),
        Currency(str(value["base_currency"])),
        Decimal(str(value["maximum_asset_weight"])),
        Decimal(str(value["minimum_cash_weight"])),
        (),
        datetime.fromisoformat(str(value["confirmed_at"])),
    )


def _collection(run: ResearchRun) -> dict[str, object]:
    checkpoint = next((item for item in run.stage_checkpoints if item.stage == "collect"), None)
    if checkpoint is None:
        raise CapabilityUnavailableError("allocation collection checkpoint is missing")
    value = json.loads(checkpoint.result_json)
    if not isinstance(value, dict):
        raise CapabilityUnavailableError("allocation collection checkpoint is invalid")
    return value


def _report(
    run: ResearchRun,
    value: dict[str, object],
    profile: InvestorProfile,
    portfolio: Portfolio,
    synthesis: dict[str, object],
) -> str:
    rows = "\n".join(
        f"| {item.symbol} | {item.instrument_id} | {item.weight} | {item.currency.code} |"
        for item in portfolio.positions
    )
    return (
        "# Suitability-Aware Allocation Research\n\n"
        "## Confirmed profile and constraints\n\n"
        f"- Horizon: {run.mandate.horizon}\n"
        f"- Investment objective: {profile.investment_objective}\n"
        f"- Risk capacity: {profile.risk_capacity.value}\n"
        f"- Profile artifact: `profiles/{portfolio.profile_id}.md`\n"
        f"- Maximum loss stress limit: {dict(run.mandate.parameters)['maximum_loss']}\n\n"
        "## Deterministic proposed weights\n\n"
        "| Symbol | Instrument | Weight | Currency |\n| --- | --- | ---: | --- |\n"
        f"{rows}\n\n"
        f"- Concentration HHI: {value['concentration']}\n"
        f"- Concentration method: {value['concentration_method']}\n"
        f"- Declared stress loss: {value['stress_loss']}\n"
        f"- Stress method: {value['stress_method']}\n"
        f"- Maximum-loss semantics: {value['maximum_loss_semantics']}\n"
        f"- Portfolio artifact: `portfolios/{portfolio.id}/v001.md`\n\n"
        "## Tradeoffs and alternatives\n\n"
        f"{synthesis.get('summary', 'No additional agent synthesis.')}\n\n"
        "## Source warning\n\n"
        f"{value['source_warning']}. This source is unofficial and personal-use-only.\n\n"
        "## Rebalancing and invalidation\n\n"
        "- Re-run when suitability inputs change.\n"
        "- Invalidate when stress loss exceeds the confirmed maximum loss.\n\n"
        "## Limitations\n\n"
        "- No brokerage, account, custody, or order action is available.\n"
        "- The proposal is a research signal rather than individualized advice.\n"
    )
