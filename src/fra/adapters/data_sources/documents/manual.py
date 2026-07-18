"""Configured official/manual URL ingestion."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from fra.adapters.data_sources.common.http import (
    HttpClient,
    content_hash,
    request_fingerprint,
)
from fra.adapters.data_sources.common.manifests import validate_source_manifest
from fra.domain.documents import Document, DocumentCapabilities, DocumentQuery, DocumentRef
from fra.domain.errors import CapabilityUnavailableError, PointInTimeUnavailableError
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor


@dataclass(frozen=True, slots=True)
class ManualDocument:
    provider_record_id: str
    title: str
    url: str
    published_at: datetime | None = None
    updated_at: datetime | None = None
    corrects_provider_record_id: str | None = None
    withdrawn: bool = False


class ManualDocumentAdapter:
    def __init__(
        self,
        *,
        documents: tuple[ManualDocument, ...],
        client: HttpClient,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        provider_id: str = "manual_documents",
        terms_url: str = "https://example.invalid/manual-source-terms",
        terms_reviewed_at: date = date(1970, 1, 1),
        allowed_usage_profiles: tuple[str, ...] = (
            "local_personal_research",
            "internal_research",
            "commercial",
        ),
    ) -> None:
        self._documents = {item.provider_record_id: item for item in documents}
        self._client = client
        self._now = now
        self._point_in_time_support = all(item.published_at is not None for item in documents)
        self._descriptor = validate_source_manifest(
            {
                "manifest_version": 1,
                "provider_id": provider_id,
                "adapter_version": "1.0.0",
                "source_kinds": ["document"],
                "authority_class": "official",
                "point_in_time_support": self._point_in_time_support,
                "allowed_usage_profiles": list(allowed_usage_profiles),
                "raw_retention": "metadata_only",
                "terms_url": terms_url,
                "terms_reviewed_at": terms_reviewed_at,
                "independence_group": provider_id,
                "normal_update_cadence": "manual",
            }
        )

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> DocumentCapabilities:
        return DocumentCapabilities(
            search=True,
            fetch=True,
            point_in_time=self._point_in_time_support,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            HealthState.HEALTHY,
            self._now(),
            f"{len(self._documents)} manual documents configured",
        )

    async def search(self, query: DocumentQuery) -> DataEnvelope[tuple[DocumentRef, ...]]:
        if query.point_in_time_at is not None and not self._point_in_time_support:
            raise PointInTimeUnavailableError(
                "manual documents without publication times cannot prove a historical cutoff"
            )
        matches = tuple(
            DocumentRef(
                item.provider_record_id,
                item.title,
                item.url,
                item.published_at,
                item.updated_at,
                item.corrects_provider_record_id,
                item.withdrawn,
            )
            for item in sorted(self._documents.values(), key=lambda value: value.provider_record_id)
            if query.text.casefold() in item.title.casefold()
            and (
                query.published_after is None
                or item.published_at is None
                or item.published_at >= query.published_after
            )
            and (
                query.published_before is None
                or item.published_at is None
                or item.published_at <= query.published_before
            )
            and (
                query.point_in_time_at is None
                or item.published_at is None
                or item.published_at <= query.point_in_time_at
            )
        )
        retrieved = self._now()
        payload = "\n".join(item.provider_record_id for item in matches).encode()
        return DataEnvelope(
            value=matches,
            descriptor=self._descriptor,
            provider_record_id="manual-index",
            source="configured manual documents",
            available_at=retrieved,
            retrieved_at=retrieved,
            content_hash=content_hash(payload),
            request_fingerprint=request_fingerprint(
                "SEARCH", "manual://documents", {"q": query.text}
            ),
            usage_policy_id=f"{self._descriptor.provider_id}-manifest-v1",
            required_attribution=self._descriptor.required_attribution,
        )

    async def fetch(self, reference: DocumentRef) -> DataEnvelope[Document]:
        try:
            configured = self._documents[reference.provider_record_id]
        except KeyError as error:
            raise CapabilityUnavailableError(
                f"manual document {reference.provider_record_id} is not configured"
            ) from error
        response = await self._client.get(configured.url)
        retrieved = self._now()
        try:
            content = response.body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CapabilityUnavailableError("manual document is not UTF-8 text") from error
        published = configured.published_at
        return DataEnvelope(
            value=Document(
                configured.provider_record_id,
                configured.title,
                configured.url,
                content,
                published,
                configured.updated_at,
                configured.corrects_provider_record_id,
                configured.withdrawn,
            ),
            descriptor=self._descriptor,
            provider_record_id=configured.provider_record_id,
            source=configured.url,
            published_at=published,
            revised_at=configured.updated_at,
            available_at=configured.updated_at or published or retrieved,
            retrieved_at=retrieved,
            content_hash=response.content_hash,
            request_fingerprint=response.request_fingerprint,
            usage_policy_id=f"{self._descriptor.provider_id}-manifest-v1",
            required_attribution=self._descriptor.required_attribution,
        )
