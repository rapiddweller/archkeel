# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Explorer snapshot carries the entry points that manifests and files prove (#2040)."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from corpus_support import commit_tree

from archkeel.cli import core_explorer, core_only
from archkeel.cli.core_arguments import Options
from archkeel.cli.core_binding import ProjectRoot
from archkeel.cli.core_frame import CoreCommand, CoreFrame
from archkeel.explorer_queries import populate, query
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _scan(root: Path, built: Path) -> list[dict[str, Any]]:
    """The `explorer` parts of the contract-free scan of a committed tree."""
    commit_tree(root)
    names = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    digests = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in names
        if not name.startswith(".git/")
    }

    def scan(target: ProjectRoot) -> tuple[bytes, CoreFrame]:
        options = Options(
            command=CoreCommand.REPORT, config=target.config, topology=True, explorer=True
        )
        return core_only._exchange_scan(options, target, built / "archkeel-core", [])

    stdout, _ = core_explorer._observed_scan(ProjectRoot.of(root, None), digests, scan)
    parts: list[dict[str, Any]] = json.loads(stdout)["explorer"]
    return parts


def _entries(parts: list[dict[str, Any]]) -> list[tuple[str, str, str, str | None, str | None]]:
    assert len(parts) == 1
    return [
        (e["kind"], e["basis"], e["name"], e["evidence"]["path"], e["evidence"]["key"])
        for e in parts[0]["entry_points"]["entries"]
    ]


def test_python_scripts_and_a_main_module_each_cite_their_evidence(
    tmp_path: Path, built: Path
) -> None:
    (tmp_path / "src/app").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "0.1"\nrequires-python = ">=3.11"\n'
        '[project.scripts]\napp-cli = "app.cli:main"\n'
        '[project.gui-scripts]\napp-gui = "app.gui:run"\n'
    )
    (tmp_path / "src/app/__init__.py").write_text("")
    (tmp_path / "src/app/cli.py").write_text("def main():\n    return 1\n")
    (tmp_path / "src/app/__main__.py").write_text("from app import cli\ncli.main()\n")
    parts = _scan(tmp_path, built)
    assert _entries(parts) == [
        ("python_script", "declared", "app-cli", "pyproject.toml", "project.scripts.app-cli"),
        (
            "python_gui_script",
            "declared",
            "app-gui",
            "pyproject.toml",
            "project.gui-scripts.app-gui",
        ),
        ("python_main_module", "observed", "app.__main__", "src/app/__main__.py", None),
    ]
    assert parts[0]["entry_points"]["unread"] == []


def test_a_real_python_project_without_entry_evidence_is_not_given_a_guess(
    tmp_path: Path, built: Path
) -> None:
    """The pinned FastAPI project declares no script and has no `__main__.py`."""
    root = tmp_path / "k"
    shutil.copytree(FIXTURES / "K-python-realworld", root)
    parts = _scan(root, built)
    assert parts[0]["entry_points"] == {"entries": [], "unread": []}


def test_an_unreadable_pyproject_makes_the_list_unknown(tmp_path: Path, built: Path) -> None:
    (tmp_path / "src/app").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[project.scripts]\napp = 3\n")
    (tmp_path / "src/app/__init__.py").write_text("")
    (tmp_path / "src/app/a.py").write_text("x = 1\n")
    entry_points = _scan(tmp_path, built)[0]["entry_points"]
    assert entry_points["entries"] == []
    assert entry_points["unread"] == ["pyproject.toml: project.scripts.app is not a string"]


def test_rust_bin_targets_are_declared_and_default_files_are_observed(
    tmp_path: Path, built: Path
) -> None:
    for crate, manifest in {
        "app": '[[bin]]\nname = "tool"\npath = "src/tool_main.rs"\n',
        "core": "",
    }.items():
        (tmp_path / f"crates/{crate}/src/bin").mkdir(parents=True)
        (tmp_path / f"crates/{crate}/Cargo.toml").write_text(
            f'[package]\nname = "{crate}"\nversion = "0.1.0"\nedition = "2021"\n{manifest}'
        )
        (tmp_path / f"crates/{crate}/src/lib.rs").write_text("pub fn f() {}\n")
    (tmp_path / "Cargo.toml").write_text('[workspace]\nmembers = ["crates/app", "crates/core"]\n')
    for name in ("main.rs", "tool_main.rs", "bin/extra.rs"):
        (tmp_path / "crates/app/src" / name).write_text("fn main() {}\n")
    parts = _scan(tmp_path, built)
    assert sorted(_entries(parts)) == [
        ("cargo_bin", "declared", "tool", "crates/app/Cargo.toml", "bin.name=tool"),
        ("cargo_bin", "observed", "app", "crates/app/src/main.rs", None),
        ("cargo_bin", "observed", "extra", "crates/app/src/bin/extra.rs", None),
    ]


def test_package_json_bin_and_main_are_declared(tmp_path: Path, built: Path) -> None:
    root = tmp_path / "ts"
    shutil.copytree(FIXTURES / "H-typescript", root)
    manifest = json.loads((root / "package.json").read_text())
    manifest.update({"main": "dist/index.js", "bin": {"shop": "bin/shop.js"}})
    (root / "package.json").write_text(json.dumps(manifest))
    assert _entries(_scan(root, built)) == [
        ("package_bin", "declared", "shop", "package.json", "bin.shop"),
        ("package_main", "declared", "archkeel-typescript-shop", "package.json", "main"),
    ]


def test_the_snapshot_passes_the_entry_points_on_and_keeps_unknown_unknown(
    tmp_path: Path,
) -> None:
    """The shell adds no entry point: a part without the key stays null, not an empty list."""
    entry = {
        "kind": "python_script",
        "basis": "declared",
        "name": "tool",
        "target": "pkg:main",
        "evidence": {"path": "pyproject.toml", "key": "project.scripts.tool"},
    }
    topology: dict[str, Any] = {
        "version": 1,
        "complete": True,
        "truncated": False,
        "gaps": [],
        "components": [],
        "modules": [],
        "edges": [],
        "explorer": [
            {"language": "python", "files": [], "entry_points": {"entries": [entry], "unread": []}},
            {"language": "dart", "files": [], "entry_points": None},
        ],
    }
    path = tmp_path / "cache" / "sample.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("r", "c", "s"),
        lambda db: populate(db, topology, tmp_path),
        "partial",
    )
    overview: Any = query(path, tmp_path, "overview", {})
    parts = overview["coverage"]["parts"]
    assert parts[0]["entry_points"] == {"entries": [entry], "unread": []}
    assert parts[1]["entry_points"] is None
