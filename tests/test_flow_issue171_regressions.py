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
assert(text.indexOf("normalizeThreshold(maximum);") <
  text.indexOf("filterStatus.textContent = activeFilterSummary();"));
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

// A card moving right keeps the prior diagram origin, so its screen position also moves.
let box = {x: 0, y: 0, width: 200, height: 100};
const viewport = {getBBox: () => box};
const svg = {style: {}, setAttribute(name, value) { this[name] = value; }};
const canvas = {scrollLeft: 0, scrollTop: 0};
const zoomValue = {textContent: ""};
const sizeSource = part("  function sizeDiagram()", "  function fit()");
const sizing = new Function("viewport", "svg", "canvas", "zoomValue", "transform",
  `let positions = {}; let sizedPositions = positions; let diagramOrigin = null; ` +
  `let dragState = null; ${sizeSource}` +
  "; return {sizeDiagram, startDrag() { dragState = {}; }, origin() { return diagramOrigin; }}")(
    viewport, svg, canvas, zoomValue, {k: 1},
  );
sizing.sizeDiagram();
const oldOrigin = sizing.origin().x;
sizing.startDrag();
box = {x: 100, y: 0, width: 200, height: 100};
sizing.sizeDiagram();
assert.equal(sizing.origin().x, oldOrigin);
assert.equal(Number(svg.viewBox.split(" ")[0]), oldOrigin);
box = {x: -100, y: 0, width: 200, height: 100};
sizing.sizeDiagram();
assert.equal(sizing.origin().x, -132);
assert.equal(canvas.scrollLeft, 100);
assert.equal(-100 - sizing.origin().x - canvas.scrollLeft, -68);

// Filter text follows the clamped threshold, and empty levels show 0/0.
const input = {value: "9", max: "9", disabled: false};
const count = {textContent: ""};
const summaries = new Function("focusLabel", "opened", "thresholdInput", "violationsOnly",
  "thresholdValue", `${part("  function activeFilterSummary()", "  function related(")}` +
  "; return {activeFilterSummary, normalizeThreshold, updateEdgeCount};")(
    null, null, input, {checked: false}, count,
  );
summaries.normalizeThreshold(1);
assert.equal(input.value, "1");
assert.match(summaries.activeFilterSummary(), /at least 1 import sites/);
summaries.updateEdgeCount(0, 0);
assert.match(count.textContent, /0\/0/);
assert(text.includes("updateEdgeCount(visibleEdges().length, fullLevel().edges.length);"));
"""
    result = subprocess.run(
        [node, "-e", script, str(FLOW_JS)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
