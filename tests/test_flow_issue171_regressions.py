# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Focused regressions for issue 171's navigation, diagram sizing, and filters."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FLOW_JS = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"


def test_issue_171_regressions() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for report-flow checks"
    script = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const text = fs.readFileSync(process.argv[1], "utf8");
const part = (start, end) => {
  const begin = text.indexOf(start);
  const finish = text.indexOf(end, begin);
  assert(begin >= 0 && finish > begin, `${start} / ${end}`);
  return text.slice(begin, finish);
};

// Back from a physical module must retain the physical-card state on the inside crumb.
const crumbText = part("  function crumbs()", "  function updateNavigation()");
const opened = {
  component: "app", inside: "tasks", physicalInsideCard: true, path: [],
  module: "sample.tasks.one",
};
const crumbs = new Function("opened", `${crumbText}; return crumbs`)(opened);
const physicalParent = crumbs().at(-2).state;
assert.equal(physicalParent.physicalInsideCard, true);
const nestedOpened = {
  component: "app", inside: "service", insidePath: ["tasks"],
  physicalInsideCard: true, path: [], module: "sample.tasks.one",
};
const nestedCrumbs = new Function("opened", `${crumbText}; return crumbs`)(nestedOpened)();
assert.equal("physicalInsideCard" in nestedCrumbs[2].state, false);
assert.equal(nestedCrumbs[3].state.physicalInsideCard, true);
const card = {label: "tasks", modules: ["sample.tasks.one"], inside: null};
const DATA = {components: [{label: "app", inside: {components: [card], edges: []}}]};
const byLabel = new Map([["app", DATA.components[0]]]);
const navText = part("  function insideScope()", "  function focusLevel(");
const fullLevel = new Function("DATA", "opened", "componentByLabel", "insideLevel",
  "cardLevel", "moduleLevel", `${navText}; return fullLevel`)(
    DATA, physicalParent, byLabel, () => ({kind: "declared"}),
    (parent, path) => ({kind: "physical", parent, path}), () => ({kind: "module"}),
  );
assert.deepEqual(fullLevel(), {kind: "physical", parent: card, path: []});

// Exercise real layout + sizing with a bounded scroll container. Drag keeps its origin;
// left/up expansion creates enough SVG extent for native scroll compensation.
const components = [{label: "card"}];
const edges = [];
let box = {x: 0, y: 0, width: 200, height: 100};
const viewport = {getBBox: () => box};
const svg = {style: {}, setAttribute(name, value) { this[name] = value; }};
const canvas = {clientWidth: 800, clientHeight: 560, _left: 0, _top: 0};
Object.defineProperties(canvas, {
  scrollLeft: {
    get() { return this._left; },
    set(value) {
      this._left = Math.max(0, Math.min(value,
        Number.parseFloat(svg.style.width || "0") - this.clientWidth));
    },
  },
  scrollTop: {
    get() { return this._top; },
    set(value) {
      this._top = Math.max(0, Math.min(value,
        Number.parseFloat(svg.style.height || "0") - this.clientHeight));
    },
  },
});
const zoomValue = {textContent: ""};
const rankSource = part("  function computeRanks()", "  function layout()");
const layoutSource = part("  function layout()", "  function portX(");
const sizeSource = part("  function sizeDiagram()", "  function fit()");
const sizing = new Function("viewport", "svg", "canvas", "zoomValue", "transform",
  "level", "visibleEdges", "groupBy", "CARD", "GAP", "PER_ROW", "ROW_GAP", "ROW_STEP",
  "getComputedStyle",
  `let positions = {}; let sizedPositions = positions; let diagramOrigin = null; ` +
  `let dragState = null; let viewMode = "diagram"; let focusLabel = null; ` +
  `${rankSource} ${layoutSource} ${sizeSource}` +
  "; return {layout, sizeDiagram, get positions() { return positions; }, " +
  "newPositions() { positions = {}; dragState = null; }, startDrag() { dragState = {}; }, " +
  "origin() { return diagramOrigin; }}")(
    viewport, svg, canvas, zoomValue, {k: 1},
    () => ({components, edges}), () => edges, (items, key) => {
      const groups = new Map();
      items.forEach((item) => {
        const value = key(item);
        if (!groups.has(value)) groups.set(value, []);
        groups.get(value).push(item);
      });
      return groups;
    }, {w: 200, h: 100}, 32, 4, 150, 120,
    () => ({borderLeftWidth: "0px", borderRightWidth: "0px",
      borderTopWidth: "0px", borderBottomWidth: "0px"}),
  );
sizing.layout();
box = {...sizing.positions.card, width: 200, height: 100};
sizing.sizeDiagram();
assert(Number.parseFloat(svg.style.width) >= canvas.clientWidth);
assert(Number.parseFloat(svg.style.height) >= canvas.clientHeight);
const cardScreenX = () => sizing.positions.card.x - sizing.origin().x - canvas.scrollLeft;
const initialScreenX = cardScreenX();
const oldOrigin = sizing.origin().x;
sizing.startDrag();
sizing.positions.card.x = 100;
sizing.layout();
box = {...sizing.positions.card, width: 200, height: 100};
sizing.sizeDiagram();
assert.equal(sizing.origin().x, oldOrigin);
assert.equal(Number(svg.viewBox.split(" ")[0]), oldOrigin);
assert.equal(cardScreenX(), initialScreenX + 200);
sizing.positions.card.x = -400;
sizing.layout();
box = {...sizing.positions.card, width: 200, height: 100};
sizing.sizeDiagram();
assert.equal(sizing.origin().x, -432);
assert.equal(canvas.scrollLeft, 300);
assert.equal(cardScreenX(), initialScreenX - 300);
sizing.positions.card.y = -400;
sizing.layout();
box = {...sizing.positions.card, width: 200, height: 100};
sizing.sizeDiagram();
assert.equal(sizing.origin().y, -432);
assert.equal(canvas.scrollTop, 400);
assert.equal(sizing.positions.card.y - sizing.origin().y - canvas.scrollTop, -368);

// Navigating from a scrolled large level to fresh small-level positions resets native scroll.
sizing.positions.card.x = 1000;
sizing.positions.card.y = 1000;
sizing.layout();
box = {...sizing.positions.card, width: 200, height: 100};
sizing.sizeDiagram();
canvas.scrollLeft = 400;
canvas.scrollTop = 500;
sizing.newPositions();
sizing.layout();
box = {...sizing.positions.card, width: 200, height: 100};
sizing.sizeDiagram();
assert.equal(canvas.scrollLeft, 0);
assert.equal(canvas.scrollTop, 0);
assert.equal(sizing.positions.card.x - sizing.origin().x, 32);
assert.equal(sizing.positions.card.y - sizing.origin().y, 32);

// Filter text follows the clamped threshold, and empty levels show 0/0.
const input = {value: "9", max: "9", disabled: false};
const count = {textContent: ""};
const summaries = new Function("focusLabel", "opened", "thresholdInput", "violationsOnly",
  "thresholdValue", `${part("  function activeFilterSummary(mode)", "  function related(")}` +
  "; return {activeFilterSummary, normalizeThreshold, updateEdgeCount};")(
    null, null, input, {checked: false}, count,
  );
summaries.normalizeThreshold(1);
assert.equal(input.value, "1");
assert.match(summaries.activeFilterSummary("diagram"), /at least 1 import locations/);
summaries.updateEdgeCount(0, 0);
assert.match(count.textContent, /0\/0/);
assert(text.includes("updateEdgeCount(visibleEdges().length, fullLevel().edges.length);"));
"""
    result = subprocess.run(
        [node, "-e", script, str(FLOW_JS)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
