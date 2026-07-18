"""Conditional CoinGecko Demo adapter for bounded crypto market history."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.common.manifests import validate_source_manifest
from fra.domain.errors import (
    CapabilityUnavailableError,
    ExternalDataInvalidError,
    PointInTimeUnavailableError,
)
from fra.domain.ids import InstrumentId
from fra.domain.instruments import AssetClass, Currency, InstrumentRef, ProviderAlias
from fra.domain.market_data import (
    HistoryRequest,
    InstrumentMatch,
    InstrumentQuery,
    MarketDataCapabilities,
    MarketObservation,
    MarketQuote,
    MarketSeries,
)
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor

BASE_URL = "https://api.coingecko.com/api/v3"
_INSTRUMENTS = {
    "bitcoin": ("bitcoin", "Bitcoin", "BTC"),
    "btc": ("bitcoin", "Bitcoin", "BTC"),
    "ethereum": ("ethereum", "Ethereum", "ETH"),
    "eth": ("ethereum", "Ethereum", "ETH"),
}


class CoinGeckoMarketDataAdapter:
    def __init__(
        self,
        client: HttpClient,
        *,
        api_key: str | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        base_url: str = BASE_URL,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._now = now
        self._base_url = base_url.rstrip("/")
        self._descriptor = validate_source_manifest(
            {
                "manifest_version": 1,
                "provider_id": "coingecko",
                "adapter_version": "1.0.0",
                "source_kinds": ["market_data"],
                "authority_class": "aggregator",
                "point_in_time_support": False,
                "allowed_usage_profiles": ["local_personal_research"],
                "raw_retention": "metadata_only",
                "terms_url": "https://www.coingecko.com/en/api_terms",
                "terms_reviewed_at": "2026-07-19",
                "independence_group": "coingecko",
                "markets": ["GLOBAL", "CRYPTO"],
                "frequencies": ["daily", "hourly"],
                "authentication_kind": "api_key",
                "credential_environment_names": ["COINGECKO_DEMO_API_KEY"],
                "quota_description": "Demo plan quota and per-minute rate limits apply",
                "normal_update_cadence": "provider-defined",
                "maximum_expected_age_seconds": 3600,
                "required_attribution": "Data provided by CoinGecko",
                "fields": ["price", "market_cap", "volume"],
            }
        )

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> MarketDataCapabilities:
        return MarketDataCapabilities(
            quotes=True,
            history=True,
            resolutions=frozenset({"daily", "hourly"}),
        )

    async def health(self) -> HealthStatus:
        await self._client.get(f"{self._base_url}/ping", headers=self._headers())
        return HealthStatus(HealthState.HEALTHY, self._now(), "CoinGecko Demo API reachable")

    async def resolve_instrument(self, query: InstrumentQuery) -> tuple[InstrumentMatch, ...]:
        normalized = query.text.strip().lower()
        match = _INSTRUMENTS.get(normalized)
        if match is None:
            return ()
        coin_id, name, symbol = match
        return (
            InstrumentMatch(
                instrument=InstrumentRef(
                    id=InstrumentId(f"crypto:{coin_id}"),
                    asset_class=AssetClass.CRYPTO,
                    name=name,
                    currency=Currency("USD"),
                    aliases=(ProviderAlias("coingecko", coin_id),),
                    display_symbol=symbol,
                ),
                score=Decimal(1),
            ),
        )

    async def quote(self, instrument: InstrumentRef) -> DataEnvelope[MarketQuote]:
        coin_id = self._coin_id(instrument)
        currency = instrument.currency or Currency("USD")
        params: dict[str, str | int] = {
            "ids": coin_id,
            "vs_currencies": currency.code.lower(),
            "include_last_updated_at": "true",
        }
        url = f"{self._base_url}/simple/price"
        response = await self._client.get(url, params=params, headers=self._headers())
        payload = response.json()
        record = payload.get(coin_id) if isinstance(payload, dict) else None
        if not isinstance(record, dict):
            raise ExternalDataInvalidError("CoinGecko quote response is missing the requested coin")
        price = _decimal(record.get(currency.code.lower()), "quote price")
        raw_timestamp = record.get("last_updated_at")
        observed_at = _unix_time(raw_timestamp, milliseconds=False, field="last_updated_at")
        retrieved_at = self._now()
        return DataEnvelope(
            value=MarketQuote(instrument.id, price, currency, observed_at),
            descriptor=self._descriptor,
            provider_record_id=coin_id,
            source=url,
            available_at=retrieved_at,
            retrieved_at=retrieved_at,
            provider_subject_ids=(coin_id,),
            fra_subject_ids=(instrument.id,),
            observed_at=observed_at,
            currency=currency.code,
            content_hash=response.content_hash,
            request_fingerprint=response.request_fingerprint,
            usage_policy_id="coingecko-demo-local-evaluation-2026-07-19",
            required_attribution=self._descriptor.required_attribution,
            missing_fields=("published_at", "historical_availability", "vintage"),
        )

    async def history(self, request: HistoryRequest) -> DataEnvelope[MarketSeries]:
        if request.point_in_time_at is not None:
            raise PointInTimeUnavailableError(
                "CoinGecko market charts do not expose historical availability or vintages"
            )
        if request.resolution not in self.capabilities().resolutions:
            raise CapabilityUnavailableError(
                f"CoinGecko resolution is unsupported: {request.resolution}"
            )
        if request.end_at - request.start_at > timedelta(days=365):
            raise CapabilityUnavailableError("CoinGecko MVP history is bounded to 365 days")
        coin_id = self._coin_id(request.instrument)
        currency = request.instrument.currency or Currency("USD")
        params: dict[str, str | int] = {
            "vs_currency": currency.code.lower(),
            "from": int(request.start_at.timestamp()),
            "to": int(request.end_at.timestamp()),
            "interval": request.resolution,
        }
        url = f"{self._base_url}/coins/{quote(coin_id, safe='')}/market_chart/range"
        response = await self._client.get(url, params=params, headers=self._headers())
        observations = _market_observations(response.json(), request.instrument.id, currency)
        if not observations:
            raise CapabilityUnavailableError(
                "CoinGecko returned no history for the requested range"
            )
        retrieved_at = self._now()
        return DataEnvelope(
            value=MarketSeries(request.instrument.id, observations, currency),
            descriptor=self._descriptor,
            provider_record_id=f"{coin_id}:{request.start_at.date()}:{request.end_at.date()}",
            source=url,
            available_at=retrieved_at,
            retrieved_at=retrieved_at,
            provider_subject_ids=(coin_id,),
            fra_subject_ids=(request.instrument.id,),
            observed_at=observations[-1].observed_at,
            period_start=observations[0].observed_at,
            period_end=observations[-1].observed_at,
            timezone="UTC",
            currency=currency.code,
            content_hash=response.content_hash,
            request_fingerprint=response.request_fingerprint,
            usage_policy_id="coingecko-demo-local-evaluation-2026-07-19",
            required_attribution=self._descriptor.required_attribution,
            warnings=(
                "CoinGecko is an aggregator and does not provide exchange-authoritative prices",
                "CoinGecko Demo plan limits and attribution requirements apply",
            ),
            missing_fields=("published_at", "historical_availability", "vintage"),
        )

    def _coin_id(self, instrument: InstrumentRef) -> str:
        coin_id = instrument.alias_for("coingecko")
        if coin_id is None:
            raise CapabilityUnavailableError("instrument has no CoinGecko coin ID")
        return coin_id

    def _headers(self) -> dict[str, str] | None:
        return {"x-cg-demo-api-key": self._api_key} if self._api_key else None


def _market_observations(
    payload: Any, instrument_id: InstrumentId, currency: Currency
) -> tuple[MarketObservation, ...]:
    if not isinstance(payload, dict):
        raise ExternalDataInvalidError("CoinGecko history response must be an object")
    prices = _pairs(payload.get("prices"), "prices")
    market_caps = dict(_pairs(payload.get("market_caps"), "market_caps"))
    volumes = dict(_pairs(payload.get("total_volumes"), "total_volumes"))
    if set(market_caps) != {timestamp for timestamp, _value in prices} or set(volumes) != {
        timestamp for timestamp, _value in prices
    }:
        raise ExternalDataInvalidError("CoinGecko history arrays have inconsistent timestamps")
    return tuple(
        MarketObservation(
            instrument_id=instrument_id,
            observed_at=_unix_time(timestamp, milliseconds=True, field="market timestamp"),
            price=value,
            market_cap=market_caps[timestamp],
            volume=volumes[timestamp],
            currency=currency,
        )
        for timestamp, value in prices
    )


def _pairs(value: Any, field: str) -> tuple[tuple[int, Decimal], ...]:
    if not isinstance(value, list):
        raise ExternalDataInvalidError(f"CoinGecko {field} must be an array")
    result: list[tuple[int, Decimal]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], int):
            raise ExternalDataInvalidError(f"CoinGecko {field} contains an invalid pair")
        result.append((item[0], _decimal(item[1], field)))
    if [timestamp for timestamp, _item in result] != sorted(
        timestamp for timestamp, _item in result
    ):
        raise ExternalDataInvalidError(f"CoinGecko {field} timestamps are not chronological")
    return tuple(result)


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ExternalDataInvalidError(f"CoinGecko {field} is invalid") from error
    if not result.is_finite() or result < 0:
        raise ExternalDataInvalidError(f"CoinGecko {field} is invalid")
    return result


def _unix_time(value: Any, *, milliseconds: bool, field: str) -> datetime:
    if not isinstance(value, int) or value < 0:
        raise ExternalDataInvalidError(f"CoinGecko {field} is invalid")
    divisor = 1000 if milliseconds else 1
    try:
        return datetime.fromtimestamp(value / divisor, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise ExternalDataInvalidError(f"CoinGecko {field} is invalid") from error
