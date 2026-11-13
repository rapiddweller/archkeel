# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issues #976 and #988: a source that reaches a forbidden module in a skipped way gives no PASS.

Consumer: `archkeel validate` on a TypeScript project: the default path through the core. The
contract lets `a` use nothing, so any edge from `a` to `b` fails it. Each probe is a source that
reaches `b` from `a` by a construct that a collector once read as no dependency: a `/// <reference
types>` line, a `declare module` augmentation (by a relative name, or by a bare name that `paths`
or `baseUrl` maps to a project file), and a use of `self.x` or `frames.x` for a global that a
script of `b` publishes through `window.x` (also through `this`, which is the global object in a
classic script). The honest cases (no such line, and a bare name that no alias maps) must still
give PASS, so that the probes test the contract and not a broken fixture. Each probe must give an
edge (FAIL) or a gap (UNKNOWN), never PASS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree

from archkeel.cli import core_only

CONTRACT = {
    "schema_version": "2.2.0",
    "components": [
        {
            "id": f"COMP-{name.upper()}",
            "label": name,
            "role": "component",
            "packages": [f"app.src.{name}"],
            "public": [f"app.src.{name}"],
            "responsibilities": [f"Hold {name}."],
            "forbidden_responsibilities": [],
            "provenance": ["README.md"],
            "requires": [],
            "decided_by": "architect",
        }
        for name in ("a", "b")
    ],
    "rules": [
        {
            "id": "REQUIRES",
            "kind": "complete_requires",
            "rationale": "a uses nothing.",
            "provenance": ["README.md"],
            "decided_by": "architect",
        },
        {
            "id": "ASSIGNMENT",
            "kind": "complete_assignment",
            "source": "app",
            "rationale": "Every module has a component.",
            "provenance": ["README.md"],
            "decided_by": "architect",
        },
    ],
}
BASE = {
    "tsconfig.json": '{"compilerOptions":{"allowJs":true},"include":["src"]}',
    "archkeel.toml": (
        '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
    ),
    "architecture-contract.json": json.dumps(CONTRACT),
    "README.md": "# probe\n",
    "src/b/t.ts": "export type T = number;\n",
}
ALIASES = '{"compilerOptions":{"allowJs":true,"baseUrl":".","paths":{"@b/*":["src/b/*"]}}}'
TYPE_ROOTS = '{"compilerOptions":{"allowJs":true,"typeRoots":["./src"]},"include":["src"]}'
BASE_URL = '{"compilerOptions":{"allowJs":true,"baseUrl":"."},"include":["src"]}'
AUGMENT = 'export {};\ndeclare module "NAME" { interface Q {} }\n'
CASES = {
    "honest": {"src/a/a.ts": "export const a = 1;\n"},
    # A bare name that no alias can map to a project file stays silent.
    "bare-augmentation-without-aliases": {
        "src/a/a.ts": AUGMENT.replace("NAME", "express"),
    },
    "reference-types": {"src/a/a.ts": '/// <reference types="../b/t" />\nexport const a = 1;\n'},
    "module-augmentation": {"src/a/a.ts": 'declare module "../b/t" {}\nexport const a = 1;\n'},
    "self-as-script-root": {
        "src/a/a.js": "self.x();\n",
        "src/b/b.js": "window.x = 1;\n",
    },
    # `this` is the global object in a classic script, at the top level and in a plain call (#988).
    "this-alias-in-a-function": {
        "src/a/a.js": "function f() { var self = this; self.x(); }\n",
        "src/b/b.js": "window.x = 1;\n",
    },
    "this-at-the-top-level": {
        "src/a/a.js": "this.x();\n",
        "src/b/b.js": "window.x = 1;\n",
    },
    "amd-dependency": {
        "src/a/a.ts": '/// <amd-dependency path="../b/t" />\nexport const a = 1;\n',
    },
    # A type root inside the project lets `types="b"` name a directory of the project (#988).
    "type-root-in-the-project": {
        "tsconfig.json": TYPE_ROOTS,
        "src/b/index.d.ts": "declare var fromB: number;\n",
        "src/a/a.ts": '/// <reference types="b" />\nexport const a = fromB;\n',
    },
    "edge-and-effect-gap": {
        "src/a/a.ts": 'import type { T } from "../b/t";\nexport type X = T;\n',
        "src/a/g.js": "this.x();\n",
    },
    # The window outside a frame: a use through `top` or `parent` is never silent (#988).
    "top-as-script-root": {
        "src/a/a.js": "top.x();\n",
        "src/b/b.js": "window.x = 1;\n",
    },
    "parent-as-script-root": {
        "src/a/a.js": "parent.x();\n",
        "src/b/b.js": "window.x = 1;\n",
    },
    # A directive reads its attributes in any order and any case, as tsc does (#988).
    "amd-dependency-with-the-name-first": {
        "src/a/a.ts": '/// <amd-dependency name="n" path="../b/t" />\nexport const a = 1;\n',
    },
    "amd-dependency-in-capitals": {
        "src/a/a.ts": '/// <AMD-DEPENDENCY PATH="../b/t" />\nexport const a = 1;\n',
    },
    "reference-with-an-attribute-first": {
        "src/a/a.ts": '/// <reference preserve="true" path="../b/t.ts" />\nexport const a = 1;\n',
    },
    "frames-as-script-root": {
        "src/a/a.js": "frames.x();\n",
        "src/b/b.js": "window.x = 1;\n",
    },
    # tsc resolves the name of an augmentation through `paths` and `baseUrl` (#976).
    "augmentation-through-paths": {
        "tsconfig.json": ALIASES,
        "src/a/a.ts": AUGMENT.replace("NAME", "@b/t"),
    },
    "augmentation-through-base-url": {
        "tsconfig.json": BASE_URL,
        "src/a/a.ts": AUGMENT.replace("NAME", "src/b/t"),
    },
    "augmentation-in-a-declaration-file": {
        "tsconfig.json": ALIASES,
        "src/a/a.d.ts": AUGMENT.replace("NAME", "@b/t"),
    },
}
# A chain of aliases of the global object is a use of the global object (#1007).
CHAINS = (
    "window.window",
    "self.window",
    "globalThis.window",
    "window.self",
    "window.globalThis",
    "top.window",
    "parent.top",
    "frames.self.window",
)
CASES.update(
    {
        f"alias-chain-{chain}": {"src/a/a.js": f"{chain}.x();\n", "src/b/b.js": "window.x = 1;\n"}
        for chain in CHAINS
    }
)
# An alias, a destructuring or a call receiver that is a chain of aliases is as much a use of the
# global object as the one-alias form (#1007).
CHAIN_USES = {
    "const-alias-of-top": "const w = window.top;\nw.x();\n",
    "const-alias-of-a-chain": "const w = window.window;\nw.x();\n",
    "destructuring-of-a-chain": "const { x } = window.self;\nx();\n",
    "destructuring-of-parent-window": "const { x } = parent.window;\nx();\n",
    "var-alias-of-a-chain": "var w = top.self;\nw.x();\n",
    "function-alias-of-a-chain": "var f = window.self;\nf.x();\n",
    "parenthesized-chain-receiver": "(window.self).x();\n",
}
CASES.update(
    {
        f"alias-use-{name}": {"src/a/a.js": text, "src/b/b.js": "window.x = 1;\n"}
        for name, text in CHAIN_USES.items()
    }
)
HONEST = ("honest", "bare-augmentation-without-aliases")


