import asyncio
from datetime import UTC, datetime

from fra.adapters.fakes.documents import FakeDocumentProvider
from fra.adapters.in_memory.repositories import InMemorySourceStatusRepository
from fra.application.source_platform import SourceRegistry
from fra.application.source_service import SourceService
from fra.domain.sources import SourceRole

NOW = datetime(2000, 1, 1, tzinfo=UTC)


def test_source_checks_are_explicit_and_persist_last_known_status() -> None:
    statuses = InMemorySourceStatusRepository()
    registry = SourceRegistry()
    registry.register(FakeDocumentProvider(now=NOW), roles=(SourceRole.PRIMARY,))
    service = SourceService(registry, statuses)

    assert statuses.list() == ()
    assert service.list()[0].health == "unknown"

    checked = asyncio.run(service.check("fake_documents"))

    assert checked[0].health.state.value == "healthy"
    assert statuses.get("fake_documents") == checked[0]
    assert service.list()[0].health == "healthy"


def test_source_description_exposes_manifest_policy_without_credentials() -> None:
    registry = SourceRegistry()
    registry.register(FakeDocumentProvider(), roles=(SourceRole.PRIMARY, SourceRole.CROSS_CHECK))
    service = SourceService(registry, InMemorySourceStatusRepository())

    described = service.describe("fake_documents")

    assert described.provider_id == "fake_documents"
    assert described.roles == (SourceRole.PRIMARY, SourceRole.CROSS_CHECK)
    assert described.allowed_usage_profiles == ("local_personal_research",)
    assert described.credential_environment_names == ()
