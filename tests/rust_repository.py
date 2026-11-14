# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build a small Cargo workspace with an Archkeel contract, and validate it with the core.

Consumer: the tests of the Rust profile (AD-335). The workspace has two crates, `base` and `app`,
below `crates/`. A test changes the sources or the contract and reads the verdict of the core.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree

from archkeel.cli import core_only

WORKSPACE = """[workspace]
members = ["base", "app"]
"""
BASE = """[package]
name = "base-crate"
version = "0.0.0"
edition = "2021"
"""
APP = """[package]
name = "app"
version = "0.0.0"
edition = "2021"
[dependencies]
base-crate = { path = "../base" }
"""
BASE_SOURCE = "pub fn make() {}\n"
APP_SOURCE = "use base_crate::make;\npub fn run() { make(); }\n"
GRAPH_PAGE = """# Target

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
{edges}
```
"""
PROVENANCE = ["docs/target.md"]


def component(label: str, crate: str, requires: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [f"native.{crate}"],
        "responsibilities": ["Own this crate."],
        "forbidden_responsibilities": [],
        "provenance": PROVENANCE,
        "requires": [
            {"component": name, "rationale": f"The {label} crate calls into the {name} crate."}
            for name in requires
        ],
        "decided_by": "architect",
    }


def rule(identifier: str, kind: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": kind,
        "rationale": "The fixture states this rule.",
        "provenance": PROVENANCE,
        "decided_by": "architect",
        **fields,
    }


_CORES: dict[Path, Path] = {}
CRATE_RULES = (
    rule("ASSIGNED", "complete_assignment", source="native"),
    rule("REQUIRES", "complete_requires"),
    rule("NO-CYCLES", "no_component_cycles"),
)


def repository(
    root: Path,
    binary: Path,
    files: dict[str, str] | None = None,
    components: tuple[dict[str, Any], ...] | None = None,
    rules: tuple[dict[str, Any], ...] = CRATE_RULES,
) -> Path:
    """Write the fixture below `root`. A file in `files` replaces or adds a file of the default.

    `binary` is the core that decides the fixture (the `core_binary` fixture).
    """
    assert binary.is_file(), binary
    _CORES[root.resolve()] = binary
    sources = {
        "crates/Cargo.toml": WORKSPACE,
        "crates/base/Cargo.toml": BASE,
        "crates/base/src/lib.rs": BASE_SOURCE,
        "crates/app/Cargo.toml": APP,
        "crates/app/src/lib.rs": APP_SOURCE,
        **(files or {}),
    }
    parts = components or (
        component("base", "base_crate"),
        component("app", "app", ("base",)),
    )
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    edges = "\n".join(
        f"    {part['label']} --> {need['component']}"
        for part in parts
        for need in part["requires"]
    )
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/target.md").write_text(GRAPH_PAGE.format(edges=edges or "    base"))
    contract = {"schema_version": "2.1.0", "components": list(parts), "rules": list(rules)}
    (root / "architecture-contract.json").write_text(json.dumps(contract, indent=2))
    (root / "archkeel.toml").write_text(
        "[scan]\n"
        'language = "rust"\n'
        'roots = ["crates"]\n'
        'namespace = "native"\n'
        'contract = "architecture-contract.json"\n'
    )
    commit_tree(root)
    return root


def validate(root: Path, capsys: pytest.CaptureFixture[str] | None = None) -> dict[str, Any]:
    """Run `archkeel validate --json` on the fixture and return the result document."""
    return _run(root, "validate")


def report(root: Path, capsys: pytest.CaptureFixture[str] | None = None) -> dict[str, Any]:
    """Run `archkeel report --json` on the fixture and return the result document."""
    return _run(root, "report")


def _run(root: Path, command: str) -> dict[str, Any]:
    return outcome(root, command)[1]


def outcome(root: Path, command: str = "validate") -> tuple[int, dict[str, Any]]:
    """The exit code and the result document of `archkeel <command> --json` on the fixture."""
    binary = _CORES[root.resolve()]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: binary)
        return run(command, "--root", str(root))


def statuses(result: dict[str, Any]) -> dict[str, str]:
    """The status of each rule by id."""
    return {name: row[1] for name, row in result.get("frame", {}).get("rules", {}).items()}


def claims(result: dict[str, Any]) -> list[str]:
    """Each thing the run reports: the violations, the gaps, the source gaps and the refusal."""
    frame = result.get("frame", {})
    found = [
        f"{name}: {row['source']} -> {row['target']}: {row['cause']}"
        for name, rows in frame.get("details", {}).items()
        for row in rows
    ]
    found += [f"{gap['kind']}: {gap['subject']}: {gap['reason']}" for gap in result.get("gaps", ())]
    found += [
        f"{gap['kind']}: {', '.join(gap['subjects'])}: {gap['reason']}"
        for gap in frame.get("collection_gaps", ())
    ]
    found += [f"{name}: {reason}" for name, reason in frame.get("explained", {}).items()]
    if "refusal" in result:
        found.append(f"{result['refusal']['kind']}: {result['refusal']['message']}")
    return found
