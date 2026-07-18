"""Configured RSS/Atom document ingestion using the shared HTTP boundary."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.common.manifests import validate_source_manifest
from fra.domain.documents import Document, DocumentCapabilities, DocumentQuery, DocumentRef
from fra.domain.errors import (
    CapabilityUnavailableError,
    ExternalDataInvalidError,
    PointInTimeUnavailableError,
)
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import DataEnvelope, SourceDescriptor


class RssAtomDocumentAdapter:
    def __init__(
        self,
        *,
        feed_url: str,
        client: HttpClient,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        provider_id: str = "rss_atom_documents",
        terms_url: str = "https://www.rssboard.org/rss-specification",
        terms_reviewed_at: date = date(1970, 1, 1),
        allowed_usage_profiles: tuple[str, ...] = (
            "local_personal_research",
            "internal_research",
            "commercial",
        ),
    ) -> None:
        self._feed_url = feed_url
        self._client = client
        self._now = now
        self._items: dict[str, tuple[DocumentRef, str]] = {}
        self._last_hash: str | None = None
        self._last_fingerprint: str | None = None
        self._descriptor = validate_source_manifest(
            {
                "manifest_version": 1,
                "provider_id": provider_id,
                "adapter_version": "1.0.0",
                "source_kinds": ["document"],
                "authority_class": "official",
                "point_in_time_support": False,
                "allowed_usage_profiles": list(allowed_usage_profiles),
                "raw_retention": "metadata_only",
                "terms_url": terms_url,
                "terms_reviewed_at": terms_reviewed_at,
                "independence_group": provider_id,
                "normal_update_cadence": "feed-defined",
            }
        )

    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    def capabilities(self) -> DocumentCapabilities:
        return DocumentCapabilities(search=True, fetch=True, point_in_time=False)

    async def health(self) -> HealthStatus:
        await self._load()
        return HealthStatus(HealthState.HEALTHY, self._now(), "feed retrieved and parsed")

    async def search(self, query: DocumentQuery) -> DataEnvelope[tuple[DocumentRef, ...]]:
        if query.point_in_time_at is not None:
            raise PointInTimeUnavailableError(
                "a current RSS/Atom feed cannot prove its historical contents"
            )
        await self._load()
        matches = tuple(
            reference
            for reference, content in self._items.values()
            if query.text.casefold() in f"{reference.title} {content}".casefold()
            and (
                query.published_after is None
                or reference.published_at is None
                or reference.published_at >= query.published_after
            )
            and (
                query.published_before is None
                or reference.published_at is None
                or reference.published_at <= query.published_before
            )
            and (
                query.point_in_time_at is None
                or reference.published_at is None
                or reference.published_at <= query.point_in_time_at
            )
        )
        retrieved = self._now()
        return DataEnvelope(
            value=matches,
            descriptor=self._descriptor,
            provider_record_id="feed-index",
            source=self._feed_url,
            available_at=retrieved,
            retrieved_at=retrieved,
            content_hash=self._last_hash,
            request_fingerprint=self._last_fingerprint,
            usage_policy_id=f"{self._descriptor.provider_id}-manifest-v1",
        )

    async def fetch(self, reference: DocumentRef) -> DataEnvelope[Document]:
        if reference.provider_record_id not in self._items:
            await self._load()
        try:
            stored, content = self._items[reference.provider_record_id]
        except KeyError as error:
            raise CapabilityUnavailableError(
                f"feed document {reference.provider_record_id} is unavailable"
            ) from error
        retrieved = self._now()
        return DataEnvelope(
            value=Document(
                stored.provider_record_id,
                stored.title,
                stored.source,
                content,
                stored.published_at,
                stored.updated_at,
                stored.corrects_provider_record_id,
                stored.withdrawn,
            ),
            descriptor=self._descriptor,
            provider_record_id=stored.provider_record_id,
            source=stored.source,
            published_at=stored.published_at,
            revised_at=stored.updated_at,
            available_at=stored.updated_at or stored.published_at or retrieved,
            retrieved_at=retrieved,
            content_hash=self._last_hash,
            request_fingerprint=self._last_fingerprint,
            usage_policy_id=f"{self._descriptor.provider_id}-manifest-v1",
        )

    async def _load(self) -> None:
        response = await self._client.get(self._feed_url)
        try:
            root = ElementTree.fromstring(response.body)
        except ElementTree.ParseError as error:
            raise ExternalDataInvalidError("source returned malformed RSS/Atom XML") from error
        items: dict[str, tuple[DocumentRef, str]] = {}
        for node in root.findall(".//item"):
            title = _text(node, "title")
            link = _text(node, "link")
            record_id = _text(node, "guid") or link
            content = _text(node, "description")
            published = _published(_text(node, "pubDate"))
            if title and link and record_id and content:
                reference = DocumentRef(record_id, title, link, published)
                items[record_id] = (reference, content)
        atom_namespace = {"atom": "http://www.w3.org/2005/Atom"}
        for node in root.findall(".//atom:entry", atom_namespace):
            title = _text(node, "{http://www.w3.org/2005/Atom}title")
            record_id = _text(node, "{http://www.w3.org/2005/Atom}id")
            link_node = node.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.attrib.get("href", "") if link_node is not None else ""
            content = _text(node, "{http://www.w3.org/2005/Atom}summary") or _text(
                node, "{http://www.w3.org/2005/Atom}content"
            )
            published = _published(_text(node, "{http://www.w3.org/2005/Atom}published"))
            updated = _published(_text(node, "{http://www.w3.org/2005/Atom}updated"))
            published = published or updated
            if title and link and record_id and content:
                reference = DocumentRef(record_id, title, link, published, updated)
                items[record_id] = (reference, content)
        if not items:
            raise ExternalDataInvalidError("feed contains no valid document entries")
        self._items = dict(sorted(items.items()))
        self._last_hash = response.content_hash
        self._last_fingerprint = response.request_fingerprint


def _text(node: ElementTree.Element, tag: str) -> str:
    found = node.find(tag)
    return "" if found is None or found.text is None else found.text.strip()


def _published(value: str) -> datetime | None:
    if not value:
        return None
    try:
        if "," in value:
            parsed = parsedate_to_datetime(value)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
