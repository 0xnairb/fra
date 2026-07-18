from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fra.domain.errors import DomainValidationError
from fra.domain.ids import InstrumentId, ProfileId
from fra.domain.instruments import Currency
from fra.domain.portfolio import (
    AllocationCandidate,
    InvestorProfile,
    RiskTolerance,
    propose_allocation,
)

NOW = datetime(2026, 7, 19, tzinfo=UTC)


def test_allocation_is_deterministic_sums_exactly_and_respects_constraints() -> None:
    profile = _profile()
    candidates = (
        AllocationCandidate(
            InstrumentId("equity:us:SPY"), "SPY", Currency("USD"), Decimal("0.8"), Decimal("-0.35")
        ),
        AllocationCandidate(
            InstrumentId("bond:us:BND"), "BND", Currency("USD"), Decimal("0.2"), Decimal("-0.08")
        ),
        AllocationCandidate(
            InstrumentId("commodity:GLD"), "GLD", Currency("USD"), Decimal("0.5"), Decimal("-0.15")
        ),
    )

    first = propose_allocation(profile, candidates)
    second = propose_allocation(profile, candidates)

    assert first == second
    assert sum((item.weight for item in first.positions), Decimal(0)) == Decimal(1)
    assert max(item.weight for item in first.positions) <= profile.maximum_asset_weight
    assert first.positions[-1].instrument_id == InstrumentId("cash:base")
    assert first.positions[-1].weight == Decimal("0.10")
    assert first.stress_loss < 0


def test_infeasible_allocation_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="infeasible"):
        propose_allocation(
            _profile(maximum_asset_weight=Decimal("0.2")),
            (
                AllocationCandidate(
                    InstrumentId("equity:us:SPY"),
                    "SPY",
                    Currency("USD"),
                    Decimal("0.8"),
                    Decimal("-0.3"),
                ),
            ),
        )


def _profile(maximum_asset_weight: Decimal = Decimal("0.5")) -> InvestorProfile:
    return InvestorProfile(
        ProfileId("profile_0001"),
        10,
        RiskTolerance.MEDIUM,
        "Long-term capital growth",
        RiskTolerance.MEDIUM,
        Decimal("0.25"),
        Decimal("0.10"),
        "US",
        Currency("USD"),
        maximum_asset_weight,
        Decimal("0.10"),
        (),
        NOW,
    )
