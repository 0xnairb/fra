"""World Bank Indicators API adapter with deterministic pagination."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from urllib.parse import quote

from fra.adapters.data_sources.common.http import (
    HttpClient,
    content_hash,
    request_fingerprint,
)
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

BASE_URL = "https://api.worldbank.org/v2"


class WorldBankIndicatorsAdapter:
    def __init__(
        self,
        client: HttpClient,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        base_url: str = BASE_URL,
    ) -> None:
        self._client = client
        self._now = now
        self._base_url = base_url.rstrip("/")
        self._descriptor = validate_source_manifest(
            {
                "manifest_version": 1,
                "provider_id": "world_bank_indicators",
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
                "terms_url": "https://www.worldbank.org/en/about/legal/terms-of-use-for-world-bank-websites",
                "terms_reviewed_at": "2026-07-18",
                "independence_group": "world-bank",
                "geographies": ["GLOBAL"],
                "frequencies": ["annual"],
                "normal_update_cadence": "provider-defined",
                "maximum_expected_age_seconds": 31622400,
                "required_attribution": "World Bank Indicators API",
            }
        )

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> EconomicSeriesCapabilities:
        return EconomicSeriesCapabilities(
            observations=True,
            vintages=False,
            frequencies=frozenset({"annual"}),
        )

    async def health(self) -> HealthStatus:
        await self._client.get(
            f"{self._base_url}/country",
            params={"format": "json", "per_page": 1, "page": 1},
        )
        return HealthStatus(HealthState.HEALTHY, self._now(), "World Bank API reachable")

    async def observations(self, request: EconomicSeriesRequest) -> DataEnvelope[EconomicSeries]:
        if request.point_in_time_at is not None:
            raise PointInTimeUnavailableError(
                "World Bank Indicators does not expose historical vintages"
            )
        url = (
            f"{self._base_url}/country/{quote(request.geography, safe='')}"
            f"/indicator/{quote(request.series_id, safe='')}"
        )
        base_params: dict[str, str | int] = {
            "format": "json",
            "date": f"{request.start_period}:{request.end_period}",
            "per_page": request.page_size,
        }
        page = 1
        pages = 1
        rows: list[dict[str, Any]] = []
        raw_pages: list[Any] = []
        while page <= pages:
            response = await self._client.get(url, params={**base_params, "page": page})
            payload = response.json()
            raw_pages.append(payload)
            metadata, values = _page(payload)
            pages = _positive_int(metadata.get("pages"), "pages")
            if _positive_int(metadata.get("page"), "page") != page:
                raise ExternalDataInvalidError("World Bank pagination returned the wrong page")
            rows.extend(values)
            page += 1
        observations = tuple(
            sorted((_observation(row) for row in rows), key=lambda item: item.period)
        )
        title = request.series_id
        units: str | None = None
        if rows:
            indicator = rows[0].get("indicator")
            if isinstance(indicator, dict) and isinstance(indicator.get("value"), str):
                title = indicator["value"]
            units_value = rows[0].get("unit")
            units = units_value if isinstance(units_value, str) and units_value else None
        retrieved = self._now()
        series = EconomicSeries(request.series_id, request.geography, title, observations)
        return DataEnvelope(
            value=series,
            descriptor=self._descriptor,
            provider_record_id=f"{request.geography}:{request.series_id}",
            source=url,
            available_at=retrieved,
            retrieved_at=retrieved,
            period_start=_period_time(request.start_period, end=False),
            period_end=_period_time(request.end_period, end=True),
            units=units,
            content_hash=content_hash(
                json.dumps(raw_pages, sort_keys=True, separators=(",", ":")).encode()
            ),
            request_fingerprint=request_fingerprint("GET", url, base_params),
            usage_policy_id="world-bank-indicators-terms-2026-07-18",
            required_attribution=self._descriptor.required_attribution,
            warnings=("World Bank Indicators does not provide historical vintages",),
            missing_fields=("published_at", "revised_at", "vintage"),
        )


def _page(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if (
        not isinstance(payload, list)
        or len(payload) != 2
        or not isinstance(payload[0], dict)
        or not isinstance(payload[1], list)
        or any(not isinstance(row, dict) for row in payload[1])
    ):
        raise ExternalDataInvalidError("World Bank response has an invalid page schema")
    return payload[0], payload[1]


def _positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or value < 1:
        raise ExternalDataInvalidError(f"World Bank pagination {field} is invalid")
    return value


def _observation(row: dict[str, Any]) -> EconomicObservation:
    indicator = row.get("indicator")
    country = row.get("country")
    if not isinstance(indicator, dict) or not isinstance(country, dict):
        raise ExternalDataInvalidError("World Bank observation identifiers are invalid")
    series_id = indicator.get("id")
    geography = row.get("countryiso3code") or country.get("id")
    period = row.get("date")
    if not all(isinstance(value, str) and value for value in (series_id, geography, period)):
        raise ExternalDataInvalidError("World Bank observation identity is incomplete")
    raw_value = row.get("value")
    try:
        value = None if raw_value is None else Decimal(str(raw_value))
    except InvalidOperation as error:
        raise ExternalDataInvalidError("World Bank observation value is invalid") from error
    units = row.get("unit")
    status = row.get("obs_status")
    return EconomicObservation(
        series_id=cast(str, series_id),
        geography=cast(str, geography),
        period=cast(str, period),
        value=value,
        units=units if isinstance(units, str) and units else None,
        status=status if isinstance(status, str) and status else None,
    )


def _period_time(period: str, *, end: bool) -> datetime | None:
    if not period.isdigit() or len(period) != 4:
        return None
    return datetime(
        int(period),
        12 if end else 1,
        31 if end else 1,
        23 if end else 0,
        59 if end else 0,
        59 if end else 0,
        tzinfo=UTC,
    )
