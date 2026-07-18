"""Deterministic local/file-download metadata helpers."""

from dataclasses import dataclass
from pathlib import Path

from fra.adapters.data_sources.common.http import content_hash, request_fingerprint


@dataclass(frozen=True, slots=True)
class LoadedFile:
    content: bytes
    content_hash: str
    request_fingerprint: str


def load_file(path: Path) -> LoadedFile:
    resolved = path.expanduser().resolve()
    content = resolved.read_bytes()
    return LoadedFile(
        content=content,
        content_hash=content_hash(content),
        request_fingerprint=request_fingerprint("FILE", resolved.as_uri()),
    )
