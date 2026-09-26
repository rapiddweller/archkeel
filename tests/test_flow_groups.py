# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise the browser's package aggregation without adding a JS dependency."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from test_analyzer import _component, _inside_component, _observe

from archkeel.render.flow import build_flow
from archkeel.render.html import _flow_payload


def _node() -> str:
    node = shutil.which("node")
    assert node is not None, "Node.js 22 is required for flow browser tests"
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True)
    major = int(version.stdout.removeprefix("v").split(".", 1)[0])
    assert major >= 22, f"Node.js 22+ is required, found {version.stdout.strip()}"
    return node


def test_package_groups_keep_import_totals_and_violations() -> None:
    node = _node()
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function rootPackage(");
const end = text.indexOf("  // The declared names a module publishes", begin);
assert(begin >= 0 && end > begin);
const DATA = {modules: {
  pkg: {symbols: []}, "pkg.api": {symbols: []},
  "pkg.api.users": {symbols: [{}]}, "pkg.api.orders": {symbols: [{}]},
  "pkg.util": {symbols: [{}]},
}};
const {rootPackage, cardLevel} = new Function("DATA", text.slice(begin, end) +
  ";return {rootPackage, cardLevel}")(DATA);
const component = {
  modules: ["pkg", "pkg.api", "pkg.api.users", "pkg.api.orders", "pkg.util"],
  public: ["pkg.api.users"],
  inner_edges: [
    {source: "pkg.api.users", target: "pkg.util", import_sites: 2, state: "observed"},
    {source: "pkg.api.orders", target: "pkg.util", import_sites: 3,
      state: "violation", rule_ids: ["R1"]},
  ],
};
const root = cardLevel(component, []);
assert.deepEqual(root.components.map(card => card.label), ["pkg:__init__", "pkg.api", "pkg.util"]);
assert.equal(root.components[1].folder, true);
assert.equal(root.components[1].modules.length, 3);
assert.equal(root.components[1].public.length, 1);
assert.equal(root.edges.length, 1);
assert.equal(root.edges[0].import_sites, 5);
assert.equal(root.edges[0].state, "violation");
assert.deepEqual(root.edges[0].rule_ids, ["R1"]);
assert.deepEqual(cardLevel(component, ["pkg.api"]).components.map(card => card.label),
  ["pkg.api:__init__", "pkg.api.orders", "pkg.api.users"]);
DATA.modules.pkg.symbols = [{}];
assert(cardLevel(component, []).components.some(card => card.label === "pkg:__init__"));
component.public = null;
assert(cardLevel(component, []).components.every(card => card.public === null));
assert.equal(rootPackage(["pkg.a.api", "pkg.b.api"]), "pkg");
const importsOnly = {modules: {
  pkg: {symbols: [], imports: ["pkg.api.users"]},
  "pkg.api.users": {symbols: [{}]}, "pkg.api.orders": {symbols: [{}]},
}};
const onlyCardLevel = new Function("DATA", text.slice(begin, end) +
  ";return cardLevel")(importsOnly);
const initializer = onlyCardLevel({modules: Object.keys(importsOnly.modules),
  public: null, inner_edges: []}, []).components.find(card => card.label === "pkg:__init__");
assert(initializer, "an imports-only initializer remains reachable");
assert.equal(initializer.folder, false);
assert.equal(initializer.openable, true);
assert.equal(initializer.opensModule, "pkg");
const insideBegin = text.indexOf("  function insideLevel(");
const insideEnd = text.indexOf("  function rootPackage(", insideBegin);
assert(insideBegin >= 0 && insideEnd > insideBegin);
const inside = new Function("DATA", text.slice(insideBegin, insideEnd) +
  ";return insideLevel")(importsOnly);
const [orphan] = inside({components: [], edges: [], unassigned: ["pkg"]}).components;
assert.deepEqual(orphan.modules, ["pkg"]);
assert.equal(orphan.openable, true);
assert.equal(orphan.opensModule, "pkg");
"""
    result = subprocess.run(
        [node, "-e", script, str(source)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_analyzer_payload_keeps_unassigned_and_import_only_modules_navigable(
    tmp_path: Path,
) -> None:
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component("library:json", packages=["sample.owned"]),
                    _component("Unassigned modules", packages=["sample.other"]),
                ],
                "rules": [
                    {
                        "id": "JSON-OWNED",
                        "kind": "external_dependency_scope",
                        "dependency": "json",
                        "exact_sources": ["sample.owned"],
                        "rationale": "Owned source rule.",
                        "provenance": ["docs/architecture/owned.md"],
                        "decided_by": "architect",
                    },
                    {
                        "id": "JSON-OTHER",
                        "kind": "external_dependency_scope",
                        "dependency": "json",
                        "exact_sources": ["sample.other"],
                        "rationale": "Other source rule.",
                        "provenance": ["docs/architecture/other.md"],
                        "decided_by": "agent",
                    },
                ],
            }
        )
    )
    package = tmp_path / "sample"
    (package / "owned").mkdir(parents=True)
    (package / "other").mkdir(parents=True)
    (package / "__init__.py").write_text("import sample.engine\n")
    (package / "engine.py").write_text("VALUE = 1\n")
    (package / "owned/__init__.py").write_text("import json\n")
    (package / "owned/api.py").write_text("VALUE = 2\n")
    (package / "other/__init__.py").write_text("import json\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    observation = result.observation
    flow = build_flow(observation)
    payload = _flow_payload(observation, flow)

    assert set(flow.modules) >= {
        "sample",
        "sample.engine",
        "sample.owned",
        "sample.owned.api",
    }
    assert set(payload["unassigned"]["modules"]) == {"sample", "sample.engine"}
    assert payload["unassigned"]["navigation_only"] is True
    assert payload["unassigned"]["inner_edges"][0]["state"] == "observed"
    assert payload["unassigned"]["inner_edges"][0]["rule_ids"] == []
    assert payload["unassigned"]["label"] != "Unassigned modules"
    assert {item["label"] for item in payload["components"]} == {
        "library:json",
        "Unassigned modules",
    }
    assert len(payload["libraries"]) == 1
    library = payload["libraries"][0]
    assert library["label"] != "library:json"
    assert [rule["rule_id"] for rule in library["rules"]] == ["JSON-OTHER", "JSON-OWNED"]
    assert {rule["rationale"] for rule in library["rules"]} == {
        "Other source rule.",
        "Owned source rule.",
    }
    assert {rule["decided_by"] for rule in library["rules"]} == {"agent", "architect"}
    assert {tuple(rule["exact_sources"]) for rule in library["rules"]} == {
        ("sample.other",),
        ("sample.owned",),
    }
    assert {tuple(rule["provenance"]) for rule in library["rules"]} == {
        ("docs/architecture/other.md",),
        ("docs/architecture/owned.md",),
    }
    assert {edge["target"] for edge in payload["edges"] if edge["library"]} == {
        library["label"],
    }
    assert {tuple(edge["rule_ids"]) for edge in payload["edges"] if edge["library"]} == {
        ("JSON-OTHER",),
        ("JSON-OWNED",),
    }

    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const source = fs.readFileSync(process.argv[1], "utf8");
const data = JSON.parse(fs.readFileSync(0, "utf8"));
const begin = source.indexOf("  function rootPackage(");
const end = source.indexOf("  // The declared names a module publishes", begin);
assert(begin >= 0 && end > begin);
const {cardLevel} = new Function("DATA", source.slice(begin, end) + ";return {cardLevel}")(data);
const groups = cardLevel(data.unassigned, []).components;
assert(groups.some(card => card.label === "sample:__init__" && card.openable));
assert(groups.some(card => card.label === "sample.engine" && card.openable));
assert.notEqual(data.unassigned.label, "Unassigned modules");
assert.equal(data.libraries.length, 1);
assert.notEqual(data.libraries[0].label, "library:json");
assert.deepEqual(data.libraries[0].rules.map(rule => rule.rule_id), ["JSON-OTHER", "JSON-OWNED"]);
"""
    completed = subprocess.run(
        [_node(), "-e", script, str(source)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_root_library_projection_excludes_inside_only_scopes(tmp_path: Path) -> None:
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("core") | {"inside": "inner.json"}],
                "rules": [],
            }
        )
    )
    (tmp_path / "inner.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_inside_component("api", []), _inside_component("other", [])],
                "rules": [
                    {
                        "id": "INNER-JSON",
                        "kind": "external_dependency_scope",
                        "dependency": "json",
                        "exact_sources": ["sample.core.other"],
                        "rationale": "Keep the JSON use local to this inside.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    package = tmp_path / "sample/core"
    package.mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (package / "api.py").write_text("VALUE = 1\n")
    (package / "other.py").write_text("import json\n")

    result = _observe(tmp_path)
    assert result.observation is not None
    payload = _flow_payload(result.observation, build_flow(result.observation))

    assert payload["libraries"] == []
    assert not any(edge.get("library") for edge in payload["edges"])


def test_component_and_module_site_pairs_use_distinct_keys(tmp_path: Path) -> None:
    components = [
        _component("sample.a", packages=["sample.left"]) | {"id": "COMP-A"},
        _component("sample.b", packages=["sample.right"]) | {"id": "COMP-B"},
    ]
    (tmp_path / "contract.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": components, "rules": []})
    )
    for package in ("left", "right"):
        folder = tmp_path / f"sample/{package}"
        folder.mkdir(parents=True)
        (folder / "__init__.py").write_text(
            "import sample.right\n" if package == "left" else "VALUE = 1\n"
        )
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/a.py").write_text("import sample.b\n")
    (tmp_path / "sample/b.py").write_text("VALUE = 1\n")

    result = _observe(tmp_path)
    assert result.observation is not None
    flow = build_flow(result.observation)
    payload = _flow_payload(result.observation, flow)

    [root_edge] = [
        edge
        for edge in payload["edges"]
        if (edge["source"], edge["target"]) == ("sample.a", "sample.b")
    ]
    assert root_edge["sites"] == ["sample/left/__init__.py:1"]
    assert payload["unassigned"]["inner_edges"][0]["sites"] == ["sample/a.py:1"]
