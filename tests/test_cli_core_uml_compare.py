# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-494: the core compares the module and import part of a UML target.

Each plant is a TypeScript tree with a UML target; `EXPECTED` gives the row of release 4.0.1
on the same tree and the row of the core, which is equal or stricter.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_cli_core_only_scan import command

ROW = "UML-TARGET-a2e40c5592b1b06a"
PROVENANCE = ["README.md"]
ONE = "app.src.a.one_x2e_ts"
TWO = "app.src.a.two_x2e_ts"
T = "app.src.b.t_x2e_ts"


def component(name: str, packages: list[str], requires: tuple[str, ...] = (), **extra: Any) -> dict:
    return {
        "id": name.upper(),
        "label": name,
        "role": "component",
        "packages": packages,
        "responsibilities": ["Own."],
        "forbidden_responsibilities": [],
        "provenance": PROVENANCE,
        "decided_by": "architect",
        "requires": [{"component": other, "rationale": "Use it."} for other in requires],
        **extra,
    }


def module(identity: str, name: str, language: str = "typescript") -> dict:
    return {
        "id": identity,
        "kind": "module",
        "qualified_name": name,
        "language": language,
        "presence": "planned",
        "provenance": PROVENANCE,
        "responsibilities": ["Hold it."],
    }


def imports(identity: str, source: str, target: str) -> dict:
    return {
        "id": identity,
        "kind": "imports",
        "source_id": source,
        "target_id": target,
        "provenance": PROVENANCE,
    }


def scope(entity: str, entity_kinds: list[str], relationship_kinds: list[str]) -> dict:
    return {
        "scope_id": entity,
        "mode": "closed",
        "rationale": "Keep it closed.",
        "provenance": PROVENANCE,
        "entity_kinds": entity_kinds,
        "relationship_kinds": relationship_kinds,
    }


IMPORTING = "import { t } from '../b/t';\nexport const one = t;\n"
FILES = {"src/a/one.ts": IMPORTING, "src/b/t.ts": "export const t = 1;\n"}
BASE = {
    "entities": [module("one", ONE), module("t", T)],
    "relationships": [imports("one-t", "one", "t")],
    "scopes": [],
}


def target(**change: Any) -> dict:
    return {"schema_version": "1.1.0", **BASE, **change}


# name: (files, UML target, inside target or None, row of 4.0.1, row of the core)
PLANTS: dict[str, tuple[dict[str, str], dict | None, dict | None, str, str]] = {
    "pass": (FILES, target(), None, "PASS", "PASS"),
    "missing-edge": (
        {**FILES, "src/a/one.ts": "export const one = 1;\n"},
        target(),
        None,
        "FAIL",
        "FAIL",
    ),
    "extra-edge": (
        FILES,
        target(relationships=[], scopes=[scope("one", [], ["imports"])]),
        None,
        "FAIL",
        "FAIL",
    ),
    "extra-module": (
        {**FILES, "src/a/two.ts": "export const two = 2;\n"},
        target(
            entities=[*BASE["entities"], {**module("pkg-a", "app.src.a"), "kind": "package"}],
            scopes=[scope("pkg-a", ["module"], [])],
        ),
        None,
        "FAIL",
        "FAIL",
    ),
    "component-scope": (
        {**FILES, "src/a/two.ts": "export const two = 2;\n"},
        target(scopes=[scope("A", ["module"], [])]),
        None,
        "UNKNOWN",
        "UNKNOWN",
    ),
    "renamed-module": (
        FILES,
        target(entities=[module("one", "app.src.a.renamed_x2e_ts"), module("t", T)]),
        None,
        "UNKNOWN",
        "UNKNOWN",
    ),
    "other-language": (
        FILES,
        target(entities=[module("one", ONE, "python"), module("t", T)]),
        None,
        "UNKNOWN",
        "UNKNOWN",
    ),
    "class-entity": (
        FILES,
        target(entities=[*BASE["entities"], {**module("k", f"{ONE}.K"), "kind": "class"}]),
        None,
        "UNKNOWN",
        "UNKNOWN",
    ),
    "pass-incomplete": (
        {**FILES, "src/b/bad.ts": "export const = ;\n"},
        target(),
        None,
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-edge-incomplete": (
        {**FILES, "src/a/one.ts": "export const one = 1;\n", "src/b/bad.ts": "export const = ;\n"},
        target(),
        None,
        "UNKNOWN",
        "UNKNOWN",
    ),
    "open-scope-missing": (
        FILES,
        target(
            # A referenced entity has no assessment of its own; only the scope reads it.
            entities=[
                *BASE["entities"],
                {**module("gone", "app.src.a.gone_x2e_ts"), "presence": "referenced"},
            ],
            scopes=[{**scope("gone", ["module"], ["imports"]), "mode": "open"}],
        ),
        None,
        "UNKNOWN",
        "UNKNOWN",
    ),
    "closed-listed": (
        FILES,
        target(
            entities=[*BASE["entities"], {**module("pkg-a", "app.src.a"), "kind": "package"}],
            scopes=[scope("pkg-a", ["module"], [])],
        ),
        None,
        "UNKNOWN",
        "UNKNOWN",
    ),
    # 4.0.1 passes a target of a mount; the core does not compare it (stricter).
    "mounted-target": (FILES, None, target(), "PASS", "UNKNOWN"),
}


