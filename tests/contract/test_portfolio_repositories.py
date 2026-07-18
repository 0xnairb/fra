from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fra.adapters.in_memory.repositories import (
    InMemoryPortfolioRepository,
    InMemoryProfileRepository,
)
from fra.adapters.storage.markdown_portfolios import (
    MarkdownPortfolioRepository,
    MarkdownProfileRepository,
)
from fra.adapters.storage.workspace import Workspace
from fra.domain.errors import RepositoryConflictError
from fra.domain.ids import CalculationId, EvidenceId, InstrumentId, PortfolioId, ProfileId
from fra.domain.instruments import Currency
from fra.domain.portfolio import (
    InvestorProfile,
    Portfolio,
    PortfolioKind,
    PortfolioPosition,
    RiskTolerance,
)
from fra.ports.repositories import PortfolioRepository, ProfileRepository

NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)


@pytest.mark.parametrize("kind", ["memory", "markdown"])
def test_profile_and_versioned_portfolio_repository_contract(kind: str, tmp_path: Path) -> None:
    profiles, portfolios = _repositories(kind, tmp_path)
    profile = _profile()
    profiles.save(profile)

    assert profiles.get(profile.id) == profile
    assert profiles.list() == (profile,)
    with pytest.raises(RepositoryConflictError):
        profiles.save(profile)

    first = _portfolio(profile.id)
    portfolios.save(first)
    second = replace(
        first,
        version=2,
        as_of=NOW + timedelta(days=1),
        supersedes_version=1,
    )
    portfolios.save(second)

    assert portfolios.get(first.id, 1) == first
    assert portfolios.get(first.id) == second
    assert portfolios.list() == (second,)
    with pytest.raises(RepositoryConflictError):
        portfolios.save(second)


def _repositories(kind: str, tmp_path: Path) -> tuple[ProfileRepository, PortfolioRepository]:
    if kind == "memory":
        return InMemoryProfileRepository(), InMemoryPortfolioRepository()
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    return MarkdownProfileRepository(workspace), MarkdownPortfolioRepository(workspace)


def _profile() -> InvestorProfile:
    return InvestorProfile(
        ProfileId("profile_0001"),
        10,
        RiskTolerance.MEDIUM,
        "Long-term capital growth",
        RiskTolerance.MEDIUM,
        Decimal("0.35"),
        Decimal("0.10"),
        "US",
        Currency("USD"),
        Decimal("0.50"),
        Decimal("0.10"),
        (),
        NOW,
    )


def _portfolio(profile_id: ProfileId) -> Portfolio:
    return Portfolio(
        PortfolioId("portfolio_0001"),
        1,
        PortfolioKind.PROPOSED,
        profile_id,
        (
            PortfolioPosition(InstrumentId("etf:spy"), "SPY", Decimal("0.6"), Currency("USD")),
            PortfolioPosition(InstrumentId("cash:base"), "CASH", Decimal("0.4"), Currency("USD")),
        ),
        NOW,
        (EvidenceId("evidence_0001"),),
        (CalculationId("calculation_0001"),),
    )
