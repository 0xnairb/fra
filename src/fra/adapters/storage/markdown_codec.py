"""Deterministic YAML-front-matter Markdown codec."""

from __future__ import annotations

from typing import Any

import yaml

from fra.domain.errors import RepositoryCorruptError


class MarkdownCodec:
    """Render and parse the common FRA Markdown document envelope."""

    def __init__(self, *, supported_schema_version: int = 1) -> None:
        self._supported_schema_version = supported_schema_version

    def render(self, metadata: dict[str, Any], body: str) -> str:
        required = {"schema", "schema_version", "id"}
        if not required.issubset(metadata):
            missing = ", ".join(sorted(required - metadata.keys()))
            raise RepositoryCorruptError(f"document metadata is missing: {missing}")
        front_matter = yaml.safe_dump(
            metadata,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ).rstrip()
        normalized_body = body.rstrip() + "\n"
        return f"---\n{front_matter}\n---\n\n{normalized_body}"

    def parse(self, text: str, *, expected_schema: str | None = None) -> tuple[dict[str, Any], str]:
        if not text.startswith("---\n"):
            raise RepositoryCorruptError("document is missing YAML front matter")
        boundary = text.find("\n---\n", 4)
        if boundary < 0:
            raise RepositoryCorruptError("document has malformed YAML front matter")
        try:
            loaded = yaml.safe_load(text[4:boundary])
        except yaml.YAMLError as error:
            raise RepositoryCorruptError("document has malformed YAML front matter") from error
        if not isinstance(loaded, dict):
            raise RepositoryCorruptError("document front matter must be a mapping")
        metadata = dict(loaded)
        schema = metadata.get("schema")
        version = metadata.get("schema_version")
        if not isinstance(schema, str) or not isinstance(version, int):
            raise RepositoryCorruptError("document schema metadata is missing or invalid")
        if expected_schema is not None and schema != expected_schema:
            raise RepositoryCorruptError(
                f"document schema {schema!r} does not match {expected_schema!r}"
            )
        if version != self._supported_schema_version:
            raise RepositoryCorruptError(
                f"unsupported {schema} schema version {version}; "
                f"supported version is {self._supported_schema_version}"
            )
        body = text[boundary + 5 :]
        if body.startswith("\n"):
            body = body[1:]
        return metadata, body
