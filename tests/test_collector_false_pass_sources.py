# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #976: a source that reaches a forbidden module in a way the collector skips gives no PASS.

Consumer: the host (`run_report`), with the Python collector and with the bundled native one. The
contract lets `a` use nothing, so any edge from `a` to `b` fails it. Each probe is a source that
reaches `b` from `a` by a construct that both producers read as no dependency: a `/// <reference
types>` line, a `declare module` augmentation, and a use of `self.x` for a global that a script of
`b` publishes through `window.x`. The honest case (no such line) must still give PASS, so that the
probes test the contract and not a broken fixture. Each probe must give an edge (FAIL) or a gap
(UNKNOWN) in both producers, never PASS.
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
CASES = {
    "honest": {"src/a/a.ts": "export const a = 1;\n"},
    "reference-types": {"src/a/a.ts": '/// <reference types="../b/t" />\nexport const a = 1;\n'},
    "module-augmentation": {"src/a/a.ts": 'declare module "../b/t" {}\nexport const a = 1;\n'},
    "self-as-script-root": {
        "src/a/a.js": "self.x();\n",
        "src/b/b.js": "window.x = 1;\n",
    },
}


def _project(tmp_path: Path, name: str) -> Path:
    root = tmp_path / "repo"
    for rel, text in {**BASE, **CASES[name]}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _commit(root)
    return root


def _exits(tmp_path: Path, name: str, directory: Path) -> tuple[int, int]:
    root = _project(tmp_path, name)
    python = _verdict(root, None)
    native = _verdict(root, None, directory)
    return int(python["exit"]), int(native["exit"])  # type: ignore[call-overload]


def test_the_honest_project_gives_pass_in_both_producers(
    tmp_path: Path,
    bundled_directory: Path,  # noqa: F811
) -> None:
    assert _exits(tmp_path, "honest", bundled_directory) == (0, 0)


@pytest.mark.parametrize("name", [name for name in CASES if name != "honest"])
def test_a_construct_that_reaches_a_forbidden_module_gives_no_pass(
    tmp_path: Path,
    bundled_directory: Path,  # noqa: F811
    name: str,
) -> None:
    python, native = _exits(tmp_path, name, bundled_directory)
    assert python != 0, f"{name}: the Python collector gives PASS"
    assert native != 0, f"{name}: the native collector gives PASS"
