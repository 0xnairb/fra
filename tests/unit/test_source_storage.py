from datetime import UTC, datetime, timedelta
from pathlib import Path

from fra.adapters.in_memory.repositories import InMemorySourceCacheRepository
from fra.adapters.storage.markdown_sources import (
    MarkdownSourceCacheRepository,
    MarkdownSourceStatusRepository,
)
from fra.adapters.storage.workspace import Workspace
from fra.application.source_cache import SourceCache
from fra.domain.shared import HealthState, HealthStatus
from fra.domain.sources import (
    RawRetentionPolicy,
    SourceCacheEntry,
    SourceStatusRecord,
    UsageProfile,
)

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)
FINGERPRINT = "sha256:" + "a" * 64
CONTENT_HASH = "sha256:" + "b" * 64


def test_source_status_round_trips_as_human_readable_markdown(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    repository = MarkdownSourceStatusRepository(workspace)
    record = SourceStatusRecord(
        provider_id="world_bank_indicators",
        checked_at=NOW,
        health=HealthStatus(HealthState.DEGRADED, NOW, "reachable", warnings=("slow",)),
        capability_warnings=("no historical vintages",),
        quota_warning="provider may throttle requests",
    )

    repository.save(record)

    assert repository.get("world_bank_indicators") == record
    assert repository.list() == (record,)
    text = (workspace.root / "source-status/world_bank_indicators.md").read_text()
    assert "schema: fra.source_status" in text
    assert "# Source Status: world_bank_indicators" in text
    assert "provider may throttle requests" in text


def test_cache_enforces_expiry_usage_and_retention_for_memory_and_markdown(tmp_path: Path) -> None:
    entries = (
        InMemorySourceCacheRepository(),
        MarkdownSourceCacheRepository(Workspace(tmp_path / "workspace")),
    )
    for repository in entries:
        if isinstance(repository, MarkdownSourceCacheRepository):
            repository.initialize_workspace()
        cache = SourceCache(repository)
        entry = SourceCacheEntry(
            provider_id="world_bank_indicators",
            request_fingerprint=FINGERPRINT,
            retrieved_at=NOW,
            available_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(hours=1),
            usage_profile=UsageProfile.LOCAL_PERSONAL_RESEARCH,
            raw_retention=RawRetentionPolicy.METADATA_ONLY,
            content_hash=CONTENT_HASH,
            payload={"value": "fixture"},
        )
        cache.put(entry)

        assert (
            cache.get(
                "world_bank_indicators",
                FINGERPRINT,
                now=NOW,
                usage_profile=UsageProfile.LOCAL_PERSONAL_RESEARCH,
                raw_retention_required=False,
            )
            == entry
        )
        assert (
            cache.get(
                "world_bank_indicators",
                FINGERPRINT,
                now=NOW + timedelta(hours=2),
                usage_profile=UsageProfile.LOCAL_PERSONAL_RESEARCH,
                raw_retention_required=False,
            )
            is None
        )
        assert (
            cache.get(
                "world_bank_indicators",
                FINGERPRINT,
                now=NOW,
                usage_profile=UsageProfile.COMMERCIAL,
                raw_retention_required=False,
            )
            is None
        )
        assert (
            cache.get(
                "world_bank_indicators",
                FINGERPRINT,
                now=NOW,
                usage_profile=UsageProfile.LOCAL_PERSONAL_RESEARCH,
                raw_retention_required=True,
            )
            is None
        )