def project(root: Path, files: dict[str, str], uml: dict | None, inner: dict | None) -> Path:
    # AD-466: the provenance file draws the component graph of the imports.
    edge = "    n_0 --> n_1\n" if "../b/t" in files.get("src/a/one.ts", "") else ""
    graph = (
        "# Provenance\n\n<!-- archkeel-component-graph -->\n```mermaid\nflowchart LR\n"
        f'    n_0["a"]\n    n_1["b"]\n{edge}```\n'
    )
    base = {"README.md": graph, "tsconfig.json": '{"compilerOptions": {"strict": true}}\n'}
    for name, text in {**base, **files}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
    )
    rules = [
        {
            "id": "REQUIRES",
            "kind": "complete_requires",
            "rationale": "Keep it.",
            "provenance": PROVENANCE,
            "decided_by": "architect",
        }
    ]
    parent = component("a", ["app.src.a"], ("b",))
    if inner is not None:
        parent["inside"] = "inside.json"
        inside = {
            "schema_version": "2.2.0",
            "components": [component("ax", ["app.src.a"])],
            "rules": [],
            "declarations": {"uml": inner},
        }
        (root / "inside.json").write_text(json.dumps(inside))
    contract: dict[str, Any] = {
        "schema_version": "2.2.0",
        "components": [parent, component("b", ["app.src.b"])],
        "rules": rules,
    }
    if uml is not None:
        contract["declarations"] = {"uml": uml}
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)
    return root


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_uml_row_is_the_release_row_or_stricter(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    files, uml, inner, _, expected = PLANTS[name]
    done = command(release_core, project(tmp_path, files, uml, inner), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    assert result["frame"]["rules"][ROW] == ["uml_target", expected], result["frame"]["explained"]
    if expected == "FAIL":
        assert result["frame"]["details"][ROW], result["frame"]
        assert done.returncode == 1
    if expected == "PASS":
        assert result["status"] == "PASS" and done.returncode == 0, result["frame"]


def test_a_missing_provenance_file_of_the_target_refuses_the_contract(
    release_core: Path, tmp_path: Path
) -> None:
    uml = target(
        entities=[{**module("one", ONE), "provenance": ["docs/missing.md"]}, module("t", T)]
    )
    done = command(release_core, project(tmp_path, FILES, uml, None), "--json")
    result = json.loads(done.stdout)
    refusal = result["frame"]["unsupported"]["rules"]
    assert refusal.startswith("contract hygiene reference.provenance"), refusal
    assert done.returncode == 2
