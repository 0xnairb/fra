"""Conditional personal-research yfinance market-data fallback."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from importlib import import_module

from fra.adapters.data_sources.common.http import content_hash, request_fingerprint
from fra.adapters.data_sources.common.manifests import validate_source_manifest
from fra.domain.errors import ExternalDataInvalidError, PointInTimeUnavailableError
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

Download = Callable[..., object]
_INSTRUMENTS = {
    "SPY": InstrumentRef(
        InstrumentId("fund:us:SPY"),
        AssetClass.FUND,
        "SPDR S&P 500 ETF Trust",
        Currency("USD"),
        (ProviderAlias("yfinance", "SPY"),),
        "SPY",
    ),
    "BND": InstrumentRef(
        InstrumentId("fund:us:BND"),
        AssetClass.FIXED_INCOME,
        "Vanguard Total Bond Market ETF",
        Currency("USD"),
        (ProviderAlias("yfinance", "BND"),),
        "BND",
    ),
    "GLD": InstrumentRef(
        InstrumentId("fund:us:GLD"),
        AssetClass.COMMODITY,
        "SPDR Gold Shares",
        Currency("USD"),
        (ProviderAlias("yfinance", "GLD"),),
        "GLD",
    ),
}


class YFinanceMarketDataAdapter:
    def __init__(
        self,
        *,
        download: Download | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._download = download or _default_download
        self._now = now
        self._descriptor = validate_source_manifest(
            {
                "manifest_version": 1,
                "provider_id": "yfinance",
                "adapter_version": "1.0.0",
                "source_kinds": ["market_data"],
                "authority_class": "aggregator",
                "point_in_time_support": False,
                "allowed_usage_profiles": ["local_personal_research"],
                "raw_retention": "metadata_only",
                "terms_url": "https://ranaroussi.github.io/yfinance/index.html",
                "terms_reviewed_at": "2026-07-19",
                "independence_group": "yahoo-finance-unofficial",
                "markets": ["US"],
                "frequencies": ["daily", "weekly", "monthly"],
                "normal_update_cadence": "best-effort",
                "required_attribution": "Unofficial yfinance/Yahoo Finance data; personal use only",
                "experimental": True,
            }
        )

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> MarketDataCapabilities:
        return MarketDataCapabilities(True, True, frozenset({"daily", "weekly", "monthly"}))

    async def health(self) -> HealthStatus:
        await asyncio.to_thread(
            self._download,
            "SPY",
            period="5d",
            interval="1d",
            auto_adjust=True,
            actions=False,
            progress=False,
            threads=False,
            multi_level_index=False,
            timeout=10,
        )
        return HealthStatus(HealthState.HEALTHY, self._now(), "yfinance fallback reachable")

    async def resolve_instrument(self, query: InstrumentQuery) -> tuple[InstrumentMatch, ...]:
        text = query.text.strip().upper()
        return tuple(
            InstrumentMatch(instrument, Decimal(1) if text == symbol else Decimal("0.8"))
            for symbol, instrument in _INSTRUMENTS.items()
            if text == symbol or text in instrument.name.upper()
        )

    async def quote(self, instrument: InstrumentRef) -> DataEnvelope[MarketQuote]:
        now = self._now()
        history = await self.history(
            HistoryRequest(instrument, now - timedelta(days=10), now, "daily")
        )
        latest = history.value.observations[-1]
        return DataEnvelope(
            MarketQuote(instrument.id, latest.price, latest.currency, latest.observed_at),
            self._descriptor,
            history.provider_record_id,
            history.source,
            history.available_at,
            history.retrieved_at,
            provider_subject_ids=history.provider_subject_ids,
            fra_subject_ids=history.fra_subject_ids,
            observed_at=latest.observed_at,
            currency=latest.currency.code,
            content_hash=history.content_hash,
            request_fingerprint=history.request_fingerprint,
            usage_policy_id=history.usage_policy_id,
            required_attribution=history.required_attribution,
            warnings=history.warnings,
        )

    async def history(self, request: HistoryRequest) -> DataEnvelope[MarketSeries]:
        if request.point_in_time_at is not None:
            raise PointInTimeUnavailableError("yfinance does not expose historical vintages")
        symbol = request.instrument.alias_for("yfinance")
        if symbol is None:
            raise ExternalDataInvalidError("instrument is missing its yfinance ticker alias")
        interval = {"daily": "1d", "weekly": "1wk", "monthly": "1mo"}.get(request.resolution)
        if interval is None:
            raise ExternalDataInvalidError("yfinance history resolution is unsupported")
        kwargs = {
            "start": request.start_at.date().isoformat(),
            "end": (request.end_at + timedelta(days=1)).date().isoformat(),
            "interval": interval,
            "auto_adjust": True,
            "actions": False,
            "progress": False,
            "threads": False,
            "multi_level_index": False,
            "timeout": 20,
        }
        frame = await asyncio.to_thread(self._download, symbol, **kwargs)
        records = _records(frame)
        currency = request.instrument.currency or Currency("USD")
        observations = tuple(
            _observation(request.instrument, record, currency) for record in records
        )
        if not observations:
            raise ExternalDataInvalidError("yfinance returned no usable history")
        retrieved = self._now()
        fingerprint_params: dict[str, str | int] = {
            "ticker": symbol,
            "start": str(kwargs["start"]),
            "end": str(kwargs["end"]),
            "interval": interval,
        }
        return DataEnvelope(
            MarketSeries(request.instrument.id, observations, currency),
            self._descriptor,
            symbol,
            f"https://finance.yahoo.com/quote/{symbol}/history",
            retrieved,
            retrieved,
            provider_subject_ids=(symbol,),
            fra_subject_ids=(request.instrument.id,),
            observed_at=observations[-1].observed_at,
            period_start=request.start_at,
            period_end=request.end_at,
            currency=currency.code,
            content_hash=content_hash(repr(records).encode()),
            request_fingerprint=request_fingerprint(
                "GET", "https://query1.finance.yahoo.com/v8/finance/chart", fingerprint_params
            ),
            usage_policy_id="yfinance-personal-use-2026-07-19",
            required_attribution=self._descriptor.required_attribution,
            warnings=(
                "Unofficial best-effort fallback; Yahoo Finance data is intended for personal use",
                "Adjusted prices may change when provider corrections or corporate actions update",
            ),
            missing_fields=("published_at", "vintage", "revision"),
        )


def _default_download(*args: object, **kwargs: object) -> object:
    module = import_module("yfinance")
    function = module.download
    return function(*args, **kwargs)


def _records(frame: object) -> list[dict[str, object]]:
    if isinstance(frame, list) and all(isinstance(item, dict) for item in frame):
        return frame
    reset_index = getattr(frame, "reset_index", None)
    if not callable(reset_index):
        raise ExternalDataInvalidError("yfinance returned an unsupported table")
    table = reset_index()
    to_dict = getattr(table, "to_dict", None)
    if not callable(to_dict):
        raise ExternalDataInvalidError("yfinance returned an unsupported table")
    records = to_dict(orient="records")
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise ExternalDataInvalidError("yfinance table records are invalid")
    return records


def _observation(
    instrument: InstrumentRef, record: dict[str, object], currency: Currency
) -> MarketObservation:
    raw_time = record.get("Date", record.get("Datetime"))
    if isinstance(raw_time, datetime):
        observed_at = raw_time
    elif isinstance(raw_time, str):
        observed_at = datetime.fromisoformat(raw_time)
    else:
        to_datetime = getattr(raw_time, "to_pydatetime", None)
        if not callable(to_datetime):
            raise ExternalDataInvalidError("yfinance observation date is invalid")
        observed_at = to_datetime()
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    try:
        price = Decimal(str(record["Close"]))
        volume = None if record.get("Volume") is None else Decimal(str(record["Volume"]))
    except (KeyError, InvalidOperation) as error:
        raise ExternalDataInvalidError("yfinance observation values are invalid") from error
    return MarketObservation(instrument.id, observed_at, price, None, volume, currency)
