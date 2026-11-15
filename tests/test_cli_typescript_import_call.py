# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-520: a TypeScript `import()` stays a counted import and an unbound type import stays a gap.

Consumer: a CI job that reads a TypeScript project whose `one.ts` declares the edge `one -> t`.
Release 4.0.1 counts a lazy `import("../b/t")` as an import, so the UML target row is PASS; the
core must not give FAIL. A type-position `import("../b/t").u` binds no name, so it proves no use
of a public entry of `t`: the core keeps `interface.usage_unknown`, as before AD-520.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli_core_only_scan import command
from test_cli_core_uml_review import (
    PROVENANCE,
    ROW,
    RULE,
    TS_MODULES,
    T,
    imports,
    project,
    ts,
)

LAZY = {
    "t-dyn-mod": "export const one = import('../b/t');\n",
    "t-dyn-nobind-mod": "import('../b/t');\nexport const one = 1;\n",
    "t-dyn-fn": "export async function go() { return import('../b/t'); }\n",
    "t-dyn-destructure": (
        "export async function go() { const { t } = await import('../b/t'); return t; }\n"
    ),
    "t-dyn-template": "export const one = import(`../b/t`);\n",
}
BOUNDARY = {
    "id": "BOUNDARY",
    "kind": "interface_boundary",
    "rationale": "Callers use the declared interface.",
    "provenance": PROVENANCE,
    "decided_by": "architect",
    "include_type_checking": True,
}
# name: source of one.ts, the public entries of component b, the entries that stay unknown.
TYPES = {
    "t2-typeof-member-fn": (
        "export function go(): number { const x: typeof import('../b/t').u = 2; return x; }\n",
        [f"{T}:t", f"{T}:TT"],
        [f"{T}:t"],
    ),
    "t2-typeof-member-mod": (
        "export const one: typeof import('../b/t').u = 2;\n",
        [f"{T}:t", f"{T}:TT"],
        [f"{T}:t"],
    ),
    "t2-typeof-module-fn": (
        "export function go(): number { type M = typeof import('../b/t');"
        " const x: M['u'] = 2; return x; }\n",
        [f"{T}:t", f"{T}:TT"],
        [f"{T}:t"],
    ),
    "t-importtype-fn": (
        "export function go(): number { const x: import('../b/t').TT = 1; return x; }\n",
        [f"{T}:t", f"{T}:TT"],
        [f"{T}:t"],
    ),
    "t-importtype-expr": (
        "export const one: import('../b/t').TT = 1;\n",
        [T],
        [T],
    ),
    "t-typeof-import": ("export type M = typeof import('../b/t');\n", [T], [T]),
}


@pytest.mark.parametrize("name", sorted(LAZY))
def test_a_lazy_import_meets_a_declared_edge_as_release_4_0_1_does(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    files = {"src/a/one.ts": LAZY[name]}
    plant = ts(TS_MODULES, [imports("one", "t")], files=files)
    result = json.loads(command(release_core, project(tmp_path, plant), "--json").stdout)
    assert "refusal" not in result, result
    assert result["frame"]["rules"][ROW] == ["uml_target", "PASS"], result["frame"].get("explained")


@pytest.mark.parametrize("name", sorted(TYPES))
def test_a_type_import_without_a_name_proves_no_use_of_a_public_entry(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    source, public, unknown = TYPES[name]
    configuration, files, components, target = ts(
        TS_MODULES, [imports("one", "t")], files={"src/a/one.ts": source}
    )
    components = [*components]
    components[1] = {**components[1], "public": public}
    plant = (configuration, files, components, target)
    done = command(release_core, project(tmp_path, plant, [*RULE, BOUNDARY]), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    seen = json.dumps(result["frame"]["unsupported"])
    for entry in unknown:
        assert (
            f"interface.usage_unknown:architecture-contract.json/components/1/public/{public.index(entry)}:{entry}"
            in seen
        )
