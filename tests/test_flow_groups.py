# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise the browser's package aggregation without adding a JS dependency."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_package_groups_keep_import_totals_and_violations() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
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
const {cardLevel} = new Function("DATA", text.slice(begin, end) + ";return {cardLevel}")(DATA);
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
assert.deepEqual(root.components.map(card => card.label), ["pkg.api", "pkg.util"]);
assert.equal(root.components[0].folder, true);
assert.equal(root.components[0].modules.length, 3);
assert.equal(root.components[0].public.length, 1);
assert.equal(root.edges.length, 1);
assert.equal(root.edges[0].import_sites, 5);
assert.equal(root.edges[0].state, "violation");
assert.deepEqual(root.edges[0].rule_ids, ["R1"]);
assert.deepEqual(cardLevel(component, ["pkg.api"]).components.map(card => card.label),
  ["pkg.api.orders", "pkg.api.users"]);
DATA.modules.pkg.symbols = [{}];
assert(cardLevel(component, []).components.some(card => card.label === "pkg:__init__"));
component.public = null;
assert(cardLevel(component, []).components.every(card => card.public === null));
"""
    result = subprocess.run(
        [node, "-e", script, str(source)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
