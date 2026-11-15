# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-526: TypeScript trees whose inside contracts draw their own UML target.

Consumer: `test_cli_core_uml_nested.py` and the mutation rows of the same file. `PLANTS` gives, for
each tree, the row of release 4.0.1 (measured on the same tree) and the row of the core.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from test_cli_core_uml_compare import (
    PROVENANCE,
    component,
    imports,
    module,
    scope,
)

ONE = "app.src.a.one_x2e_ts"
TWO = "app.src.a.two_x2e_ts"
DEEP = "app.src.a.deep.d_x2e_ts"
T = "app.src.b.t_x2e_ts"
FILES = {
    "src/a/one.ts": "import { two } from './two';\nimport { t } from '../b/t';\n"
    "export const one = two + t;\n",
    "src/a/two.ts": "export const two = 2;\n",
    "src/a/deep/d.ts": "export const d = 4;\n",
    "src/b/t.ts": "export const t = 1;\n",
}


def target(entities: list[dict], relationships: list[dict] | None = None, **more: Any) -> dict:
    return {
        "schema_version": "1.1.0",
        "entities": entities,
        "relationships": relationships or [],
        "scopes": more.get("scopes", []),
    }


def ent(identity: str, name: str, language: str = "typescript", **more: Any) -> dict:
    return {**module(identity, name, language), **more}


@dataclass
class Plant:
    """One tree: the files, the root target, the target of each level of mounts and the rows."""

    files: dict[str, str] = field(default_factory=lambda: dict(FILES))
    root: dict | None = None
    inside: dict | None = None
    deeper: dict | None = None
    missing_mount: bool = False
    release: str = "PASS"
    core: str = "PASS"


A_TARGET = target(
    [ent("one", ONE), ent("two", TWO)],
    [imports("one-two", "one", "two")],
)
PLANTS: dict[str, Plant] = {
    "nested-equal": Plant(inside=A_TARGET),
    "nested-and-root-equal": Plant(root=target([ent("t", T)]), inside=A_TARGET),
    "one-module-missing": Plant(
        inside=target([ent("one", ONE), ent("two", "app.src.a.gone_x2e_ts")]),
        release="UNKNOWN",
        core="UNKNOWN",
    ),
    "one-import-missing": Plant(
        files={**FILES, "src/a/one.ts": "import { t } from '../b/t';\nexport const one = t;\n"},
        inside=A_TARGET,
        release="FAIL",
        core="FAIL",
    ),
    "one-import-missing-with-root-target": Plant(
        files={**FILES, "src/a/one.ts": "import { t } from '../b/t';\nexport const one = t;\n"},
        root=target([ent("t", T)]),
        inside=A_TARGET,
        release="FAIL",
        core="FAIL",
    ),
    "one-import-extra": Plant(
        inside=target(
            [ent("one", ONE), ent("two", TWO)],
            [],
            scopes=[scope("one", [], ["imports"])],
        ),
        release="FAIL",
        core="FAIL",
    ),
    "inside-element-in-root-only": Plant(
        root=target([ent("two", TWO)]),
        inside=target([ent("one", ONE)]),
    ),
    "module-outside-mount": Plant(
        inside=target([ent("one", ONE), ent("t", T)]),
        release="PASS",
        core="UNKNOWN",
    ),
    "two-mount-levels": Plant(inside=A_TARGET, deeper=target([ent("d", DEEP)])),
    "gap-inside-mount": Plant(
        files={**FILES, "src/a/bad.ts": "export const = ;\n"},
        inside=A_TARGET,
        release="REFUSED",
        core="UNKNOWN",
    ),
    "gap-outside-mount": Plant(
        files={**FILES, "src/b/bad.ts": "export const = ;\n"},
        inside=A_TARGET,
        release="REFUSED",
        core="UNKNOWN",
    ),
    "mount-in-another-language": Plant(
        inside=target([ent("one", ONE, "python"), ent("two", TWO, "python")]),
        release="UNKNOWN",
        core="UNKNOWN",
    ),
    "symbol-element": Plant(
        inside=target([ent("one", ONE), {**ent("k", f"{ONE}.K"), "kind": "class"}]),
        release="UNKNOWN",
        core="UNKNOWN",
    ),
    "same-element-in-two-forms": Plant(
        root=target([{**ent("one", ONE), "kind": "package"}]),
        inside=A_TARGET,
        release="UNKNOWN",
        core="UNKNOWN",
    ),
    # 4.0.1 refuses the tree: "duplicate planned entity".
    "same-element-equal-twice": Plant(
        root=target([ent("one", ONE)]), inside=A_TARGET, release="REFUSED", core="UNKNOWN"
    ),
    "inside-target-without-element": Plant(inside=target([]), release="UNKNOWN", core="UNKNOWN"),
    "mounted-contract-missing": Plant(
        inside=A_TARGET, missing_mount=True, release="REFUSED", core="NO-ROW"
    ),
}


def write(root: Path, plant: Plant) -> Path:
    graph = (
        "# Provenance\n\n<!-- archkeel-component-graph -->\n```mermaid\nflowchart LR\n"
        '    n_0["a"]\n    n_1["b"]\n    n_0 --> n_1\n```\n'
    )
    base = {"README.md": graph, "tsconfig.json": '{"compilerOptions": {"strict": true}}\n'}
    for name, text in {**base, **plant.files}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
    )
    rule = {
        "id": "REQUIRES",
        "kind": "complete_requires",
        "rationale": "Keep it.",
        "provenance": PROVENANCE,
        "decided_by": "architect",
    }
    parent = component("a", ["app.src.a"], ("b",))
    if plant.inside is not None:
        parent["inside"] = "inside.json"
        ax = component("ax", ["app.src.a"])
        if plant.deeper is not None:
            ax["inside"] = "deeper.json"
        inside = {
            "schema_version": "2.2.0",
            "components": [ax],
            "rules": [],
            "declarations": {"uml": plant.inside},
        }
        if not plant.missing_mount:
            (root / "inside.json").write_text(json.dumps(inside))
    if plant.deeper is not None:
        deeper = {
            "schema_version": "2.2.0",
            "components": [component("ay", ["app.src.a.deep"])],
            "rules": [],
            "declarations": {"uml": plant.deeper},
        }
        (root / "deeper.json").write_text(json.dumps(deeper))
    contract: dict[str, Any] = {
        "schema_version": "2.2.0",
        "components": [parent, component("b", ["app.src.b"])],
        "rules": [rule],
    }
    if plant.root is not None:
        contract["declarations"] = {"uml": plant.root}
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
