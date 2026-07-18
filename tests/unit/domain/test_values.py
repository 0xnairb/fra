from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fra.domain.errors import DomainValidationError
from fra.domain.ids import InstrumentId
from fra.domain.instruments import AssetClass, Currency, InstrumentRef, Money, ProviderAlias
from fra.domain.time import as_utc


def test_datetime_values_must_be_timezone_aware_and_are_normalized_to_utc() -> None:
    value = datetime.fromisoformat("2026-07-18T15:00:00+07:00")

    assert as_utc(value) == datetime(2026, 7, 18, 8, tzinfo=UTC)

    with pytest.raises(DomainValidationError, match="timezone-aware"):
        as_utc(datetime(2026, 7, 18, 8))


def test_money_uses_decimal_and_requires_matching_currencies_for_arithmetic() -> None:
    usd = Currency("usd")

    assert Money(Decimal("1.10"), usd) + Money(Decimal("2.20"), usd) == Money(Decimal("3.30"), usd)

    with pytest.raises(DomainValidationError, match="same currency"):
        Money(Decimal("1"), usd) + Money(Decimal("1"), Currency("EUR"))


def test_instrument_identity_is_separate_from_provider_symbols() -> None:
    instrument = InstrumentRef(
        id=InstrumentId("instrument_0001"),
        asset_class=AssetClass.CRYPTO,
        name="Bitcoin",
        currency=Currency("USD"),
        aliases=(ProviderAlias(provider_id="coingecko", value="bitcoin"),),
        display_symbol="BTC",
    )

    assert instrument.id.value == "instrument_0001"
    assert instrument.display_symbol == "BTC"
    assert instrument.alias_for("coingecko") == "bitcoin"
