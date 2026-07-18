"""Fixture-backed normalized document adapter."""

from datetime import UTC, date, datetime

from fra.domain.documents import Document, DocumentCapabilities, DocumentQuery, DocumentRef
from fra.domain.errors import CapabilityUnavailableError
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)
from fra.ports.documents import DocumentProvider


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        provider_id="fake_documents",
        adapter_version="1.0.0",
        source_kinds=frozenset({SourceKind.DOCUMENT}),
        authority_class=AuthorityClass.OFFICIAL,
        point_in_time_support=True,
        allowed_usage_profiles=frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
        raw_retention=RawRetentionPolicy.PERMITTED,
        terms_url="https://example.test/fake-documents/terms",
        terms_reviewed_at=date(2000, 1, 1),
        independence_group="fake-documents",
    )


class FakeDocumentProvider(DocumentProvider):
    def __init__(
        self,
        *,
        search_result: DataEnvelope[tuple[DocumentRef, ...]] | None = None,
        documents: tuple[tuple[str, DataEnvelope[Document]], ...] = (),
        now: datetime = datetime(2000, 1, 1, tzinfo=UTC),
    ) -> None:
        self._search_result = search_result
        self._documents = dict(documents)
        self._now = now

    def descriptor(self) -> SourceDescriptor:
        return _descriptor()

    def capabilities(self) -> DocumentCapabilities:
        return DocumentCapabilities(search=True, fetch=True, point_in_time=True)

    async def health(self) -> HealthStatus:
        return HealthStatus(HealthState.HEALTHY, self._now, "fake documents ready")

    async def search(self, query: DocumentQuery) -> DataEnvelope[tuple[DocumentRef, ...]]:
        del query
        if self._search_result is None:
            raise CapabilityUnavailableError("no fake document search result")
        return self._search_result

    async def fetch(self, reference: DocumentRef) -> DataEnvelope[Document]:
        try:
            return self._documents[reference.provider_record_id]
        except KeyError as error:
            raise CapabilityUnavailableError(
                f"no fake document {reference.provider_record_id}"
            ) from error
