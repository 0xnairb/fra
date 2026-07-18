"""SEC EDGAR submissions and selected XBRL company-facts adapter."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.common.manifests import validate_source_manifest
from fra.domain.documents import Document, DocumentCapabilities, DocumentQuery, DocumentRef
from fra.domain.errors import ExternalDataInvalidError
from fra.domain.regulatory import CompanyFact
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor

BASE_URL = "https://data.sec.gov"


class SECEdgarAdapter:
    def __init__(
        self,
        client: HttpClient,
        *,
        user_agent: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        base_url: str = BASE_URL,
    ) -> None:
        if "@" not in user_agent or len(user_agent.split()) < 2:
            raise ValueError("SEC User-Agent must identify an organization and contact email")
        self._client = client
        self._headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        self._now = now
        self._base_url = base_url.rstrip("/")
        self._descriptor = validate_source_manifest(
            {
                "manifest_version": 1,
                "provider_id": "sec_edgar",
                "adapter_version": "1.0.0",
                "source_kinds": ["document"],
                "authority_class": "regulated",
                "point_in_time_support": True,
                "allowed_usage_profiles": [
                    "local_personal_research",
                    "internal_research",
                    "commercial",
                ],
                "raw_retention": "permitted",
                "terms_url": "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
                "terms_reviewed_at": "2026-07-19",
                "independence_group": "sec-edgar",
                "geographies": ["US"],
                "normal_update_cadence": "real-time",
                "quota_description": "SEC fair-access maximum 10 requests per second",
                "required_attribution": "U.S. Securities and Exchange Commission EDGAR",
            }
        )

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> DocumentCapabilities:
        return DocumentCapabilities(True, True, True)

    async def health(self) -> HealthStatus:
        await self._client.get(
            f"{self._base_url}/submissions/CIK0000320193.json", headers=self._headers
        )
        return HealthStatus(HealthState.HEALTHY, self._now(), "SEC EDGAR data API reachable")

    async def search(self, query: DocumentQuery) -> DataEnvelope[tuple[DocumentRef, ...]]:
        cik = _cik(query.text)
        url = f"{self._base_url}/submissions/CIK{cik}.json"
        response = await self._client.get(url, headers=self._headers)
        payload = response.json()
        refs = _filing_refs(payload, cik, query)
        retrieved = self._now()
        available = query.point_in_time_at or retrieved
        return DataEnvelope(
            refs,
            self._descriptor,
            f"CIK{cik}:submissions",
            url,
            available,
            retrieved,
            historical_cutoff_at=query.point_in_time_at,
            content_hash=response.content_hash,
            request_fingerprint=response.request_fingerprint,
            usage_policy_id="sec-fair-access-2026-07-19",
            required_attribution=self._descriptor.required_attribution,
        )

    async def fetch(self, reference: DocumentRef) -> DataEnvelope[Document]:
        response = await self._client.get(reference.source, headers=self._headers)
        try:
            body = response.body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ExternalDataInvalidError("SEC filing document is not UTF-8") from error
        retrieved = self._now()
        return DataEnvelope(
            Document(
                reference.provider_record_id,
                reference.title,
                reference.source,
                body,
                reference.published_at,
                reference.updated_at,
            ),
            self._descriptor,
            reference.provider_record_id,
            reference.source,
            reference.published_at or retrieved,
            retrieved,
            published_at=reference.published_at,
            content_hash=response.content_hash,
            request_fingerprint=response.request_fingerprint,
            usage_policy_id="sec-fair-access-2026-07-19",
            required_attribution=self._descriptor.required_attribution,
        )

    async def selected_facts(
        self,
        cik: str,
        concepts: tuple[str, ...],
        *,
        point_in_time_at: datetime,
    ) -> tuple[CompanyFact, ...]:
        normalized = _cik(cik)
        url = f"{self._base_url}/api/xbrl/companyfacts/CIK{normalized}.json"
        response = await self._client.get(url, headers=self._headers)
        return _company_facts(response.json(), normalized, concepts, point_in_time_at)


def _cik(value: str) -> str:
    digits = value.upper().removeprefix("CIK").strip().lstrip("0") or "0"
    if not digits.isdigit() or len(digits) > 10:
        raise ExternalDataInvalidError("SEC CIK must contain at most ten digits")
    return digits.zfill(10)


def _filing_refs(payload: object, cik: str, query: DocumentQuery) -> tuple[DocumentRef, ...]:
    if not isinstance(payload, dict):
        raise ExternalDataInvalidError("SEC submissions schema is invalid")
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else None
    if not isinstance(recent, dict):
        raise ExternalDataInvalidError("SEC recent filings schema is invalid")
    fields = ("accessionNumber", "filingDate", "form", "primaryDocument")
    columns = [recent.get(field) for field in fields]
    if any(not isinstance(column, list) for column in columns):
        raise ExternalDataInvalidError("SEC recent filing columns are invalid")
    result: list[DocumentRef] = []
    for accession, filed, form, primary in zip(*columns, strict=True):
        if not all(isinstance(item, str) and item for item in (accession, filed, form, primary)):
            raise ExternalDataInvalidError("SEC recent filing row is invalid")
        published = datetime.combine(date.fromisoformat(filed), time(), UTC)
        if query.published_after and published < query.published_after:
            continue
        if query.published_before and published > query.published_before:
            continue
        if query.point_in_time_at and published > query.point_in_time_at:
            continue
        accession_path = accession.replace("-", "")
        source = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{primary}"
        result.append(DocumentRef(accession, f"{form} filed {filed}", source, published))
    return tuple(result)


def _company_facts(
    payload: object,
    cik: str,
    concepts: tuple[str, ...],
    cutoff: datetime,
) -> tuple[CompanyFact, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("facts"), dict):
        raise ExternalDataInvalidError("SEC company-facts schema is invalid")
    entity_name = payload.get("entityName")
    if not isinstance(entity_name, str):
        raise ExternalDataInvalidError("SEC company-facts entity name is invalid")
    facts = payload["facts"].get("us-gaap", {})
    if not isinstance(facts, dict):
        raise ExternalDataInvalidError("SEC us-gaap facts schema is invalid")
    result: list[CompanyFact] = []
    for concept in concepts:
        record = facts.get(concept)
        if not isinstance(record, dict) or not isinstance(record.get("units"), dict):
            continue
        label = record.get("label")
        if not isinstance(label, str):
            continue
        for unit, rows in record["units"].items():
            if not isinstance(unit, str) or not isinstance(rows, list):
                continue
            eligible = [row for row in rows if _fact_is_eligible(row, cutoff)]
            if not eligible:
                continue
            row = max(eligible, key=lambda item: str(item.get("filed", "")))
            try:
                result.append(_company_fact(cik, entity_name, concept, label, unit, row))
            except (InvalidOperation, TypeError, ValueError) as error:
                raise ExternalDataInvalidError("SEC company fact value is invalid") from error
    return tuple(result)


def _fact_is_eligible(value: object, cutoff: datetime) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("filed"), str):
        return False
    return date.fromisoformat(value["filed"]) <= cutoff.date()


def _company_fact(
    cik: str,
    entity_name: str,
    concept: str,
    label: str,
    unit: str,
    row: dict[str, Any],
) -> CompanyFact:
    filed = date.fromisoformat(str(row["filed"]))
    start = date.fromisoformat(str(row["start"])) if row.get("start") else None
    return CompanyFact(
        cik,
        entity_name,
        "us-gaap",
        concept,
        label,
        unit,
        Decimal(str(row["val"])),
        start,
        date.fromisoformat(str(row["end"])),
        datetime.combine(filed, time(), UTC),
        str(row["form"]),
        str(row["accn"]),
    )
