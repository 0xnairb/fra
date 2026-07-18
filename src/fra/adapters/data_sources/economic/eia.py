"""U.S. EIA API v2 physical energy-series adapter."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fra.adapters.data_sources.common.http import HttpClient, content_hash, request_fingerprint
from fra.adapters.data_sources.common.manifests import validate_source_manifest
from fra.domain.economic import (
    EconomicObservation,
    EconomicSeries,
    EconomicSeriesCapabilities,
    EconomicSeriesRequest,
)
from fra.domain.errors import ExternalDataInvalidError, PointInTimeUnavailableError
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor

BASE_URL = "https://api.eia.gov/v2/petroleum/stoc/wstk/data"


class EIAEnergyAdapter:
    def __init__(
        self,
        client: HttpClient,
        *,
        api_key: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        base_url: str = BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("EIA API key must not be empty")
        self._client = client
        self._api_key = api_key
        self._now = now
        self._base_url = base_url.rstrip("/")
        self._descriptor = validate_source_manifest(
            {
                "manifest_version": 1,
                "provider_id": "eia",
                "adapter_version": "1.0.0",
                "source_kinds": ["economic_series"],
                "authority_class": "official",
                "point_in_time_support": False,
                "allowed_usage_profiles": [
                    "local_personal_research",
                    "internal_research",
                    "commercial",
                ],
                "raw_retention": "metadata_only",
                "terms_url": "https://www.eia.gov/about/copyrights_reuse.php",
                "terms_reviewed_at": "2026-07-19",
                "independence_group": "eia",
                "geographies": ["US"],
                "frequencies": ["weekly"],
                "authentication_kind": "api_key",
                "credential_environment_names": ["EIA_API_KEY"],
                "normal_update_cadence": "weekly",
                "required_attribution": "U.S. Energy Information Administration",
            }
        )

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> EconomicSeriesCapabilities:
        return EconomicSeriesCapabilities(True, False, frozenset({"weekly"}))

    async def health(self) -> HealthStatus:
        await self._client.get(
            self._base_url,
            params={"api_key": self._api_key, "length": 1},
        )
        return HealthStatus(HealthState.HEALTHY, self._now(), "EIA API v2 reachable")

    async def observations(self, request: EconomicSeriesRequest) -> DataEnvelope[EconomicSeries]:
        if request.point_in_time_at is not None:
            raise PointInTimeUnavailableError("EIA API v2 does not expose historical vintages")
        offset = 0
        total = 1
        raw_pages: list[object] = []
        rows: list[dict[str, Any]] = []
        base_params: dict[str, str | int] = {
            "api_key": self._api_key,
            "frequency": "weekly",
            "data[0]": "value",
            "facets[series][]": request.series_id,
            "start": request.start_period,
            "end": request.end_period,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "length": request.page_size,
        }
        while offset < total:
            params = {**base_params, "offset": offset}
            response = await self._client.get(self._base_url, params=params)
            payload = response.json()
            raw_pages.append(payload)
            page_rows, total = _eia_page(payload)
            rows.extend(page_rows)
            offset += request.page_size
        observations = tuple(_eia_observation(row, request) for row in rows)
        title = (
            str(rows[0].get("series-description", request.series_id)) if rows else request.series_id
        )
        units = str(rows[0]["units"]) if rows and rows[0].get("units") else None
        retrieved = self._now()
        return DataEnvelope(
            EconomicSeries(request.series_id, request.geography, title, observations),
            self._descriptor,
            request.series_id,
            self._base_url,
            retrieved,
            retrieved,
            units=units,
            content_hash=content_hash(
                json.dumps(raw_pages, sort_keys=True, separators=(",", ":")).encode()
            ),
            request_fingerprint=request_fingerprint("GET", self._base_url, base_params),
            usage_policy_id="eia-copyright-reuse-2026-07-19",
            required_attribution=self._descriptor.required_attribution,
            warnings=("EIA current API values may be revised; no historical vintage is exposed",),
            missing_fields=("vintage", "revised_at"),
        )


def _eia_page(payload: object) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
        raise ExternalDataInvalidError("EIA response schema is invalid")
    response = payload["response"]
    data = response.get("data")
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ExternalDataInvalidError("EIA response data is invalid")
    try:
        total = int(response.get("total", len(data)))
    except (TypeError, ValueError) as error:
        raise ExternalDataInvalidError("EIA response total is invalid") from error
    return data, total


def _eia_observation(row: dict[str, Any], request: EconomicSeriesRequest) -> EconomicObservation:
    period = row.get("period")
    raw = row.get("value")
    if not isinstance(period, str):
        raise ExternalDataInvalidError("EIA observation period is invalid")
    try:
        value = None if raw is None else Decimal(str(raw))
    except InvalidOperation as error:
        raise ExternalDataInvalidError("EIA observation value is invalid") from error
    return EconomicObservation(
        request.series_id,
        request.geography,
        period,
        value,
        str(row["units"]) if row.get("units") else None,
    )
