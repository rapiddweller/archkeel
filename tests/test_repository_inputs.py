# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Repository text proof follows Git identity, never a source parser or live revision fallback."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from archkeel.check.ports import RepositorySnapshotPaths
from archkeel.check.repository_inputs import read_repository_inputs
from archkeel.check.snapshot import materialize_git_snapshot
from archkeel.ir.repository_files import (
    RepositoryFileExclusion,
    RepositoryFileExclusionKind,
    RepositoryFileGapReason,
    RepositoryFileScope,
    RepositoryFileSelection,
)
from archkeel.ir.repository_manifest import manifest_file_digests


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "core.autocrlf", "false")
    return tmp_path


def _selection(*exclusions):
    return RepositoryFileSelection(
        (RepositoryFileScope(".", (".py", ".css"), ("Makefile",), True),), exclusions
    )


def _read(root, selection=None, paths=None):
    return read_repository_inputs(
        root,
        selection or _selection(),
        git_head="head",
        dirty=False,
        snapshot=None if paths is None else RepositorySnapshotPaths(paths, "head", False),
    )


def test_physical_text_inventory_ignores_language_syntax_and_preserves_exact_bytes(tmp_path):
    root = _repo(tmp_path)
    contents = {
        "broken.py": b"def (\r\n!!",
        "style.css": b"a{}\n",
        "Makefile": b"sample:\n\ttrue\n",
        "tool": b"#!/bin/sh\necho ok",
        "empty.py": b"",
        "data.txt": b"ignored",
    }
    for path, content in contents.items():
        (root / path).write_bytes(content)
    inventory = _read(root)
    assert not inventory.gaps
    assert {f.path: f.physical_lines for f in inventory.files} == {
        "broken.py": 2,
        "style.css": 1,
        "Makefile": 2,
        "tool": 2,
        "empty.py": 0,
    }
    assert all(f.sha256 == _sha(contents[f.path]) for f in inventory.files)
    assert inventory.expected_paths == tuple(sorted(contents))


@pytest.mark.parametrize("content", [b"\xff", b"abc\0def"])
def test_binary_or_undecodable_matched_file_remains_selected_unknown(tmp_path, content):
    (tmp_path / "bad.py").write_bytes(content)
    inventory = _read(tmp_path, paths=("bad.py",))
    assert inventory.selected_paths == ("bad.py",)
    assert not inventory.files
    assert [gap.reason for gap in inventory.gaps] == [RepositoryFileGapReason.DECODE]


def test_no_git_enumeration_never_falls_back_to_directory_walk(tmp_path):
    (tmp_path / "a.py").write_text("x=1")
    inventory = _read(tmp_path)
    assert not inventory.expected_paths and not inventory.files
    assert RepositoryFileGapReason.ENUMERATION in {g.reason for g in inventory.gaps}


@pytest.mark.parametrize(
    "kind", [RepositoryFileExclusionKind.FILE, RepositoryFileExclusionKind.MANIFEST]
)
@pytest.mark.parametrize("stale", [False, True])
def test_exclusion_requires_both_manifest_and_file_bytes(tmp_path, kind, stale):
    data = b"vendor\n"
    (tmp_path / "vendor.py").write_bytes(data)
    manifest = json.dumps({"files": [{"path": "vendor.py", "sha256": _sha(data)}]}).encode()
    (tmp_path / "SNAPSHOT.json").write_bytes(manifest)
    path, witness = (
        ("vendor.py", data)
        if kind is RepositoryFileExclusionKind.FILE
        else ("SNAPSHOT.json", manifest)
    )
    selection = _selection(
        RepositoryFileExclusion(kind, path, _sha(witness), "generated", ("owner",))
    )
    if stale:
        (tmp_path / "vendor.py").write_bytes(b"changed\n")
    inventory = _read(tmp_path, selection, ("SNAPSHOT.json", "vendor.py"))
    assert bool(inventory.files) is stale
    assert bool(inventory.excluded_files) is not stale
    assert bool(inventory.gaps) is stale
    if kind is RepositoryFileExclusionKind.MANIFEST:
        assert inventory.manifest_inputs[0].sha256 == _sha(manifest)


