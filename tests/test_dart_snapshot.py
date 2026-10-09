# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dart snapshots contain only selected, regular files with exact-byte digests."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from archkeel.analyzer.dart.snapshot import SnapshotError, read_snapshot
from archkeel.ir.protocol import CollectionRequest, DartSettings, SnapshotInput, SourceScope


def request(root: Path, *roots: str) -> CollectionRequest:
    pubspec = root / "pubspec.yaml"
    if not pubspec.exists() and not pubspec.is_symlink():
        pubspec.write_text("name: configured_package\n", encoding="utf-8")
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(roots or ("lib",), "configured_namespace"),
        DartSettings(),
    )


def test_snapshot_digests_exact_source_and_pubspec_bytes_and_separates_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "lib" / "main.dart"
    source.parent.mkdir()
    source.write_bytes(b"class Main {}\r\n")
    (tmp_path / "pubspec.yaml").write_bytes(b"name: another_package # metadata only\n")
    (tmp_path / "lib" / ".dart_tool").mkdir()
    (tmp_path / "lib" / ".dart_tool" / "ignored.dart").write_text("class Ignored {}")

    snapshot = read_snapshot(request(tmp_path))

    assert [(item.rel_path, item.module, item.content) for item in snapshot.sources] == [
        ("lib/main.dart", "configured_namespace.main", b"class Main {}\r\n")
    ]
    assert snapshot.package_name == "another_package"
    assert [(item.path, item.kind) for item in snapshot.problems] == [
        ("lib/.dart_tool", "ExcludedTreeError")
    ]
    assert {item.path: (item.digest, item.role) for item in snapshot.inputs} == {
        "lib/main.dart": (hashlib.sha256(source.read_bytes()).hexdigest(), "selected"),
        "pubspec.yaml": (
            hashlib.sha256((tmp_path / "pubspec.yaml").read_bytes()).hexdigest(),
            "resolution",
        ),
    }


def test_snapshot_reports_module_collisions(tmp_path: Path) -> None:
    for name in ("a-b.dart", "a_b.dart"):
        path = tmp_path / "lib" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("class A {}\n")

    snapshot = read_snapshot(request(tmp_path))

    assert {item.kind for item in snapshot.problems} == {"DartModuleCollision"}


def test_snapshot_rejects_symlinked_root_source_and_pubspec(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "escaped.dart").write_text("class Escaped {}\n")
    (tmp_path / "lib").symlink_to(outside, target_is_directory=True)
    (tmp_path / "pubspec.yaml").write_text("name: configured_package\n")

    snapshot = read_snapshot(request(tmp_path))

    assert snapshot.sources == ()
    assert [(item.path, item.kind) for item in snapshot.problems] == [("lib", "DartSourceLink")]


def test_snapshot_fails_before_reading_symlinked_pubspec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.yaml"
    outside.write_text("name: escaped\n")
    (tmp_path / "pubspec.yaml").symlink_to(outside)
    original = Path.read_bytes
    symlink = tmp_path / "pubspec.yaml"

    def guarded_read(path: Path) -> bytes:
        if path in {outside, symlink}:
            raise AssertionError("symlinked pubspec was read")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    with pytest.raises(SnapshotError, match="regular pubspec.yaml"):
        read_snapshot(request(tmp_path))


def test_snapshot_rejects_ambiguous_pubspec_identity(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: one\nname: two\n", encoding="utf-8")
    with pytest.raises(SnapshotError, match="valid package name"):
        read_snapshot(request(tmp_path))


@pytest.mark.parametrize(
    "environment",
    (
        "environment: {sdk: '>=3.9.0 <4'}\n",
        "environment:\n  sdk: '>=3.9.0 <4'\n  sdk: '<4'\n",
    ),
)
def test_snapshot_preserves_invalid_sdk_metadata_state(tmp_path: Path, environment: str) -> None:
    (tmp_path / "pubspec.yaml").write_text(f"name: valid\n{environment}", encoding="utf-8")

    snapshot = read_snapshot(request(tmp_path))

    assert snapshot.sdk_constraint is None
    assert snapshot.sdk_constraint_state == "requirement_invalid"


def test_snapshot_rejects_symlinked_source_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.dart"
    outside.write_text("class Escaped {}\n")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "escaped.dart").symlink_to(outside)
    original = Path.read_bytes
    symlink = tmp_path / "lib" / "escaped.dart"

    def guarded_read(path: Path) -> bytes:
        if path in {outside, symlink}:
            raise AssertionError("symlinked source was read")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)

    snapshot = read_snapshot(request(tmp_path))

    assert snapshot.sources == ()
    assert [(item.path, item.kind) for item in snapshot.problems] == [
        ("lib/escaped.dart", "DartSourceLink")
    ]


def test_snapshot_reports_walk_errors_instead_of_claiming_complete_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "main.dart").write_text("class Main {}\n")
    original_walk = os.walk

    def failing_walk(top, *, followlinks=False, onerror=None):
        if onerror is not None:
            onerror(PermissionError(13, "permission denied", str(tmp_path / "lib" / "blocked")))
        yield from original_walk(top, followlinks=followlinks)

    monkeypatch.setattr(os, "walk", failing_walk)

    snapshot = read_snapshot(request(tmp_path))

    assert any(
        item.path == "lib/blocked" and item.kind == "SnapshotError" for item in snapshot.problems
    )


@pytest.mark.parametrize("root", ("../outside", "/tmp", "lib\\src", "lib/**"))
def test_snapshot_rejects_unsafe_configured_roots(tmp_path: Path, root: str) -> None:
    with pytest.raises(ValueError, match="unsafe Dart snapshot root"):
        read_snapshot(request(tmp_path, root))


def test_nested_sdk_is_not_a_source_language_constraint(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text(
        "name: valid\nenvironment:\n  custom:\n    sdk: '>=3.9.0 <4.0.0'\n",
        encoding="utf-8",
    )

    snapshot = read_snapshot(request(tmp_path))

    assert snapshot.sdk_constraint is None
    assert snapshot.sdk_constraint_state == "requirement_invalid"


@pytest.mark.parametrize("relative", ("lib/main.dart", "pubspec.yaml"))
def test_replacement_with_symlink_is_rejected_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    selected = tmp_path / relative
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text("name: valid\n" if relative.endswith("yaml") else "class Main {}\n")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.write_text("name: outside\n" if relative.endswith("yaml") else "class Outside {}\n")
    collection_request = request(tmp_path)
    original = Path.resolve
    replaced = False

    def replace_after_check(path: Path, *args, **kwargs) -> Path:
        nonlocal replaced
        resolved = original(path, *args, **kwargs)
        if path == selected and not replaced:
            replaced = True
            selected.unlink()
            selected.symlink_to(outside)
        return resolved

    monkeypatch.setattr(Path, "resolve", replace_after_check)
    if relative.endswith("yaml"):
        with pytest.raises(SnapshotError, match="regular pubspec.yaml"):
            read_snapshot(collection_request)
    else:
        snapshot = read_snapshot(collection_request)
        assert snapshot.sources == ()
        assert any(issue.path == relative for issue in snapshot.problems)
    assert replaced
