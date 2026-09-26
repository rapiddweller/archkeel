# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise report-flow production functions directly with the installed Node runtime."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from test_analyzer import _component, _observe

from archkeel.render.flow import build_flow
from archkeel.render.html import _flow_payload

FLOW_JS = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"


def _run_flow_js(script: str) -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js 22+ is required for report-flow acceptance tests"
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout
    assert int(version.removeprefix("v").split(".", 1)[0]) >= 22, version
    result = subprocess.run(
        [node, "-e", script, str(FLOW_JS)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_import_only_package_initializer_stays_openable() -> None:
    _run_flow_js(
        r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function rootPackage(");
const end = text.indexOf("  // The declared names a module publishes", begin);
const DATA = {modules: {
  pkg: {symbols: [], imports: ["pkg.api.users"]},
  "pkg.api.users": {symbols: [{}]}, "pkg.api.orders": {symbols: [{}]},
  "pkg.apiary.tools": {symbols: [{}]}, "pkg.util": {symbols: [{}]},
}};
const {rootPackage, cardLevel} = new Function("DATA", text.slice(begin, end) +
  ";return {rootPackage, cardLevel}")(DATA);
const component = {modules: Object.keys(DATA.modules), public: null, inner_edges: [
  {source: "pkg", target: "pkg.api.users", import_sites: 1, state: "observed"},
]};
assert.equal(rootPackage(component.modules), "pkg");
const root = cardLevel(component, []);
const init = root.components.find(card => card.label === "pkg:__init__");
assert(init, "an imports-only package initializer must remain visible");
assert.equal(init.folder, false);
assert.equal(init.openable, true);
assert.equal(init.opensModule, "pkg");
assert.deepEqual(init.modules, ["pkg"]);
assert.deepEqual(cardLevel(component, ["pkg.api"]).components.map(card => card.label),
  ["pkg.api.orders", "pkg.api.users"]);
assert(!cardLevel(component, ["pkg.api"]).components.some(
  card => card.label.startsWith("pkg.apiary")));
"""
    )


def test_package_initializer_with_definitions_opens_as_a_module() -> None:
    _run_flow_js(
        r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function rootPackage(");
const end = text.indexOf("  // The declared names a module publishes", begin);
const DATA = {modules: {
  "pkg.core": {symbols: [{kind: "class"}, {kind: "function"}]},
  "pkg.core.api.module": {symbols: [{}]},
}};
const {cardLevel} = new Function("DATA", text.slice(begin, end) +
  ";return {cardLevel}")(DATA);
const component = {modules: Object.keys(DATA.modules), public: null, inner_edges: []};
const card = cardLevel(component, []).components.find(item => item.label === "pkg.core:__init__");
assert(card, "a package initializer with definitions must remain visible");
assert.equal(card.folder, false);
assert.equal(card.openable, true);
assert.equal(card.opensModule, "pkg.core");
assert.deepEqual(card.modules, ["pkg.core"]);
"""
    )


def test_common_prefix_stops_at_first_different_package_segment() -> None:
    _run_flow_js(
        r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function rootPackage(");
const end = text.indexOf("  // The declared names a module publishes", begin);
const {rootPackage, cardLevel} = new Function("DATA", text.slice(begin, end) +
  ";return {rootPackage, cardLevel}")({modules: {}});
const component = {modules: ["pkg.a.api", "pkg.b.api"], public: null, inner_edges: []};
assert.equal(rootPackage(component.modules), "pkg");
assert.deepEqual(cardLevel(component, []).components.map(card => card.label), ["pkg.a", "pkg.b"]);
"""
    )


def test_inside_navigation_retains_deep_isolated_and_unassigned_modules() -> None:
    _run_flow_js(
        r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function insideLevel(");
const end = text.indexOf("  // The declared names a module publishes", begin);
const names = ["pkg.core.unit.alpha", "pkg.core.unit.deep.leaf",
  "pkg.core.unit.deep.nested.tail", "pkg.core.unit.isolated", "pkg.core.loose"];
const DATA = {modules: Object.fromEntries(names.map(name => [name, {symbols: []}]))};
const {insideLevel, cardLevel} = new Function("DATA", text.slice(begin, end) +
  ";return {insideLevel, cardLevel}")(DATA);
const assigned = {label: "unit", modules: names.slice(0, 4), public: null};
const view = insideLevel({components: [assigned], edges: [], unassigned: [names[4]]});
const orphan = view.components.find(card => card.label === names[4]);
assert(orphan, "an unassigned isolated module must have a navigation card");
assert.equal(orphan.openable, true);
assert.equal(orphan.opensModule, names[4]);

const reached = new Set();
function visit(path) {
  for (const card of cardLevel(assigned, path).components) {
    if (!card.folder && card.opensModule) reached.add(card.opensModule);
    if (card.folder) visit([...path, card.label]);
  }
}
visit([]);
assert.deepEqual([...reached].sort(), names.slice(0, 4).sort());
"""
    )


def test_same_inside_child_labels_keep_parent_evidence_separate() -> None:
    _run_flow_js(
        r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const scopeStart = text.indexOf("  function insideScope()");
const scopeEnd = text.indexOf("  function rootPackage(", scopeStart);
const DATA = {components: [
  {label: "core", inside: {components: [{label: "api", modules: ["pkg.core.api"], public: null}],
    edges: [{source: "api", target: "storage", import_sites: 1,
      state: "violation", rule_ids: ["CORE-RULE"]}], unassigned: []}},
  {label: "service", inside: {components: [
    {label: "api", modules: ["pkg.service.api"], public: null}],
    edges: [{source: "api", target: "storage", import_sites: 2,
      state: "violation", rule_ids: ["SERVICE-RULE"]}], unassigned: []}},
]};
const viewFor = new Function("DATA", "moduleLevel", "cardLevel",
  "let opened; const componentByLabel = new Map(DATA.components.map(c => [c.label, c]));" +
  text.slice(scopeStart, scopeEnd) +
  ";return parent => {opened = {component: parent, path: []}; return fullLevel();}")(
    DATA, () => ({components: [], edges: []}), () => ({components: [], edges: []}));
for (const [parent, expected] of [["core", "CORE-RULE"], ["service", "SERVICE-RULE"]]) {
  const view = viewFor(parent);
  assert.deepEqual(view.components.map(card => card.label), ["api"]);
  assert.deepEqual(view.edges.map(edge => edge.rule_ids), [[expected]]);
}
"""
    )


def test_inside_import_site_evidence_is_scoped_to_its_parent_level(tmp_path: Path) -> None:
    def inner_contract(parent: str) -> dict[str, object]:
        return {
            "schema_version": "2.1.0",
            "components": [
                {
                    "id": f"COMP-{parent.upper()}-A",
                    "label": "a",
                    "role": "component",
                    "packages": [f"sample.{parent}.a"],
                    "responsibilities": [],
                    "forbidden_responsibilities": [],
                    "provenance": ["docs/architecture/sample.md"],
                },
                {
                    "id": f"COMP-{parent.upper()}-B",
                    "label": "b",
                    "role": "component",
                    "packages": [f"sample.{parent}.b"],
                    "responsibilities": [],
                    "forbidden_responsibilities": [],
                    "provenance": ["docs/architecture/sample.md"],
                },
            ],
            "rules": [],
        }

    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component("core") | {"inside": "core-inner.json"},
                    _component("service") | {"inside": "service-inner.json"},
                ],
                "rules": [],
            }
        )
    )
    for parent in ("core", "service"):
        (tmp_path / f"{parent}-inner.json").write_text(json.dumps(inner_contract(parent)))
        package = tmp_path / "sample" / parent
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        for child in ("a", "b"):
            child_package = package / child
            child_package.mkdir()
            (child_package / "__init__.py").write_text("")
        (package / "a.py").write_text(f"import sample.{parent}.b\n")
        (package / "b.py").write_text("")

    result = _observe(tmp_path)
    assert result.observation is not None
    payload = _flow_payload(result.observation, build_flow(result.observation))
    by_parent = {item["label"]: item["inside"] for item in payload["components"]}
    for parent in ("core", "service"):
        edges = by_parent[parent]["edges"]
        assert len(edges) == 1
        assert edges[0]["source"] == "a"
        assert edges[0]["target"] == "b"
        assert edges[0]["sites"] == [f"sample/{parent}/a.py:1"]


def test_symbol_use_edges_do_not_claim_import_site_counts() -> None:
    _run_flow_js(
        r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function moduleLevel(");
const end = text.indexOf("  // AD-24: the first tap", begin);
const DATA = {modules: {"pkg.mod": {symbols: [], edges: [
  {source: "pkg.mod.caller", target: "pkg.mod.callee"},
]}}};
const {moduleLevel} = new Function("DATA", text.slice(begin, end) +
  ";return {moduleLevel}")(DATA);
const edge = moduleLevel("pkg.mod").edges[0];
assert.equal(edge.state, "observed");
assert.equal(Object.hasOwn(edge, "import_sites"), false);
"""
    )
