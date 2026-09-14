# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path

import pytest

from codekeel.check.snapshot import SnapshotError, _materialize_archive, materialize_git_snapshot

ROOT = Path(__file__).parents[2]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _committed_repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "architecture@example.invalid")
    _git(root, "config", "user.name", "Architecture Test")
    _write(root / "example/__init__.py", "")
    _write(root / "example/tasks/sample.py", "value = 1\n")
    _write(root / "example/tasks/README.md", "not production Python\n")
    _write(root / "script/helper.py", "not_in_scope = True\n")
    _write(root / "pyproject.toml", '[project]\nrequires-python = ">=3.11"\n')
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "fixture")
    return root, _git(root, "rev-parse", "HEAD")


def _tar_with(member: tarfile.TarInfo, payload: bytes = b"") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as stream:
        if member.isfile():
            member.size = len(payload)
            stream.addfile(member, io.BytesIO(payload))
        else:
            stream.addfile(member)
    return buffer.getvalue()


def test_git_snapshot_contains_only_tracked_production_python(tmp_path: Path) -> None:
    root, git_head = _committed_repository(tmp_path)
    _write(root / "example/untracked.py", "must_not_leak = True\n")

    with materialize_git_snapshot(root, git_head, roots=("example",)) as snapshot:
        assert snapshot.git_head == git_head
        assert sorted(
            path.relative_to(snapshot.root).as_posix() for path in snapshot.root.rglob("*")
        ) == [
            "example",
            "example/__init__.py",
            "example/tasks",
            "example/tasks/sample.py",
            "pyproject.toml",
        ]
        assert not (snapshot.root / "example/untracked.py").exists()


def test_git_snapshot_binds_pyproject_to_each_revision(tmp_path: Path) -> None:
    root, first = _committed_repository(tmp_path)
    _write(root / "pyproject.toml", '[project]\nrequires-python = ">=3.12"\n')
    _git(root, "add", "pyproject.toml")
    _git(root, "commit", "-q", "-m", "new runtime")
    second = _git(root, "rev-parse", "HEAD")

    with materialize_git_snapshot(root, first, roots=("example",)) as snapshot:
        assert snapshot.root.joinpath("pyproject.toml").read_text() == (
            '[project]\nrequires-python = ">=3.11"\n'
        )
    with materialize_git_snapshot(root, second, roots=("example",)) as snapshot:
        assert snapshot.root.joinpath("pyproject.toml").read_text() == (
            '[project]\nrequires-python = ">=3.12"\n'
        )


def test_git_snapshot_allows_missing_pyproject(tmp_path: Path) -> None:
    root, _ = _committed_repository(tmp_path)
    _git(root, "rm", "-q", "pyproject.toml")
    _git(root, "commit", "-q", "-m", "remove metadata")
    git_head = _git(root, "rev-parse", "HEAD")

    with materialize_git_snapshot(root, git_head, roots=("example",)) as snapshot:
        assert not snapshot.root.joinpath("pyproject.toml").exists()


def test_archive_with_only_metadata_has_no_scoped_python_sources(tmp_path: Path) -> None:
    metadata = tarfile.TarInfo("pyproject.toml")
    with pytest.raises(SnapshotError, match="no scoped Python sources"):
        _materialize_archive(
            _tar_with(metadata, b'[project]\nrequires-python = ">=3.11"\n'),
            tmp_path / "snapshot",
            roots=("example",),
        )


def test_git_snapshot_rejects_missing_revision(tmp_path: Path) -> None:
    root, _ = _committed_repository(tmp_path)

    with (
        pytest.raises(SnapshotError, match="cannot resolve Git revision"),
        materialize_git_snapshot(root, "f" * 40, roots=("example",)),
    ):
        pass


@pytest.mark.parametrize(
    "member",
    [
        tarfile.TarInfo("../example/escape.py"),
        tarfile.TarInfo("example/link.py"),
        tarfile.TarInfo("pyproject.toml"),
    ],
)
def test_git_snapshot_rejects_unsafe_or_linked_members(
    tmp_path: Path, member: tarfile.TarInfo
) -> None:
    if member.name.endswith("link.py") or member.name == "pyproject.toml":
        member.type = tarfile.SYMTYPE
        member.linkname = "target.py"

    with pytest.raises(SnapshotError, match="unsafe|unsupported"):
        _materialize_archive(
            _tar_with(member, b"value = 1\n"), tmp_path / "snapshot", roots=("example",)
        )
