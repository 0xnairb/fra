import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from fra.adapters.storage import atomic_files
from fra.adapters.storage.atomic_files import AggregateLock, AtomicFileWriter
from fra.adapters.storage.markdown_codec import MarkdownCodec
from fra.domain.errors import RepositoryCorruptError

FIXTURES = Path(__file__).parents[1] / "fixtures" / "markdown"


def test_markdown_codec_is_deterministic_and_round_trips() -> None:
    codec = MarkdownCodec()
    metadata = {
        "schema": "fra.fixture",
        "schema_version": 1,
        "id": "fixture_0001",
        "items": ["one", "two"],
    }

    rendered = codec.render(metadata, "# Fixture\n\nBody.\n")

    assert rendered == codec.render(metadata, "# Fixture\n\nBody.\n")
    assert codec.parse(rendered, expected_schema="fra.fixture") == (
        metadata,
        "# Fixture\n\nBody.\n",
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not front matter", "front matter"),
        ("---\nschema: fra.fixture\nschema_version: 2\n---\nbody\n", "unsupported"),
        ("---\nschema: fra.other\nschema_version: 1\n---\nbody\n", "schema"),
    ],
)
def test_markdown_codec_rejects_malformed_newer_and_wrong_documents(
    text: str, message: str
) -> None:
    with pytest.raises(RepositoryCorruptError, match=message):
        MarkdownCodec().parse(text, expected_schema="fra.fixture")


def test_atomic_writer_preserves_previous_file_when_replace_is_interrupted(
    tmp_path: Path,
) -> None:
    target = tmp_path / "aggregate.md"
    target.write_text("previous")

    def interrupted(_source: Path, _target: Path) -> None:
        raise OSError("interrupted before replace")

    with pytest.raises(OSError, match="interrupted"):
        AtomicFileWriter(replace=interrupted).write_text(target, "new")

    assert target.read_text() == "previous"
    assert tuple(tmp_path.glob(".aggregate.md.*.tmp")) == ()


def test_aggregate_lock_uses_readable_handle_for_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[int, int]] = []
    fake_msvcrt = SimpleNamespace(
        LK_LOCK=1,
        LK_UNLCK=2,
        locking=lambda _descriptor, operation, size: calls.append((operation, size)),
    )
    monkeypatch.setattr(atomic_files, "fcntl", None)
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    path = tmp_path / "aggregate.lock"

    with AggregateLock(path):
        pass

    assert path.read_text() == "0"
    assert calls == [(fake_msvcrt.LK_LOCK, 1), (fake_msvcrt.LK_UNLCK, 1)]


def test_checked_in_schema_and_interrupted_document_fixtures() -> None:
    codec = MarkdownCodec()
    metadata, body = codec.parse((FIXTURES / "valid.md").read_text(), expected_schema="fra.fixture")
    assert metadata["id"] == "fixture_valid"
    assert body == "# Valid fixture\n"

    for name in ("older.md", "newer.md", "malformed.md", "partially-written.md"):
        with pytest.raises(RepositoryCorruptError):
            codec.parse((FIXTURES / name).read_text(), expected_schema="fra.fixture")
