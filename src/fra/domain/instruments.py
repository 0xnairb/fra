"""Instrument, currency, and monetary values."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from fra.domain.errors import DomainValidationError
from fra.domain.ids import InstrumentId


@dataclass(frozen=True, slots=True)
class Currency:
    """Three-letter currency code used for explicit monetary units."""

    code: str

    def __post_init__(self) -> None:
        code = self.code.strip().upper()
        if len(code) != 3 or not code.isalpha() or not code.isascii():
            raise DomainValidationError("currency must be a three-letter ASCII code")
        object.__setattr__(self, "code", code)

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class Money:
    """An exact decimal amount with an explicit currency."""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite():
            raise DomainValidationError("money amount must be a finite Decimal")

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise DomainValidationError("money arithmetic requires the same currency")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise DomainValidationError("money arithmetic requires the same currency")
        return Money(self.amount - other.amount, self.currency)


class AssetClass(StrEnum):
    """Initial provider-independent instrument classes."""

    CRYPTO = "crypto"
    EQUITY = "equity"
    COMMODITY = "commodity"
    FIXED_INCOME = "fixed_income"
    FX = "fx"
    FUND = "fund"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ProviderAlias:
    """An external provider identifier kept separate from domain identity."""

    provider_id: str
    value: str

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.value.strip():
            raise DomainValidationError("provider aliases require a provider and value")


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    """A stable instrument reference with optional external aliases."""

    id: InstrumentId
    asset_class: AssetClass
    name: str
    currency: Currency | None = None
    aliases: tuple[ProviderAlias, ...] = ()
    display_symbol: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainValidationError("instrument name must not be empty")
        providers = [alias.provider_id for alias in self.aliases]
        if len(providers) != len(set(providers)):
            raise DomainValidationError("an instrument cannot have duplicate provider aliases")

    def alias_for(self, provider_id: str) -> str | None:
        """Return an external alias without using it as domain identity."""
        return next(
            (alias.value for alias in self.aliases if alias.provider_id == provider_id), None
        )