def _project(tmp_path: Path, name: str) -> Path:
    root = tmp_path / "repo"
    for rel, text in {**BASE, **CASES[name]}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    commit_tree(root)
    return root


def _verdict(tmp_path: Path, name: str, binary: Path) -> tuple[int, dict[str, Any]]:
    """The exit code and the result document of the default `validate` on the project."""
    root = _project(tmp_path, name)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: binary)
        return run("validate", "--root", str(root))


def _requires(document: dict[str, Any]) -> str | None:
    row = document.get("frame", {}).get("rules", {}).get("REQUIRES")
    return row[1] if row else None


@pytest.mark.parametrize("name", HONEST)
def test_an_honest_project_gives_pass(tmp_path: Path, core_binary: Path, name: str) -> None:
    code, document = _verdict(tmp_path, name, core_binary)

    assert (code, document["status"]) == (0, "PASS")
    assert {row[1] for row in document["frame"]["rules"].values()} == {"PASS"}


@pytest.mark.parametrize("name", [name for name in CASES if name not in HONEST])
def test_a_construct_that_reaches_a_forbidden_module_gives_no_pass(
    tmp_path: Path, core_binary: Path, name: str
) -> None:
    # An incomplete scan makes the exit code 2 whatever a rule says, so the rule itself is read: a
    # REQUIRES that passes beside an incomplete scan is a PASS for the edge a -> b (#988).
    code, document = _verdict(tmp_path, name, core_binary)

    assert code in {1, 2}, f"{name}: PASS"
    assert document["status"] != "PASS", name
    # A crash or an invalid reply ends the scan as a refusal: no verdict, not an UNKNOWN.
    assert "refusal" not in document, f"{name}: {document.get('refusal')}"
    status = _requires(document)
    assert status in {None, "FAIL", "UNKNOWN"}, f"{name}: REQUIRES is {status}"
    if status is None:
        # The core gives no row for a rule that it cannot decide: a gap names the rule.
        assert [gap for gap in document["gaps"] if gap["subject"] == "REQUIRES"], name


def test_a_real_edge_stays_fail_beside_an_effect_gap_in_another_file(
    tmp_path: Path, core_binary: Path
) -> None:
    # A runtime-effect gap makes a PASS impossible; it must not turn a found violation into UNKNOWN.
    code, document = _verdict(tmp_path, "edge-and-effect-gap", core_binary)

    assert _requires(document) == "FAIL", document["frame"]["rules"]
    assert code == 1
