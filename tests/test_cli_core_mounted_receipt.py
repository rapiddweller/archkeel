# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-470: the receipt of a mounted `complete_requires` reads the modules of its mount.

Each expected row is the row of release 4.0.1 on the same plant (`rule_assessments`).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_cli_core_only_scan import command

COMPONENT = {
    "role": "component",
    "responsibilities": ["Own."],
    "forbidden_responsibilities": [],
    "provenance": ["README.md"],
    "decided_by": "architect",
}
RULE = {"rationale": "Keep it.", "provenance": ["README.md"], "decided_by": "architect"}
ONE = {
    "src/a/x/one.ts": "export const one = 1;\n",
    "src/a/y/two.ts": "import { one } from '../x/one';\nexport const two = one;\n",
}
CROSS = (
    "import { one } from '../x/one';\nimport { t } from '../../b/t';\nexport const two = one + t;\n"
)


def component(
    name: str, packages: list[str], requires: tuple[str, ...] = (), **extra: Any
) -> dict[str, Any]:
    return {
        **COMPONENT,
        "id": name.upper(),
        "label": name,
        "packages": packages,
        "requires": [{"component": other, "rationale": "Use it."} for other in requires],
        **extra,
    }


def inner(*more: dict[str, Any], requires: tuple[str, ...] = ("ax",)) -> list[dict[str, Any]]:
    return [component("ax", ["app.src.a.x"]), component("ay", ["app.src.a.y"], requires), *more]


PARENT = component("a", ["app.src.a"], inside="inside.json")
CASES: dict[str, tuple[dict[str, str], list[dict[str, Any]], dict[str, Any], str]] = {
    "pass": (ONE, inner(), PARENT, "PASS"),
    "fail": (ONE, inner(requires=()), PARENT, "FAIL"),
    "unowned-inside": (
        {**ONE, "src/a/z/three.ts": "export const z = 3;\n"},
        inner(),
        PARENT,
        "UNKNOWN",
    ),
    "double-inside": (ONE, inner(component("axx", ["app.src.a.x"])), PARENT, "UNKNOWN"),
    "cross-boundary": (
        {**ONE, "src/a/y/two.ts": CROSS},
        inner(),
        component("a", ["app.src.a"], ("b",), inside="inside.json"),
        "PASS",
    ),
    "parent-exact-outside": (
        {**ONE, "lib/extra.ts": "export const e = 1;\n"},
        inner(),
        {**PARENT, "exact_modules": ["app.lib.extra"]},
        "UNKNOWN",
    ),
    "parent-package-unseen": (
        ONE,
        inner(),
        component("a", ["app.src.a", "app.gone"], inside="inside.json"),
        "UNKNOWN",
    ),
}


def project(root: Path, files: dict[str, str], mounted: list[dict[str, Any]], parent: dict) -> Path:
    base = {
        "README.md": "x\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
        "src/b/t.ts": "export const t = 1;\n",
    }
    for name, text in {**base, **files}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
    )
    rules = [{**RULE, "id": "REQUIRES", "kind": "complete_requires"}]
    contract = {"schema_version": "2.2.0", "components": [parent, component("b", ["app.src.b"])]}
    (root / "architecture-contract.json").write_text(json.dumps({**contract, "rules": rules}))
    inside = {"schema_version": "2.2.0", "components": mounted}
    rules = [{**RULE, "id": "IN-REQ", "kind": "complete_requires"}]
    (root / "inside.json").write_text(json.dumps({**inside, "rules": rules}))
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


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_mounted_complete_requires_row_equals_the_release_row(
    release_core: Path, tmp_path: Path, case: str
) -> None:
    files, mounted, parent, expected = CASES[case]
    done = command(release_core, project(tmp_path, files, mounted, parent), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    rows = {rule: row[1] for rule, row in result["frame"]["rules"].items()}
    assert rows["a:IN-REQ"] == expected, result["frame"]["explained"]
