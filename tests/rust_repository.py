# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build a small Cargo workspace with an Archkeel contract, and validate it with the core.

Consumer: the tests of the Rust profile (AD-335). The workspace has two crates, `base` and `app`,
below `crates/`. A test changes the sources or the contract and reads the verdict of the core.
"""

from __future__ import annotations

import json
import os
import subprocess
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
    drawn: str | None = None,
    type_reach: bool | None = None,
    premise: bool = True,
    declared: bool = False,
) -> Path:
    """Write the fixture below `root`. A file in `files` replaces or adds a file of the default.

    `binary` is the core that decides the fixture (the `core_binary` fixture). The marked graph
    draws the `requires` edges, or the edges of `drawn` when the observed edges differ (AD-466).
    `type_reach` turns the compiler type-reach facts on (AD-1047); `None` reads
    `ARCHKEEL_TEST_TYPE_REACH`. The contract then declares the premise `rust_type_reach`, unless
    `premise` is false. `declared` writes the declaration without the flag: a wish, no evidence.
    """
    reach = bool(os.environ.get("ARCHKEEL_TEST_TYPE_REACH")) if type_reach is None else type_reach
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
    edges = edges if drawn is None else drawn
    (root / "docs/target.md").write_text(GRAPH_PAGE.format(edges=edges or "    base"))
    contract: dict[str, Any] = {
        "schema_version": "2.1.0",
        "components": list(parts),
        "rules": list(rules),
    }
    if (reach and premise) or declared:
        contract["schema_version"] = "3.22.0"
        contract["declarations"] = {
            "premises": [
                {
                    "id": "PREMISE-RUST-TYPE-REACH",
                    "name": "rust_type_reach",
                    "rationale": "The fixture is the whole program and builds with its toolchain.",
                    "provenance": PROVENANCE,
                }
            ]
        }
    (root / "architecture-contract.json").write_text(json.dumps(contract, indent=2))
    (root / "archkeel.toml").write_text(
        "[scan]\n"
        'language = "rust"\n'
        'roots = ["crates"]\n'
        'namespace = "native"\n'
        'contract = "architecture-contract.json"\n' + ("rust_type_reach = true\n" if reach else "")
        # AD-1047: `ARCHKEEL_TEST_TYPE_REACH=1` runs each fixture with the compiler type-reach
        # facts, so a plant that must never PASS proves that the filter keeps its real edge.
    )
    # The producer runs `cargo check --locked`; the resolve graph (#2105) needs a lock file too.
    # Cargo never writes one into the scanned repository. No lock: no facts, no graph, UNKNOWN.
    if not (root / "crates/Cargo.lock").exists():
        subprocess.run(
            [
                "cargo",
                "generate-lockfile",
                "--offline",
                "--manifest-path",
                str(root / "crates/Cargo.toml"),
            ],
            check=False,
            capture_output=True,
        )
    commit_tree(root)
    return root


def validate(
    root: Path, capsys: pytest.CaptureFixture[str] | None = None, *, allow_build: bool = True
) -> dict[str, Any]:
    """Run `archkeel validate --json` on the fixture and return the result document."""
    return outcome(root, "validate", allow_build=allow_build)[1]


def report(root: Path, capsys: pytest.CaptureFixture[str] | None = None) -> dict[str, Any]:
    """Run `archkeel report --json` on the fixture and return the result document."""
    return outcome(root, "report")[1]


def outcome(
    root: Path, command: str = "validate", *, allow_build: bool = True
) -> tuple[int, dict[str, Any]]:
    """The exit code and the result document of `archkeel <command> --json` on the fixture.

    AD-1130: the operator allows compilation by the environment. A fixture run allows it unless
    `allow_build` is false.
    """
    binary = _CORES[root.resolve()]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: binary)
        if allow_build:
            patch.setenv("ARCHKEEL_ALLOW_BUILD", "1")
        else:
            patch.delenv("ARCHKEEL_ALLOW_BUILD", raising=False)
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
