# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise report-flow production functions directly with the installed Node runtime."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FLOW_JS = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"


def _run_flow_js(script: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    result = subprocess.run(
        [node, "-e", script, str(FLOW_JS)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_import_only_package_initializer_stays_openable_and_prefixes_are_segmented() -> None:
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
assert.equal(init.opensModule, "pkg");
assert.deepEqual(init.modules, ["pkg"]);
assert.deepEqual(cardLevel(component, ["pkg.api"]).components.map(card => card.label),
  ["pkg.api.orders", "pkg.api.users"]);
assert(!cardLevel(component, ["pkg.api"]).components.some(
  card => card.label.startsWith("pkg.apiary")));
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
const insideStart = text.indexOf("  function insideLevel(");
const insideEnd = text.indexOf("  function rootPackage(", insideStart);
const levelStart = text.indexOf("  function fullLevel(");
const levelEnd = text.indexOf("  function focusLevel(", levelStart);
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
  text.slice(insideStart, insideEnd) + text.slice(levelStart, levelEnd) +
  ";return parent => {opened = {component: parent, path: []}; return fullLevel();}")(
    DATA, () => ({components: [], edges: []}), () => ({components: [], edges: []}));
for (const [parent, expected] of [["core", "CORE-RULE"], ["service", "SERVICE-RULE"]]) {
  const view = viewFor(parent);
  assert.deepEqual(view.components.map(card => card.label), ["api"]);
  assert.deepEqual(view.edges.map(edge => edge.rule_ids), [[expected]]);
}
"""
    )


def test_switching_from_focus_recovers_full_level_and_review_counts_truthfully() -> None:
    _run_flow_js(
        r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const focusStart = text.indexOf("  function focusLevel(");
const focusEnd = text.indexOf("  function defaultFocus(", focusStart);
const levelStart = text.indexOf("  function level(");
const levelEnd = text.indexOf("  function defaultFocus(", levelStart);
const reviewStart = text.indexOf("  function renderReview(");
const reviewEnd = text.indexOf("  function renderAlternative(", reviewStart);
const focusLevel = new Function(text.slice(focusStart, focusEnd) + ";return focusLevel")();
const getLevel = new Function("fullLevel", "focusLevel", "viewMode", "focusLabel",
  text.slice(levelStart, levelEnd) + ";return level")(
    () => view, focusLevel, "diagram", "focus");
const components = Array.from({length: 16}, (_, index) => ({label: index ? `n${index}` : "focus"}));
const edges = components.slice(1).map((target, index) => ({
  source: "focus", target: target.label, import_sites: index + 1,
  state: index === 14 ? "violation" : "conforms", rule_ids: [], names: [],
}));
const view = {components, edges};
const diagram = getLevel();
assert(diagram.edges.length < edges.length);
const full = new Function("fullLevel", "focusLevel", "viewMode", "focusLabel",
  text.slice(levelStart, levelEnd) + ";return level")(
    () => view, focusLevel, "review", "focus")();
assert.equal(full.edges.length, 15);
assert.equal(full.components.length, 16);

const alternative = {innerHTML: ""};
const renderReview = new Function("alternative", "selected", "edgeKey", "esc",
  text.slice(reviewStart, reviewEnd) + ";return renderReview")(
    alternative, null, edge => `${edge.source}>${edge.target}`, String);
renderReview(full);
assert(alternative.innerHTML.includes("15 observed connections at this level"));
assert(alternative.innerHTML.includes("Other connections · 3"));
assert(alternative.innerHTML.includes("Dependency matrix · 12 of 16 entries"));
"""
    )


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