@pytest.mark.parametrize(
    "entry",
    [
        {"path": "../outside.py", "sha256": "a" * 64},
        {"path": "ok.py", "sha256": "bad"},
        {"sha256": "a" * 64},
    ],
)
def test_manifest_rejects_invalid_file_witness(entry):
    with pytest.raises(ValueError):
        manifest_file_digests("SNAPSHOT.json", json.dumps([entry]).encode())


def test_missing_and_symlink_never_become_regular_file_facts(tmp_path):
    (tmp_path / "real.py").write_text("x")
    (tmp_path / "link.py").symlink_to(tmp_path / "real.py")
    inventory = _read(tmp_path, paths=("link.py", "missing.py"))
    assert not inventory.files
    assert {g.reason for g in inventory.gaps} == {
        RepositoryFileGapReason.SYMLINK,
        RepositoryFileGapReason.MISSING,
    }


def test_archive_inventory_uses_revision_text_and_manifest_not_live_checkout(tmp_path):
    root = _repo(tmp_path)
    (root / "src").mkdir()
    (root / "src/a.py").write_text("x=1\n")
    (root / "Makefile").write_bytes(b"one\ntwo\n")
    (root / "vendor.css").write_bytes(b"generated\n")
    manifest = json.dumps({"files": [{"path": "vendor.css", "sha256": _sha(b"generated\n")}]})
    (root / "SNAPSHOT.json").write_text(manifest)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "snapshot")
    head = _git(root, "rev-parse", "HEAD")
    selection = _selection(
        RepositoryFileExclusion(
            RepositoryFileExclusionKind.MANIFEST,
            "SNAPSHOT.json",
            _sha(manifest.encode()),
            "vendor",
            ("owner",),
        )
    )
    (root / "Makefile").write_text("live\n")
    (root / "vendor.css").write_text("live\n")
    (root / "SNAPSHOT.json").unlink()
    with materialize_git_snapshot(
        root, head, roots=("src",), repository_selections=(selection,)
    ) as snapshot:
        assert snapshot.repository_paths is not None
        inventory = read_repository_inputs(
            snapshot.root, selection, git_head=head, dirty=False, snapshot=snapshot.repository_paths
        )
        assert not inventory.gaps
        assert next(f for f in inventory.files if f.path == "Makefile").physical_lines == 2
        assert inventory.excluded_files[0].sha256 == _sha(b"generated\n")
        assert not (snapshot.root / ".git").exists()


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
@pytest.mark.parametrize("count", [500, 501])
@pytest.mark.parametrize("terminated", [False, True])
def test_all_physical_newlines_have_identical_counts(tmp_path, newline, count, terminated):
    data = newline.join([b"x"] * count) + (newline if terminated else b"")
    (tmp_path / "a.py").write_bytes(data)
    inventory = _read(tmp_path, paths=("a.py",))
    assert not inventory.gaps
    assert inventory.files[0].physical_lines == count


def test_unreadable_selected_file_is_a_read_gap(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("x")
    original = Path.read_bytes

    def read(path):
        if path == target:
            raise PermissionError("denied")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    inventory = _read(tmp_path, paths=("a.py",))
    assert inventory.selected_paths == ("a.py",)
    assert inventory.gaps[0].reason is RepositoryFileGapReason.READ


@pytest.mark.parametrize("contents", [None, b"{}", b"stale"])
def test_missing_malformed_or_stale_manifest_never_excludes_files(tmp_path, contents):
    manifest = b"{}"
    (tmp_path / "a.py").write_text("x")
    if contents is not None:
        (tmp_path / "SNAPSHOT.json").write_bytes(contents)
    selection = _selection(
        RepositoryFileExclusion(
            RepositoryFileExclusionKind.MANIFEST,
            "SNAPSHOT.json",
            _sha(manifest),
            "vendor",
            ("owner",),
        )
    )
    inventory = _read(tmp_path, selection, ("a.py",))
    assert inventory.gaps
    assert not inventory.excluded_files
    assert inventory.files[0].path == "a.py"
