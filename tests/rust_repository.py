# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build a small Cargo workspace with an Archkeel contract, and validate it with the Rust collector.

Consumer: the tests of the native Rust collector (AD-335). The workspace has two crates, `base` and
`app`, below `crates/`. A test changes the sources or the contract and reads the verdict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from collector_pin import pin_of
from graph_report_support import commit_tree

from archkeel.cli import legacy_bindings as cli
from archkeel.cli import main
from archkeel.cli.config import load_config

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
    """Write the fixture below `root`. A file in `files` replaces or adds a file of the default."""
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
        f"collector_argv = {json.dumps([str(binary)])}\n"
    )
    commit_tree(root)
    return root


def validate(root: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """Run `archkeel validate --json` on the fixture and return the result document."""
    return _run(root, capsys, ["validate"])


def report(root: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """Keep rule assessments and written violations beside coverage gaps."""
    return _run(root, capsys, ["report", "--output", str(root / "out" / "architecture.json")])


def _run(root: Path, capsys: pytest.CaptureFixture[str], arguments: list[str]) -> dict[str, Any]:
    capsys.readouterr()
    program = load_config(root).collector_argv[0]  # type: ignore[index]
    build = cli.observer_for
    # A customer config has no pin (AD-344): the test pins the binary that it configured.
    with mock.patch.object(
        cli, "observer_for", lambda *a, **k: build(*a, **k, pinned_digest=pin_of(program))
    ):
        main([*arguments, "--root", str(root), "--json"])
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


def statuses(result: dict[str, Any]) -> dict[str, str]:
    """The status of each rule by id."""
    return {item["id"]: item["status"] for item in result["rule_assessments"] or ()}
