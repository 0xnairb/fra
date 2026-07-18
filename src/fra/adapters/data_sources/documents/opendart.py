"""OpenDART disclosure-search adapter with Korean corporation identifiers."""

from collections.abc import Callable
from datetime import UTC, datetime, time

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.common.manifests import validate_source_manifest
from fra.domain.documents import Document, DocumentCapabilities, DocumentQuery, DocumentRef
from fra.domain.errors import (
    AuthenticationRequiredError,
    CapabilityUnsupportedError,
    ExternalDataInvalidError,
    SourceQuotaExceededError,
)
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor

BASE_URL = "https://engopendart.fss.or.kr/engapi"


class OpenDartAdapter:
    def __init__(
        self,
        client: HttpClient,
        *,
        api_key: str,
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
                "provider_id": "opendart",
                "adapter_version": "1.0.0",
                "source_kinds": ["document"],
                "authority_class": "regulated",
                "point_in_time_support": True,
                "allowed_usage_profiles": [
                    "local_personal_research",
                    "internal_research",
                    "commercial",
                ],
                "raw_retention": "metadata_only",
                "terms_url": "https://engopendart.fss.or.kr/guide/detail.do?apiGrpCd=DE001&apiId=AE00001",
                "terms_reviewed_at": "2026-07-19",
                "independence_group": "fss-opendart",
                "geographies": ["KR"],
                "authentication_kind": "api_key",
                "credential_environment_names": ["OPENDART_API_KEY"],
                "quota_description": "status 020 indicates the configured call limit was exceeded",
                "normal_update_cadence": "filing-time",
                "required_attribution": "Financial Supervisory Service OpenDART",
            }
        )

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> DocumentCapabilities:
        return DocumentCapabilities(True, False, True)

    async def health(self) -> HealthStatus:
        response = await self._client.get(
            f"{self._base_url}/company.json",
            params={"crtfc_key": self._api_key, "corp_code": "00126380"},
        )
        _check_status(response.json(), allow_empty=False)
        return HealthStatus(HealthState.HEALTHY, self._now(), "OpenDART API reachable")

    async def search(self, query: DocumentQuery) -> DataEnvelope[tuple[DocumentRef, ...]]:
        corp_code = _corp_code(query.text)
        params: dict[str, str | int] = {
            "crtfc_key": self._api_key,
            "corp_code": corp_code,
            "page_no": 1,
            "page_count": 100,
            "sort": "date",
            "sort_mth": "desc",
        }
        if query.published_after:
            params["bgn_de"] = query.published_after.strftime("%Y%m%d")
        if query.published_before:
            params["end_de"] = query.published_before.strftime("%Y%m%d")
        if query.point_in_time_at:
            params["end_de"] = query.point_in_time_at.strftime("%Y%m%d")
        url = f"{self._base_url}/list.json"
        response = await self._client.get(url, params=params)
        payload = response.json()
        if _check_status(payload, allow_empty=True) == "013":
            rows: object = []
        else:
            rows = payload.get("list") if isinstance(payload, dict) else None
        references = _references(rows, query)
        retrieved = self._now()
        return DataEnvelope(
            references,
            self._descriptor,
            f"{corp_code}:disclosures",
            url,
            query.point_in_time_at or retrieved,
            retrieved,
            historical_cutoff_at=query.point_in_time_at,
            provider_subject_ids=(corp_code,),
            published_at=max(
                (item.published_at for item in references if item.published_at is not None),
                default=None,
            ),
            content_hash=response.content_hash,
            request_fingerprint=response.request_fingerprint,
            usage_policy_id="opendart-api-2026-07-19",
            required_attribution=self._descriptor.required_attribution,
        )

    async def fetch(self, reference: DocumentRef) -> DataEnvelope[Document]:
        del reference
        raise CapabilityUnsupportedError(
            "OpenDART original-document ZIP fetch is not enabled in this regional slice"
        )


def _corp_code(value: str) -> str:
    normalized = value.strip()
    if len(normalized) != 8 or not normalized.isdigit():
        raise ExternalDataInvalidError("OpenDART corporation code must contain eight digits")
    return normalized


def _check_status(payload: object, *, allow_empty: bool) -> str:
    if not isinstance(payload, dict):
        raise ExternalDataInvalidError("OpenDART response schema is invalid")
    status_value = payload.get("status")
    if not isinstance(status_value, str):
        raise ExternalDataInvalidError("OpenDART response schema is invalid")
    status = status_value
    if status == "000" or (allow_empty and status == "013"):
        return status
    message = str(payload.get("message", "OpenDART request failed"))
    if status in {"010", "011", "012", "101", "901"}:
        raise AuthenticationRequiredError(f"OpenDART authentication failed ({status}): {message}")
    if status == "020":
        raise SourceQuotaExceededError(f"OpenDART call limit exceeded: {message}")
    raise ExternalDataInvalidError(f"OpenDART returned status {status}: {message}")


def _references(rows: object, query: DocumentQuery) -> tuple[DocumentRef, ...]:
    if not isinstance(rows, list):
        raise ExternalDataInvalidError("OpenDART disclosure list is invalid")
    result: list[DocumentRef] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ExternalDataInvalidError("OpenDART disclosure row is invalid")
        try:
            receipt = str(row["rcept_no"])
            title = str(row["report_nm"])
            filed = datetime.combine(
                datetime.strptime(str(row["rcept_dt"]), "%Y%m%d").date(), time(), UTC
            )
        except (KeyError, ValueError) as error:
            raise ExternalDataInvalidError("OpenDART disclosure fields are invalid") from error
        if len(receipt) != 14 or not receipt.isdigit() or not title.strip():
            raise ExternalDataInvalidError("OpenDART disclosure identity is invalid")
        if query.point_in_time_at and filed > query.point_in_time_at:
            continue
        result.append(
            DocumentRef(
                receipt,
                title,
                f"https://englishdart.fss.or.kr/dsbh001/main.do?rcpNo={receipt}",
                filed,
            )
        )
    return tuple(result)
