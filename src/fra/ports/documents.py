"""Normalized document capability port."""

from typing import Protocol

from fra.domain.documents import (
    Document,
    DocumentCapabilities,
    DocumentQuery,
    DocumentRef,
)
from fra.domain.shared import HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor


class DocumentProvider(Protocol):
    def descriptor(self) -> SourceDescriptor: ...

    def capabilities(self) -> DocumentCapabilities: ...

    async def health(self) -> HealthStatus: ...

    async def search(self, query: DocumentQuery) -> DataEnvelope[tuple[DocumentRef, ...]]: ...

    async def fetch(self, reference: DocumentRef) -> DataEnvelope[Document]: ...
