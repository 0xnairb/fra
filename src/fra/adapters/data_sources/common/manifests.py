"""Strict Pydantic validation at the source-manifest boundary."""

from datetime import date, timedelta
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, ValidationError

from fra.domain.errors import DomainValidationError
from fra.domain.sources import (
    AuthenticationKind,
    AuthorityClass,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    manifest_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    provider_id: NonEmpty
    adapter_version: NonEmpty
    source_kinds: frozenset[SourceKind]
    authority_class: AuthorityClass
    point_in_time_support: Annotated[bool, Field(strict=True)]
    allowed_usage_profiles: frozenset[UsageProfile]
    raw_retention: RawRetentionPolicy
    terms_url: HttpUrl
    terms_reviewed_at: date
    independence_group: NonEmpty
    geographies: frozenset[str] = frozenset()
    markets: frozenset[str] = frozenset()
    frequencies: frozenset[str] = frozenset()
    fields: frozenset[str] = frozenset()
    history_start: date | None = None
    authentication_kind: AuthenticationKind = AuthenticationKind.NONE
    credential_environment_names: tuple[str, ...] = ()
    quota_description: str | None = None
    normal_update_cadence: str | None = None
    maximum_expected_age_seconds: Annotated[int, Field(strict=True, gt=0)] | None = None
    required_attribution: str | None = None
    experimental: Annotated[bool, Field(strict=True)] = False
    discovery_only: Annotated[bool, Field(strict=True)] = False


def validate_source_manifest(raw: dict[str, Any]) -> SourceDescriptor:
    """Validate untrusted manifest data and return the immutable domain descriptor."""
    try:
        manifest = SourceManifest.model_validate(raw)
    except ValidationError as error:
        errors = error.errors(include_url=False, include_input=False)
        if any(item["type"] == "extra_forbidden" for item in errors):
            fields = ", ".join(".".join(map(str, item["loc"])) for item in errors)
            raise DomainValidationError(f"unknown manifest option: {fields}") from error
        message = "; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in errors)
        raise DomainValidationError(f"invalid source manifest: {message}") from error
    if not manifest.allowed_usage_profiles:
        raise DomainValidationError("unknown source usage rights fail closed")
    if not manifest.source_kinds:
        raise DomainValidationError("source descriptor requires at least one source kind")
    if manifest.terms_url.scheme != "https":
        raise DomainValidationError("source manifest terms URL must use HTTPS")
    return SourceDescriptor(
        provider_id=manifest.provider_id,
        adapter_version=manifest.adapter_version,
        source_kinds=manifest.source_kinds,
        authority_class=manifest.authority_class,
        point_in_time_support=manifest.point_in_time_support,
        allowed_usage_profiles=manifest.allowed_usage_profiles,
        raw_retention=manifest.raw_retention,
        terms_url=str(manifest.terms_url),
        terms_reviewed_at=manifest.terms_reviewed_at,
        independence_group=manifest.independence_group,
        geographies=manifest.geographies,
        markets=manifest.markets,
        frequencies=manifest.frequencies,
        fields=manifest.fields,
        history_start=manifest.history_start,
        authentication_kind=manifest.authentication_kind,
        credential_environment_names=manifest.credential_environment_names,
        quota_description=manifest.quota_description,
        normal_update_cadence=manifest.normal_update_cadence,
        maximum_expected_age=(
            timedelta(seconds=manifest.maximum_expected_age_seconds)
            if manifest.maximum_expected_age_seconds is not None
            else None
        ),
        required_attribution=manifest.required_attribution,
        experimental=manifest.experimental,
        discovery_only=manifest.discovery_only,
    )
