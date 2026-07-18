import stat
from pathlib import Path

import pytest

from fra.adapters.storage.workspace import Workspace


def test_workspace_initialization_is_idempotent_and_preserves_user_content(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    workspace = Workspace(root)

    first = workspace.initialize()
    marker = root / "signals" / "user-note.md"
    marker.write_text("keep me")
    second = workspace.initialize()

    assert first.created is True
    assert second.created is False
    assert marker.read_text() == "keep me"
    assert (root / "workspace.md").is_file()
    assert stat.S_IMODE(root.stat().st_mode) & 0o077 == 0


def test_workspace_rejects_paths_outside_its_root(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()

    assert workspace.path("runs/run_1/run.md").is_relative_to(workspace.root)

    try:
        workspace.path("../outside.md")
    except ValueError as error:
        assert "contained" in str(error)
    else:
        raise AssertionError("path traversal was accepted")


def test_workspace_rejects_a_symlink_that_escapes_the_root(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace.root / "runs" / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("filesystem does not support symlinks")

    with pytest.raises(ValueError, match="contained"):
        workspace.path("runs/escape/run.md")
