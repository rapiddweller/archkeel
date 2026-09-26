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


def test_deep_isolated_and_ownerless_modules_remain_reachable() -> None:
    node = _node()
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function rootPackage(");
const end = text.indexOf("  // The declared names a module publishes", begin);
assert(begin >= 0 && end > begin);
const names = ["pkg", "pkg.deep", "pkg.deep.leaf", "pkg.deep.other", "solo", "unowned.nested.leaf"];
const DATA = {modules: Object.fromEntries(names.map(name => [name, {
  symbols: [], imports: [], exports: [], edges: [],
}]))};
const {cardLevel} = new Function("DATA", text.slice(begin, end) + ";return {cardLevel}")(DATA);
function reachableModules(component) {
  const reached = new Set();
  function visit(path) {
    for (const card of cardLevel(component, path).components) {
      if (card.folder) visit([...path, card.label]);
      else if (card.openable && card.opensModule) reached.add(card.opensModule);
    }
  }
  visit([]);
  return reached;
}
const owned = {label: "owned", modules: names.slice(0, 5), public: null, inner_edges: []};
const unassigned = {label: "unassigned", modules: [names[5]], public: null, inner_edges: []};
assert.deepEqual([...reachableModules(owned)].sort(), names.slice(0, 5).sort());
assert.deepEqual([...reachableModules(unassigned)].sort(), [names[5]]);
"""
    result = subprocess.run(
        [node, "-e", script, str(source)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_structure_reports_zero_modules_for_an_empty_module_group() -> None:
    node = _node()
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function renderStructure(view)");
const end = text.indexOf("  function renderReview(view)", begin);
assert(begin >= 0 && end > begin);
const alternative = {innerHTML: ""};
const makeRenderer = () => new Function("alternative", "selected", "opened", "splitMap", "esc",
  text.slice(begin, end) + ";return renderStructure")(
    alternative, null, null,
    mapped => mapped.map((item, index) => ({item, x: index, y: 0, width: 100, height: 100})),
    String,
  );
const renderStructure = makeRenderer();
renderStructure({components: [
  {label: "one", display: "one", modules: ["pkg.one"], library: false}
]});
assert(alternative.innerHTML.includes("1 observed modules"), alternative.innerHTML);
renderStructure({components: [{label: "empty", display: "empty", modules: [], library: false}]});
assert(alternative.innerHTML.includes("0 observed modules"), alternative.innerHTML);
assert(!alternative.innerHTML.includes("1 observed modules"), alternative.innerHTML);
"""
    result = subprocess.run(
        [node, "-e", script, str(source)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_component_inspector_lists_all_connections_independent_of_focus() -> None:
    node = _node()
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function renderInspector(visible)");
const end = text.indexOf("  function legendSwatch(state)", begin);
assert(begin >= 0 && end > begin);
function render(componentLabel, allEdges, focusedEdges) {
  const component = {label: componentLabel, modules: [], public: null, requires: []};
  const inspector = {innerHTML: ""};
  const selected = {type: "node", label: componentLabel};
  const view = {components: [component], edges: focusedEdges};
  const complete = {components: [component], edges: allEdges};
  const renderInspector = new Function(
    "selected", "showOverview", "level", "fullLevel", "esc", "opened",
    "componentByLabel", "moduleTree", "DATA", "scopeRules", "scopeRuleList", "inspector",
    text.slice(begin, end) + ";return renderInspector",
  )(
    selected, () => {}, () => view, () => complete, String, null,
    new Map(), () => "", {}, () => [], () => "", inspector,
  );
  renderInspector([]);
  return inspector.innerHTML;
}
const outbound = Array.from({length: 6}, (_, i) => ({source: "api", target: `consumer${i}`}));
const inbound = Array.from({length: 6}, (_, i) => ({source: `provider${i}`, target: "api"}));
const allEdges = [...outbound, ...inbound];
// Model a focused diagram that includes only five of each direction.
const focusedEdges = [...outbound.slice(0, 5), ...inbound.slice(0, 5)];
const details = render("api", allEdges, focusedEdges);
const empty = render("isolated", [], []);
assert(empty.includes("<dt>Uses</dt><dd>—</dd>"), empty);
assert(empty.includes("<dt>Used by</dt><dd>—</dd>"), empty);
const missing = [];
if (!details.includes("consumer0, consumer1, consumer2, consumer3, consumer4, consumer5"))
  missing.push("sixth outgoing relationship is absent");
if (!details.includes("provider0, provider1, provider2, provider3, provider4, provider5"))
  missing.push("sixth incoming relationship is absent");
assert.deepEqual(missing, [], details);
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


def test_focused_diagram_keeps_violations_outside_its_top_connections() -> None:
    node = _node()
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function focusLevel(");
const end = text.indexOf("  function level(", begin);
assert(begin >= 0 && end > begin);
const focusLevel = new Function("weight", text.slice(begin, end) + ";return focusLevel")(
  edge => edge.kind === "symbol_use" ? 1 : edge.import_sites);
const names = ["focus", ...Array.from({length: 7}, (_, index) => `used${index}`),
  "brokenSource", "brokenTarget"];
const view = {components: names.map(label => ({label})), edges: [
  ...names.slice(1, 8).map((target, index) =>
    ({source: "focus", target, import_sites: 10 - index, state: "conforms"})),
  {source: "brokenSource", target: "brokenTarget", import_sites: 1, state: "violation"},
]};
const shown = focusLevel(view, "focus");
assert.equal(shown.edges.length, 6);
assert(shown.edges.some(edge => edge.state === "violation"));
assert(shown.components.some(card => card.label === "brokenSource"));
assert(shown.components.some(card => card.label === "brokenTarget"));
assert.equal(focusLevel(view, "missing"), view);
assert.equal(focusLevel(view, null), view);
"""
    result = subprocess.run(
        [node, "-e", script, str(source)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_review_queue_shows_all_flagged_connections_before_busy_clean_ones() -> None:
    node = _node()
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function renderReview(");
const end = text.indexOf("  function renderAlternative(", begin);
assert(begin >= 0 && end > begin);
const alternative = {innerHTML: ""};
const edgeKey = edge => `${edge.source}>${edge.target}`;
const renderReview = new Function(
  "alternative", "selected", "edgeKey", "esc", "weight", "edgeCountLabel",
  text.slice(begin, end) + ";return renderReview")(
    alternative, null, edgeKey, value => String(value),
    edge => edge.kind === "symbol_use" ? 1 : edge.import_sites,
    edge => edge.kind === "symbol_use" ? "symbol-use edge" : `${edge.import_sites} import sites`);
const components = Array.from({length: 16}, (_, index) => ({
  label: `pkg.mod.${index}`, display: `m${index}`,
}));
const edges = components.slice(1).map((target, index) => ({
  source: components[0].label, target: target.label,
  import_sites: index < 13 ? 1 : 200,
  state: index < 12 ? "violation" : index === 12 ? "undecided" : "conforms",
  rule_ids: [], names: [],
}));
renderReview({components, edges});
const firstList = alternative.innerHTML.split("<details><summary>Other connections")[0];
assert.equal((firstList.match(/data-flow-edge=/g) || []).length, 13);
assert(firstList.includes("m0 → m1"));
assert(firstList.includes("m0 → m13"));
assert(!firstList.includes("m0 → m14"));
assert(alternative.innerHTML.includes("Other connections · 2"));
assert(alternative.innerHTML.includes("Dependency matrix · 12 of 16 entries"));
"""
    result = subprocess.run(
        [node, "-e", script, str(source)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_symbol_use_edges_do_not_claim_import_site_counts() -> None:
    node = _node()
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function moduleLevel(");
const end = text.indexOf("  // AD-24: the first tap", begin);
assert(begin >= 0 && end > begin);
const data = {modules: {pkg: {
  symbols: [], edges: [{source: "pkg:caller", target: "pkg:callee"}],
}}};
const moduleLevel = new Function("DATA", text.slice(begin, end) +
  ";return moduleLevel")(data);
const [edge] = moduleLevel("pkg").edges;
assert.equal(edge.kind, "symbol_use");
assert(!Object.hasOwn(edge, "import_sites"));
const countBegin = text.indexOf("  function edgeCountLabel(");
const countEnd = text.indexOf("  function heaviestBlock(", countBegin);
const edgeCountLabel = new Function(text.slice(countBegin, countEnd) +
  ";return edgeCountLabel")();
assert.equal(edgeCountLabel(edge), "symbol-use edge");
"""
    result = subprocess.run(
        [node, "-e", script, str(source)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_scope_counts_use_current_physical_and_symbol_levels() -> None:
    node = _node()
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const begin = text.indexOf("  function statBlock()");
const end = text.indexOf("  function topHeaviestEdges", begin);
assert(begin >= 0 && end > begin);
const run = ({scope, view, opened, owner, data = {modules: {}}}) => {
  const componentByLabel = new Map([["runtime", owner]]);
  const visibleEdges = () => view.edges;
  const statBlock = new Function(
    "fullLevel", "level", "viewMode", "visibleEdges", "opened", "componentByLabel",
    "DATA", "weight",
    text.slice(begin, end) + ";return statBlock",
  )(
    () => scope, () => view, "diagram", visibleEdges, opened, componentByLabel, data,
    edge => edge.kind === "symbol_use" ? 1 : edge.import_sites,
  );
  return statBlock();
};
const folder = run({
  scope: {components: [{label: "runtime.tasks.generate", modules: Array(9).fill("x")}], edges: []},
  view: {components: [{label: "runtime.tasks.generate", modules: Array(9).fill("x")}], edges: []},
  opened: {component: "runtime", path: ["runtime", "tasks"]},
  owner: {modules: Array(51).fill("x")},
});
assert(folder.includes("Modules shown / in this scope</dt><dd>9/9"), folder);
assert(!folder.includes("9/51"), folder);
const module = run({
  scope: {components: [
    {label: "pkg:one", members: ["a", "b"]},
    {label: "pkg:two", members: ["c"]},
    {label: "pkg:three", members: []},
  ], edges: [{kind: "symbol_use"}, {kind: "symbol_use"}]},
  view: {components: [{label: "pkg:one", members: ["a", "b"]}], edges: [{kind: "symbol_use"}]},
  opened: {component: "runtime", module: "pkg"},
  owner: {modules: []},
  data: {modules: {pkg: {exports: [], imports: []}}},
});
assert(module.includes("Symbols shown / in module</dt><dd>1/3"), module);
assert(module.includes("Methods shown / in module</dt><dd>2/3"), module);
assert(module.includes("Symbol-use edges shown / in module</dt><dd>1/2"), module);
"""
    result = subprocess.run(
        [node, "-e", script, str(source)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
