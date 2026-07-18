"""Auditable regional source and identifier mappings."""

from fra.domain.errors import RepositoryNotFoundError
from fra.domain.regions import (
    RegionalIdentifierMapping,
    RegionalPack,
    RegionalPackState,
)

_PACKS = (
    RegionalPack(
        "US",
        "United States",
        RegionalPackState.READY,
        (
            RegionalIdentifierMapping("SEC CIK", "10 decimal digits", "SEC EDGAR"),
            RegionalIdentifierMapping("exchange ticker", "exchange-qualified symbol", "listing"),
        ),
        ("sec_edgar",),
        ("yfinance (personal-use fallback only)",),
        ("Authoritative exchange prices require a separately licensed adapter.",),
    ),
    RegionalPack(
        "KR",
        "South Korea",
        RegionalPackState.PARTIAL,
        (
            RegionalIdentifierMapping("OpenDART corporation code", "8 digits", "OpenDART"),
            RegionalIdentifierMapping("stock code", "6 digits", "OpenDART/KRX"),
        ),
        ("opendart",),
        (),
        (
            "KRX market data is blocked until membership, service approval, key issuance, and "
            "terms validation are recorded.",
        ),
    ),
    RegionalPack(
        "VN",
        "Vietnam",
        RegionalPackState.PARTIAL,
        (
            RegionalIdentifierMapping(
                "exchange symbol", "HOSE:HNX:UPCOM plus symbol", "official disclosure mapping"
            ),
        ),
        ("manual_documents", "rss_atom"),
        ("yfinance (personal-use fallback only)",),
        (
            "Decision completed 2026-07-19: no authoritative price provider is approved; "
            "production coverage requires an exchange or licensed agreement and contract tests.",
        ),
    ),
)


class RegionalPackService:
    def list(self) -> tuple[RegionalPack, ...]:
        return _PACKS

    def describe(self, code: str) -> RegionalPack:
        normalized = code.strip().upper()
        try:
            return next(item for item in _PACKS if item.code == normalized)
        except StopIteration as error:
            raise RepositoryNotFoundError(f"regional pack {code} does not exist") from error
