# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-536: a TypeScript `import()` stays a counted import and an unbound type import stays a gap.

Consumer: a CI job that reads a TypeScript project whose `one.ts` declares the edge `one -> t`.
Release 4.0.1 counts a lazy `import("../b/t")` as an import, so the UML target row is PASS; the
core must not give FAIL. A type-position `import("../b/t").u` binds no name, so it proves no use
of a public entry of `t`: the core keeps `interface.usage_unknown`, as before AD-536.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_cli_core_only_scan import command
from test_cli_core_uml_review import (
    ONE,
    PROVENANCE,
    ROW,
    RULE,
    TS_MODULES,
    T,
    imports,
    project,
    readme,
    ts,
)
from test_cli_python_door_reach import GIT

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


@pytest.mark.parametrize(
    ("case", "status"),
    [
        ("allowed", "PASS"),
        ("forbidden", "FAIL"),
        ("open", "UNKNOWN"),
        ("missing", "UNKNOWN"),
        ("scope", "UNKNOWN"),
    ],
)
def test_computed_imports_use_declared_possible_targets(
    release_core: Path, tmp_path: Path, case: str, status: str
) -> None:
    source = "export const load = (name: string) => import(name);\n"
    if case == "open":
        source += "export const other = (name: string) => import(name);\n"
    files = {"src/a/one.ts": source, "src/b/secret.ts": "export {};\n"}
    if case == "forbidden":
        files["src/b/secret.ts"] = "import '../a/one';\n"
    plant = ts(TS_MODULES, [], files=files)
    secret = "app.src.b.secret_x2e_ts"
    forbidden = {
        **RULE[0],
        "id": "NO-SECRET",
        "kind": "forbidden_dependency",
        "source": ONE,
        "target": secret,
        "include_type_checking": True,
    }
    cycles = {**RULE[0], "id": "NO-CYCLE", "kind": "no_component_cycles", "level": "module"}
    directions = [
        {
            **RULE[0],
            "id": identity,
            "kind": "allowed_dependency",
            "source": start,
            "target": end,
        }
        for identity, start, end in (
            ("AB", "app.src.a", "app.src.b"),
            ("BA", "app.src.b", "app.src.a"),
        )
    ]
    root = project(tmp_path, plant, [forbidden, cycles, *directions])
    if case == "forbidden":
        (root / "README.md").write_text(readme(True).replace("n_0 --> n_1", "n_1 --> n_0"))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.15.0"
    loads = {"forbidden": ["app.src.b"], "missing": [T, "app.src.b.gone_x2e_ts"]}.get(case, [T])
    contract["declarations"] = {
        "door_reach": [
            {
                "id": "D-IMPORT",
                "module": ONE,
                "door": "loader",
                **({"scope": ""} if case == "scope" else {"line": 1}),
                "loads": loads,
                "rationale": "The caller supplies a name from the registry.",
                "provenance": PROVENANCE,
            }
        ]
    }
    path.write_text(json.dumps(contract))
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "reach"], check=True, env=GIT)
    done = command(release_core, root, "--json", "--topology", verb="report")
    result = json.loads(done.stdout)
    assert "frame" in result, result
    frame = result["frame"]
    assert frame["rules"]["NO-SECRET"] == ["forbidden_dependency", status], result
    assert frame["rules"]["NO-CYCLE"] == ["no_component_cycles", status], result
    assert not [edge for edge in frame["topology"]["edges"] if edge["source"] == ONE]
    if case in {"missing", "scope"}:
        assert "door_reach" not in frame
        problem = "door_reach.invalid" if case == "missing" else "door_reach.unmatched"
        assert any(gap["kind"] == problem for gap in result["gaps"])
    else:
        (reach,) = frame["door_reach"]
        assert reach["loads"] == loads
        assert reach["possible_loads"] == ([secret, T] if case == "forbidden" else [T])
    if case == "allowed":
        assert frame["assumed"]["NO-SECRET"] == [f"D-IMPORT ({ONE}:1 loader)"]
        assert frame["topology"]["requires"][0]["imports"] == 0
        assert result["status"] == "PASS", result
    if case == "forbidden":
        (detail,) = frame["details"]["NO-SECRET"]
        assert (detail["source"], detail["target"]) == (ONE, secret)
        assert detail["possible"] is True
        (evidence,) = detail["evidence"]
        assert frame["locations"][evidence] == {"path": "src/a/one.ts", "line": 1}
        (cycle,) = frame["details"]["NO-CYCLE"]
        assert [(edge["from"], edge["to"]) for edge in cycle["path"] if edge.get("possible")] == [
            (ONE, secret)
        ]
        text = command(release_core, root, "--text").stdout
        assert "Possible targets: app.src.b.secret.ts, app.src.b.t.ts" in text
        assert "PASS assuming" not in text
        page_path = tmp_path / "report.html"
        command(release_core, root, "--output", str(page_path), "--format", "html", verb="report")
        page = page_path.read_text()
        assert "MAY IMPORT" in page
        assert "Declared possible import:" in page
    if status == "UNKNOWN":
        assert "NO-SECRET" not in frame.get("assumed", {})


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
