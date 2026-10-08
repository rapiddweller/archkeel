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


def test_compass_snapshot_preserves_libraries_and_generated_parts() -> None:
    fixture = "fixtures/J-compass"
    snapshot = _snapshot(f"{fixture}/SNAPSHOT.json")
    assert snapshot["repository"] == "flutter/samples"
    assert snapshot["commit"] == "5541c59ab8e9d7e74c1a35ef22bd43a487fc596c"

    files = snapshot["files"]
    dart = [
        item for item in files if item["path"].startswith("lib/") and item["path"].endswith(".dart")
    ]
    generated = [item for item in dart if item.get("generated") is True]
    libraries = [item for item in dart if item.get("generated") is False]
    assert (len(dart), len(libraries), len(generated)) == (111, 89, 22)
    actual_dart = {
        path.relative_to(ROOT / fixture).as_posix()
        for path in (ROOT / fixture / "lib").rglob("*.dart")
    }
    assert actual_dart == {item["path"] for item in dart}

    for item in files:
        target = ROOT / fixture / item["path"]
        assert _sha256(target) == item["sha256"]
        if item["path"].endswith(".dart"):
            assert item["source_url"].startswith(
                "https://github.com/flutter/samples/blob/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c/"
            )
            assert item["source_path"] == "compass_app/app/" + item["path"]
    library_paths = {item["path"] for item in libraries}
    for item in generated:
        assert item["parent_library"] in library_paths
        assert (
            item["parent_library"]
            == item["path"].removesuffix(".freezed.dart").removesuffix(".g.dart") + ".dart"
        )


def test_python_snapshot_preserves_exact_app_and_root_allowlist() -> None:
    fixture = "fixtures/K-python-realworld"
    snapshot = _snapshot(f"{fixture}/SNAPSHOT.json")
    assert snapshot["repository"] == "nsidnev/fastapi-realworld-example-app"
    assert snapshot["commit"] == "029eb7781c60d5f563ee8990a0cbfb79b244538c"
    expected_root = {
        "LICENSE",
        "README.rst",
        "pyproject.toml",
        "setup.cfg",
        "poetry.lock",
        "alembic.ini",
    }
    upstream = snapshot["upstream_tree"]
    assert len(upstream) == 125
    upstream_base = (
        "https://github.com/nsidnev/fastapi-realworld-example-app/blob/"
        "029eb7781c60d5f563ee8990a0cbfb79b244538c/"
    )
    for row in upstream:
        assert row["source_url"] == upstream_base + row["path"]
        assert row["selected"] == (row["selection_reason"] != "excluded_from_fixture_scope")
    assert {
        row["path"] for row in upstream if row["selected"] and not row["path"].startswith("app/")
    } == expected_root

    selected = snapshot["files"]
    app_files = [item for item in selected if item["path"].startswith("app/")]
    python = [item for item in app_files if item["path"].endswith(".py")]
    non_python = [item for item in app_files if not item["path"].endswith(".py")]
    assert (len(app_files), len(python), len(non_python)) == (79, 72, 7)
    actual_app = {
        path.relative_to(ROOT / fixture).as_posix()
        for path in (ROOT / fixture / "app").rglob("*")
        if path.is_file()
    }
    assert actual_app == {item["path"] for item in app_files}
    assert {Path(item["path"]).suffix for item in non_python} == {".sql", ".pyi", ".mako"}
    assert sum(item["path"].endswith(".sql") for item in non_python) == 5
    assert len(selected) == 85
    assert {
        item["path"] for item in selected if not item["path"].startswith("app/")
    } == expected_root

    upstream_by_path = {row["path"]: row["git_blob_sha1"] for row in upstream}
    for item in selected:
        target = ROOT / fixture / item["path"]
        payload = target.read_bytes()
        assert _sha256(target) == item["sha256"]
        assert _git_blob_sha1(payload) == upstream_by_path[item["path"]]
        assert item["source_url"].startswith(
            "https://github.com/nsidnev/fastapi-realworld-example-app/blob/029eb7781c60d5f563ee8990a0cbfb79b244538c/"
        )


def test_nest_snapshot_preserves_original_and_derived_build_inputs() -> None:
    fixture = "fixtures/L-nest-realworld"
    snapshot = _snapshot(f"{fixture}/SNAPSHOT.json")
    assert snapshot["repository"] == "mikro-orm/nestjs-realworld-example-app"
    assert snapshot["commit"] == "a6818d84b6a019cf2df4ef391dc87cea7d02c6a9"

    originals = snapshot["original_src_files"]
    assert len(originals) == 45
    build = [item for item in originals if item["build_input"]]
    excluded = [item for item in originals if not item["build_input"]]
    assert len([item for item in originals if item["path"].endswith(".ts")]) == 42
    assert len(build) == 39
    assert len(excluded) == 6
    expected_excluded = {
        "src/tag/tag.controller.spec.ts",
        "src/user/test/user.controller.spec.ts",
        "src/user/test/user.service.spec.ts",
        "src/config.ts.example",
        "src/mikro-orm.config.ts.example",
        "src/migrations/.snapshot-nestjsrealworld.json",
    }
    assert {item["path"] for item in excluded} == expected_excluded

    derived = snapshot["derived_files"]
    assert {item["source_path"] for item in derived} == {
        "src/config.ts.example",
        "src/mikro-orm.config.ts.example",
    }
    assert len(build) + len(derived) == 41
    actual_src = {
        path.relative_to(ROOT / fixture).as_posix()
        for path in (ROOT / fixture / "src").rglob("*")
        if path.is_file()
    }
    assert actual_src == {item["path"] for item in originals} | {item["path"] for item in derived}

    for item in originals:
        target = ROOT / fixture / item["path"]
        assert _sha256(target) == item["sha256"]
    for item in derived:
        source = ROOT / fixture / item["source_path"]
        target = ROOT / fixture / item["path"]
        assert source.read_bytes() == target.read_bytes()
        assert _sha256(source) == item["source_sha256"] == item["sha256"]

    support = snapshot["support_files"]
    upstream_readme = next(item for item in support if item["source_path"] == "README.md")
    assert upstream_readme["path"] == "UPSTREAM_README.md"
    for item in support:
        target = ROOT / fixture / item["path"]
        assert _sha256(target) == item["sha256"]
        assert item["source_url"].startswith(
            "https://github.com/mikro-orm/nestjs-realworld-example-app/blob/a6818d84b6a019cf2df4ef391dc87cea7d02c6a9/"
        )
