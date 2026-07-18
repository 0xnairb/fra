"""FRED/ALFRED observation adapter with explicit real-time vintages."""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from fra.adapters.data_sources.common.http import HttpClient, content_hash, request_fingerprint
from fra.adapters.data_sources.common.manifests import validate_source_manifest
from fra.domain.economic import (
    EconomicObservation,
    EconomicSeries,
    EconomicSeriesCapabilities,
    EconomicSeriesRequest,
)
from fra.domain.errors import ExternalDataInvalidError, LookAheadEvidenceError
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FREDVintageAdapter:
    def __init__(
        self,
        client: HttpClient,
        *,
        api_key: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        base_url: str = BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("FRED API key must not be empty")
        self._client = client
        self._api_key = api_key
        self._now = now
        self._base_url = base_url
        self._descriptor = validate_source_manifest(
            {
                "manifest_version": 1,
                "provider_id": "fred_alfred",
                "adapter_version": "1.0.0",
                "source_kinds": ["economic_series"],
                "authority_class": "official",
                "point_in_time_support": True,
                "allowed_usage_profiles": [
                    "local_personal_research",
                    "internal_research",
                    "commercial",
                ],
                "raw_retention": "metadata_only",
                "terms_url": "https://fred.stlouisfed.org/docs/api/terms_of_use.html",
                "terms_reviewed_at": "2026-07-19",
                "independence_group": "federal-reserve-st-louis",
                "geographies": ["US"],
                "frequencies": ["daily", "weekly", "monthly", "quarterly", "annual"],
                "authentication_kind": "api_key",
                "credential_environment_names": ["FRED_API_KEY"],
                "required_attribution": "Federal Reserve Bank of St. Louis FRED/ALFRED",
            }
        )

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> EconomicSeriesCapabilities:
        return EconomicSeriesCapabilities(
            True, True, frozenset({"daily", "weekly", "monthly", "quarterly", "annual"})
        )

    async def health(self) -> HealthStatus:
        await self._client.get(
            self._base_url,
            params={
                "api_key": self._api_key,
                "file_type": "json",
                "series_id": "DCOILWTICO",
                "limit": 1,
            },
        )
        return HealthStatus(HealthState.HEALTHY, self._now(), "FRED API reachable")

    async def observations(self, request: EconomicSeriesRequest) -> DataEnvelope[EconomicSeries]:
        cutoff = request.point_in_time_at
        vintage = (cutoff or self._now()).date().isoformat()
        params: dict[str, str | int] = {
            "api_key": self._api_key,
            "file_type": "json",
            "series_id": request.series_id,
            "realtime_start": vintage,
            "realtime_end": vintage,
            "observation_start": request.start_period,
            "observation_end": request.end_period,
            "limit": min(request.page_size, 100000),
            "offset": 0,
            "sort_order": "asc",
        }
        response = await self._client.get(self._base_url, params=params)
        payload = response.json()
        observations = _fred_observations(payload, request, date.fromisoformat(vintage))
        retrieved = self._now()
        available = cutoff or retrieved
        return DataEnvelope(
            EconomicSeries(request.series_id, request.geography, request.series_id, observations),
            self._descriptor,
            f"{request.series_id}:{vintage}",
            self._base_url,
            available,
            retrieved,
            historical_cutoff_at=cutoff,
            period_start=_date_time(request.start_period),
            period_end=_date_time(request.end_period),
            vintage=vintage,
            content_hash=content_hash(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ),
            request_fingerprint=request_fingerprint("GET", self._base_url, params),
            usage_policy_id="fred-api-terms-2026-07-19",
            required_attribution=self._descriptor.required_attribution,
        )


def _fred_observations(
    payload: object, request: EconomicSeriesRequest, vintage: date
) -> tuple[EconomicObservation, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
        raise ExternalDataInvalidError("FRED response schema is invalid")
    result: list[EconomicObservation] = []
    for row in payload["observations"]:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str):
            raise ExternalDataInvalidError("FRED observation schema is invalid")
        realtime_start = row.get("realtime_start")
        if isinstance(realtime_start, str) and date.fromisoformat(realtime_start) > vintage:
            raise LookAheadEvidenceError("FRED returned an observation after the requested vintage")
        raw = row.get("value")
        try:
            value = None if raw in {None, "."} else Decimal(str(raw))
        except InvalidOperation as error:
            raise ExternalDataInvalidError("FRED observation value is invalid") from error
        result.append(
            EconomicObservation(
                request.series_id,
                request.geography,
                row["date"],
                value,
                str(payload.get("units", "lin")),
            )
        )
    return tuple(result)


def _date_time(value: str) -> datetime | None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)
