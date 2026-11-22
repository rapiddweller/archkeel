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
import shutil
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
from test_cli_python_trojan_horse_reach import GIT

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
        ("same-line", "UNKNOWN"),
        ("include", "UNKNOWN"),
        ("inside", "UNKNOWN"),
        ("system", "PASS"),
        ("system-open", "PASS"),
        ("exclusive", "FAIL"),
    ],
)
def test_computed_imports_use_declared_possible_targets(
    release_core: Path, tmp_path: Path, case: str, status: str
) -> None:
    source = "export const load = (name: string) => import(name);\n"
    if case in {"open", "same-line"}:
        other = "export const other = (name: string) => import(name);\n"
        source = source + other if case == "open" else source.rstrip() + " " + other
    if case == "exclusive":
        source = "export const load = mode => mode === 'left' && import('../b/' + 'secret.mjs');\n"
    files = {"src/a/one.ts": source, "src/b/secret.ts": "export {};\n"}
    if case == "forbidden":
        files["src/b/secret.ts"] = "import '../a/one';\n"
    if case == "exclusive":
        files["src/b/secret.ts"] = (
            "export const load = mode => mode === 'right' && import('../a/' + 'one.mjs');\n"
        )
    if case == "include":
        files["tsconfig.json"] = json.dumps({"include": ["src/a/one.ts", "src/b/secret.ts"]})
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
    loads = {
        "forbidden": ["app.src.b"],
        "missing": [T, "app.src.b.gone_x2e_ts"],
        "exclusive": [secret],
    }.get(case, [T])
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
    if case == "exclusive":
        first = contract["declarations"]["door_reach"][0]
        contract["declarations"]["door_reach"].append(
            {**first, "id": "D-RETURN", "module": secret, "loads": [ONE]}
        )
    if case == "inside":
        outer = contract["components"][0]
        inside = {
            "schema_version": "3.15.0",
            "components": [{**outer, "id": "INNER", "label": "inner", "requires": []}],
            "rules": [],
            "declarations": contract.pop("declarations"),
        }
        outer["inside"] = "inside.json"
        (root / "inside.json").write_text(json.dumps(inside))
    path.write_text(json.dumps(contract))
    options = ()
    if case in {"system", "system-open"}:
        part = {
            "id": "web",
            "title": "Web",
            "config": "archkeel.toml",
            "responsibilities": ["Check the web code."],
            "forbidden_responsibilities": ["Check code outside this part."],
            "provides": ["The web verdict."],
        }
        parts = [part]
        if case == "system-open":
            config = (root / "archkeel.toml").read_text()
            (root / "open.toml").write_text(
                config.replace('namespace = "app"', 'namespace = "open"').replace(
                    '"architecture-contract.json"', '"open.json"'
                )
            )
            other = json.loads(json.dumps(contract).replace("app.src.", "open.src."))
            other.pop("declarations")
            for row in [*other["rules"], *other["components"]]:
                row["id"] = f"OPEN-{row['id']}"
            (root / "open.json").write_text(json.dumps(other))
            parts.append({**part, "id": "open", "title": "Open", "config": "open.toml"})
        document = {
            "schema_version": "archkeel-system-contract-1",
            "kind": "system",
            "title": "Fixture",
            "parts": parts,
            "interfaces": [],
            "rules": [],
        }
        (root / "system.json").write_text(json.dumps(document))
        options = ("--config", "system.json")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, env=GIT)
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "reach"], check=True, env=GIT)
    done = command(release_core, root, "--json", "--topology", *options, verb="report")
    result = json.loads(done.stdout)
    assert "frame" in result, result
    frame = result["frame"]
    assert frame["rules"]["NO-SECRET"] == ["forbidden_dependency", status], result
    assert frame["rules"]["NO-CYCLE"] == ["no_component_cycles", status], result
    assert not [edge for edge in frame["topology"]["edges"] if edge["source"] == ONE]
    problems = {
        "missing": "trojan_horse_reach.invalid",
        "scope": "trojan_horse_reach.unmatched",
        "same-line": "trojan_horse_reach.ambiguous",
        "include": "trojan_horse_reach.invalid",
        "inside": "trojan_horse_reach.inside",
    }
    if case in problems:
        assert "trojan_horse_reach" not in frame
        assert any(gap["kind"] == problems[case] for gap in result["gaps"]), result["gaps"]
    else:
        reach = frame["trojan_horse_reach"][0]
        assert reach["loads"] == loads
        expected = {"forbidden": [secret, T], "exclusive": [secret]}.get(case, [T])
        assert reach["possible_loads"] == expected
    if case in {"allowed", "system"}:
        assert frame["assumed"]["NO-SECRET"] == [f"D-IMPORT ({ONE}:1 loader)"]
        assert frame["topology"]["requires"][0]["imports"] == 0
        assert result["status"] == "PASS", result
    if case == "system":
        assert frame["system"]["parts"][0]["id"] == "web"
        assert frame["premises"]["NO-SECRET"][0]["kind"] == "trojan_horse_reach"
        text = command(release_core, root, "--text", *options).stdout
        assert "PASS under 1 declared reach" in text
        assert "Possible targets: app.src.b.t.ts" in text
        target = tmp_path / "system.html"
        command(release_core, root, "--output", str(target), *options, verb="report")
        assert "PASS UNDER 1 DECLARED REACH" in target.read_text()
    if case == "system-open":
        assert result["status"] == "UNKNOWN", result
        assert frame["rules"]["OPEN-NO-SECRET"] == ["forbidden_dependency", "UNKNOWN"]
        assert "OPEN-NO-SECRET" not in frame["premises"]
        assert frame["assumed"]["NO-SECRET"] == [f"D-IMPORT ({ONE}:1 loader)"]
        assert len(frame["trojan_horse_reach"]) == 1
    if case == "forbidden":
        assert {(edge["source"], edge["target"]) for edge in frame["topology"]["edges"]} == {
            (secret, ONE)
        }
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
        assert "NO-CYCLE: contract graph cycle" in text
        assert "the contract declares this possibility" in text
        assert "PASS under" not in text
        page_path = tmp_path / "report.html"
        command(release_core, root, "--output", str(page_path), "--format", "html", verb="report")
        page = page_path.read_text()
        assert "MAY IMPORT" in page
        assert "Declared possible import:" in page
        assert "Contract graph cycle" in page
        assert "not evidence that the imports execute together" in page
    if case == "exclusive":
        assert frame["topology"]["edges"] == []
        (cycle,) = frame["details"]["NO-CYCLE"]
        assert {(edge["from"], edge["to"]) for edge in cycle["path"] if edge.get("possible")} == {
            (ONE, secret),
            (secret, ONE),
        }
        if node := shutil.which("node"):
            # Run the same fixture bodies as ES modules without a TypeScript compiler.
            for path in ("a/one", "b/secret"):
                runtime = root / "src" / f"{path}.mjs"
                runtime.write_text(files[f"src/{path}.ts"])
            script = """
const a = await import('./src/a/one.mjs');
const b = await import('./src/b/secret.mjs');
const mode = process.argv[1];
console.log(JSON.stringify([Boolean(await a.load(mode)), Boolean(await b.load(mode))]));
"""
            for mode, expected in (("left", [True, False]), ("right", [False, True])):
                ran = subprocess.run(
                    [node, "--input-type=module", "-e", script, "--", mode],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                assert json.loads(ran.stdout) == expected
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
