# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issues #976 and #988: a source that reaches a forbidden module in a skipped way gives no PASS.

Consumer: the host (`run_report`), with the Python collector and with the bundled native one. The
contract lets `a` use nothing, so any edge from `a` to `b` fails it. Each probe is a source that
reaches `b` from `a` by a construct that both producers read as no dependency: a `/// <reference
types>` line, a `declare module` augmentation (by a relative name, or by a bare name that `paths`
or `baseUrl` maps to a project file), and a use of `self.x` or `frames.x` for a global that a
script of `b` publishes through `window.x` (also through `this`, which is the global object in a
classic script). The honest cases (no such line, and a bare name that no alias maps) must still
give PASS, so that the probes test the contract and not a broken fixture. Each probe must give an
edge (FAIL) or a gap (UNKNOWN) in both producers, never PASS.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_collector_native_verdicts import _commit, _verdict, bundled_directory  # noqa: F401

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
# global object as the one-alias form (#1007). The first two crashed the Python collector.
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
    _commit(root)
    return root


def _verdicts(tmp_path: Path, name: str, directory: Path) -> list[dict[str, object]]:
    root = _project(tmp_path, name)
    return [_verdict(root, None), _verdict(root, None, directory)]


@pytest.mark.parametrize("name", HONEST)
def test_an_honest_project_gives_pass_in_both_producers(
    tmp_path: Path,
    bundled_directory: Path,  # noqa: F811
    name: str,
) -> None:
    assert [item["exit"] for item in _verdicts(tmp_path, name, bundled_directory)] == [0, 0]


@pytest.mark.parametrize("name", [name for name in CASES if name not in HONEST])
def test_a_construct_that_reaches_a_forbidden_module_gives_no_pass(
    tmp_path: Path,
    bundled_directory: Path,  # noqa: F811
    name: str,
) -> None:
    # An incomplete scan makes the exit code 2 whatever a rule says, so the rule itself is read: a
    # REQUIRES that passes beside an incomplete scan is a PASS for the edge a -> b (#988).
    found = _verdicts(tmp_path, name, bundled_directory)
    for producer, item in zip(("Python", "native"), found, strict=True):
        assert item["exit"] != 0, f"{name}: the {producer} collector gives PASS"
        # A crash or an invalid reply ends the scan as a parse error: no verdict, not an UNKNOWN.
        assert "parse_error" not in item["diagnostics"], f"{name}: {producer}: no valid reply"  # type: ignore[operator]
        requires = dict(item["rules"]).get("REQUIRES")  # type: ignore[call-overload]
        assert requires != "PASS", f"{name}: REQUIRES passes with the {producer} collector"


def test_a_real_edge_stays_fail_beside_an_effect_gap_in_another_file(
    tmp_path: Path,
    bundled_directory: Path,  # noqa: F811
) -> None:
    # A runtime-effect gap makes a PASS impossible; it must not turn a found violation into UNKNOWN.
    found = _verdicts(tmp_path, "edge-and-effect-gap", bundled_directory)
    for producer, item in zip(("Python", "native"), found, strict=True):
        assert dict(item["rules"]).get("REQUIRES") == "FAIL", f"{producer}: {item['rules']}"  # type: ignore[call-overload]
