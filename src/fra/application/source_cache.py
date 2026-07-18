"""Policy-aware access to disposable source cache entries."""

from datetime import datetime

from fra.domain.sources import RawRetentionPolicy, SourceCacheEntry, UsageProfile
from fra.domain.time import as_utc
from fra.ports.repositories import SourceCacheRepository


class SourceCache:
    def __init__(self, repository: SourceCacheRepository) -> None:
        self._repository = repository

    def put(self, entry: SourceCacheEntry) -> None:
        self._repository.save(entry)

    def get(
        self,
        provider_id: str,
        request_fingerprint: str,
        *,
        now: datetime,
        usage_profile: UsageProfile,
        raw_retention_required: bool,
        allow_stale: bool = False,
    ) -> SourceCacheEntry | None:
        entry = self._repository.get(provider_id, request_fingerprint)
        if entry is None:
            return None
        now = as_utc(now, field="cache lookup time")
        if now > entry.expires_at and not allow_stale:
            return None
        if entry.usage_profile is not usage_profile:
            return None
        if raw_retention_required and entry.raw_retention is not RawRetentionPolicy.PERMITTED:
            return None
        return entry
