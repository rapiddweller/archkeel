# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Integrity checks for pinned project demo source snapshots."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _snapshot(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_bytes())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha1(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode()
    return hashlib.sha1(header + payload).hexdigest()


def _source_identity(snapshot: dict[str, object], item: dict[str, object]) -> None:
    """One identity check: the URL of a file names the repository and the commit of the snapshot."""
    base = f"https://github.com/{snapshot['repository']}/blob/{snapshot['commit']}/"
    assert item["source_url"] == base + str(item["source_path"]), item["path"]


def _on_disk(root: Path, *folders: str) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for folder in folders
        for path in (root / folder).rglob("*")
        if path.is_file()
    }


def test_compass_snapshot_matches_the_files_and_the_workspace() -> None:
    fixture = ROOT / "fixtures/J-compass"
    snapshot = _snapshot("fixtures/J-compass/SNAPSHOT.json")
    files = snapshot["files"]
    for item in files:
        assert _sha256(fixture / item["path"]) == item["sha256"]
        _source_identity(snapshot, item)
    listed = {item["path"] for item in files}
    # The workspace root and every member of it hold a pubspec file (AD-808).
    on_disk = _on_disk(fixture, "compass_app/app/lib") | {
        path.relative_to(fixture).as_posix() for path in fixture.rglob("pubspec.yaml")
    }
    assert on_disk <= listed
    assert {path for path in listed if path.endswith(".dart")} == {
        path for path in on_disk if path.endswith(".dart")
    }
    libraries = {item["path"] for item in files if item.get("generated") is False}
    for item in files:
        if item.get("generated") is True:
            stem = item["path"].removesuffix(".freezed.dart").removesuffix(".g.dart")
            assert item["parent_library"] == stem + ".dart"
            assert item["parent_library"] in libraries


def test_python_snapshot_matches_the_files_and_the_upstream_tree() -> None:
    fixture = ROOT / "fixtures/K-python-realworld"
    snapshot = _snapshot("fixtures/K-python-realworld/SNAPSHOT.json")
    upstream = snapshot["upstream_tree"]
    for row in upstream:
        _source_identity(snapshot, {**row, "source_path": row["path"]})
        assert row["selected"] == (row["selection_reason"] != "excluded_from_fixture_scope")
    upstream_by_path = {row["path"]: row["git_blob_sha1"] for row in upstream}
    selected = snapshot["files"]
    for item in selected:
        payload = (fixture / item["path"]).read_bytes()
        assert _sha256(fixture / item["path"]) == item["sha256"]
        assert _git_blob_sha1(payload) == upstream_by_path[item["path"]]
        _source_identity(snapshot, {**item, "source_path": item["path"]})
    listed = {item["path"] for item in selected}
    assert _on_disk(fixture, "app") == {path for path in listed if path.startswith("app/")}
    assert {row["path"] for row in upstream if row["selected"]} == listed


def test_nest_snapshot_matches_the_original_derived_and_support_files() -> None:
    fixture = ROOT / "fixtures/L-nest-realworld"
    snapshot = _snapshot("fixtures/L-nest-realworld/SNAPSHOT.json")
    originals = snapshot["original_src_files"]
    derived = snapshot["derived_files"]
    for item in [*originals, *snapshot["support_files"]]:
        assert _sha256(fixture / item["path"]) == item["sha256"]
        _source_identity(snapshot, item)
    for item in derived:
        source, target = fixture / item["source_path"], fixture / item["path"]
        assert source.read_bytes() == target.read_bytes()
        assert _sha256(source) == item["source_sha256"] == item["sha256"]
    assert _on_disk(fixture, "src") == {item["path"] for item in [*originals, *derived]}


def test_nest_resolver_inputs_are_pinned() -> None:
    fixture = ROOT / "fixtures/L-nest-realworld"
    provenance = _snapshot("fixtures/L-nest-realworld/resolver-inputs/provenance.json")
    packages = provenance["packages"]
    for package in packages:
        assert package["tarball_integrity"].startswith("sha512-")
        for record in [*package["files"], package["license_file"]]:
            path = fixture / "resolver-inputs" / record["path"]
            assert path.stat().st_size == record["size"]
            assert _sha256(path) == record["sha256"]
