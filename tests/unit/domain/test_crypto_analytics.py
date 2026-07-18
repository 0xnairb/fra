from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from fra.domain.analytics import crypto_market_metrics
from fra.domain.errors import DomainValidationError
from fra.domain.ids import InstrumentId
from fra.domain.instruments import Currency
from fra.domain.market_data import MarketObservation, MarketSeries


def _series(*prices: str) -> MarketSeries:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return MarketSeries(
        instrument_id=InstrumentId("crypto:bitcoin"),
        observations=tuple(
            MarketObservation(
                instrument_id=InstrumentId("crypto:bitcoin"),
                observed_at=start + timedelta(days=index),
                price=Decimal(price),
                market_cap=None,
                volume=None,
                currency=Currency("USD"),
            )
            for index, price in enumerate(prices)
        ),
        currency=Currency("USD"),
    )


def test_crypto_metrics_are_deterministic_and_decimal_based() -> None:
    metrics = crypto_market_metrics(_series("100", "110", "99", "118.8"))

    assert metrics.total_return == Decimal("0.188")
    assert metrics.current_drawdown == Decimal("0")
    assert metrics.maximum_drawdown == Decimal("-0.1")
    assert metrics.observation_count == 4
    assert metrics.annualized_volatility.quantize(Decimal("0.000001")) == Decimal("2.918333")


@pytest.mark.parametrize("prices", [(), ("100",), ("100", "0")])
def test_crypto_metrics_reject_insufficient_or_non_positive_prices(prices: tuple[str, ...]) -> None:
    with pytest.raises(DomainValidationError):
        crypto_market_metrics(_series(*prices))
