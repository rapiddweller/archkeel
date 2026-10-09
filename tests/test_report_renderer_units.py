# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The report scene and layout assets expose data-only browser APIs."""

from pathlib import Path

import pytest
from browser_report_support import _browser_page

ASSET_DIR = Path(__file__).parents[1] / "src/archkeel/render/assets"


def _asset_page(api, assets):
    playwright, browser, page = _browser_page(api, "<!doctype html><html><body></body></html>")
    try:
        for asset in assets:
            page.add_script_tag(path=str(ASSET_DIR / asset))
    except Exception:
        browser.close()
        playwright.stop()
        raise
    return playwright, browser, page


def test_report_scene_projection_is_stable_and_does_not_mutate_payload():
    api = pytest.importorskip("playwright.sync_api")
    data = {
        "observed": {
            "origin": "observed",
            "entities": [
                {
                    "id": "obs-a",
                    "kind": "module",
                    "qualified_name": "sample.a",
                    "parent_id": None,
                    "presence": "defined",
                    "responsibilities": [],
                    "modifiers": [],
                    "file_path": "sample/a.py",
                },
                {
                    "id": "obs-b",
                    "kind": "module",
                    "qualified_name": "sample.b",
                    "parent_id": None,
                    "presence": "defined",
                    "responsibilities": [],
                    "modifiers": [],
                    "file_path": "sample/b.py",
                },
            ],
            "relationships": [
                {
                    "id": "obs-import",
                    "kind": "imports",
                    "source_id": "obs-a",
                    "target_id": "obs-b",
                    "candidate_ids": [],
                    "resolution": "resolved",
                },
                {
                    "id": "obs-unknown",
                    "kind": "imports",
                    "source_id": "obs-a",
                    "target_id": "obs-b",
                    "candidate_ids": [],
                    "resolution": "resolved",
                },
            ],
            "component_intents": [],
        },
        "target": {"component_intents": []},
        "memberships": [],
        "findings": [],
        "decision_gaps": [],
    }
    target_graph = {
        "origin": "declared",
        "entities": [
            {
                "id": "target-a",
                "kind": "module",
                "qualified_name": "sample.a",
                "parent_id": None,
                "presence": "defined",
                "responsibilities": [],
                "modifiers": [],
                "file_path": "sample/a.py",
            },
            {
                "id": "target-b",
                "kind": "module",
                "qualified_name": "sample.b",
                "parent_id": None,
                "presence": "defined",
                "responsibilities": [],
                "modifiers": [],
                "file_path": "sample/b.py",
            },
        ],
        "relationships": [
            {
                "id": "target-fail",
                "kind": "requires",
                "source_id": "target-a",
                "target_id": "target-b",
                "candidate_ids": [],
                "resolution": "resolved",
            },
            {
                "id": "target-unknown",
                "kind": "requires",
                "source_id": "target-a",
                "target_id": "target-b",
                "candidate_ids": [],
                "resolution": "resolved",
            },
        ],
        "component_intents": [],
    }
    playwright, browser, page = _asset_page(api, ["report-scene.js"])
    try:
        result = page.evaluate(
            """({data, targetGraph}) => {
          const before = JSON.stringify(data);
          const model = window.ArchkeelReportScene.create(data);
          const project = (graph, viewMode, comparison = null) =>
            model.projectArchitectureScene({graph, scope: null, comparison}, {viewMode});
          const observed = project(data.observed, 'diagram');
          const observedAgain = project(data.observed, 'diagram');
          const target = project(targetGraph, 'target');
          const comparison = {
            assessments: [
              {id: 'fail', subject_id: 'target-fail', observed_ids: ['obs-import'], status: 'FAIL'},
              {id: 'unknown', subject_id: 'target-unknown', observed_ids: ['obs-unknown'],
                status: 'UNKNOWN'},
            ],
            correspondences: [
              {target_id: 'target-a', observed_ids: ['obs-a']},
              {target_id: 'target-b', observed_ids: ['obs-b']},
            ],
          };
          const diff = project(targetGraph, 'diff', comparison);
          const shape = scene => ({
            ids: scene.nodes.map(node => node.id).sort(),
            edges: scene.edges.map(edge => [edge.id, edge.state]).sort(),
          });
          return {observed: shape(observed), observedAgain: shape(observedAgain),
            target: shape(target), diff: shape(diff), unchanged: JSON.stringify(data) === before};
        }""",
            {"data": data, "targetGraph": target_graph},
        )
        assert result["observed"] == {
            "ids": ["obs-a", "obs-b"],
            "edges": [["imports:obs-a>obs-b:resolved", "observed"]],
        }
        assert result["observedAgain"] == result["observed"]
        assert result["target"] == {
            "ids": ["target-a", "target-b"],
            "edges": [["target-fail", "declared"], ["target-unknown", "declared"]],
        }
        assert result["diff"]["edges"] == [
            ["target-fail", "violation"],
            ["target-unknown", "undecided"],
        ]
        assert result["unchanged"]
    finally:
        browser.close()
        playwright.stop()


def test_report_layout_routes_explicit_geometry_and_rejects_incomplete_elk_output():
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _asset_page(api, ["elkjs-0.12.0.bundled.js", "report-layout.js"])
    try:
        result = page.evaluate("""async () => {
          const layout = window.ArchkeelReportLayout;
          const geometry = {
            positions: {a: {x: 0, y: 0}, b: {x: 320, y: 180}},
            nodeSizes: {a: {width: 200, height: 92}, b: {width: 200, height: 92}},
            frames: {}, cardWidth: 200, gap: 34, laneGap: 11, rowGap: 90,
            edges: [{id: 'edge-ab', source: 'a', target: 'b'}],
          };
          const before = JSON.stringify(geometry);
          const routes = layout.routeUmlRelationships(geometry);
          const incompletePositions = {a: geometry.positions.a};
          const manualCoverage = [
            layout.hasCompleteManualPositions(['a', 'b'], geometry.positions),
            layout.hasCompleteManualPositions(['a', 'b'], incompletePositions),
            layout.hasCompleteManualPositions(['a'], {a: {x: 0, y: Number.NaN}}),
          ];
          const graph = {id: 'root', children: [{id: 'frame:outer', children: [
            {id: 'node:a', width: 200, height: 92},
          ]}, {id: 'node:b', width: 200, height: 92}],
            edges: [{id: 'edge:edge-ab', sources: ['node:a'], targets: ['node:b']}],
            layoutOptions: {'elk.algorithm': 'layered', 'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
              'elk.edgeRouting': 'ORTHOGONAL'}};
          const laidOut = await layout.layout(graph);
          const decoded = layout.decodeLayout(laidOut, {
            nodeIds: ['node:a', 'node:b'], frameIds: ['frame:outer'], edgeIds: ['edge:edge-ab'],
          });
          const rejects = value => {
            try { layout.decodeLayout(value, {
              nodeIds: ['node:a', 'node:b'], frameIds: ['frame:outer'], edgeIds: ['edge:edge-ab'],
            }); return false; } catch { return true; }
          };
          const missing = {...laidOut, children: laidOut.children.slice(0, 1)};
          const duplicate = {...laidOut, children: [...laidOut.children,
            {...laidOut.children[1], id: 'frame:outer'}]};
          const unexpected = {...laidOut, children: [...laidOut.children,
            {id: 'unexpected', x: 0, y: 0, width: 1, height: 1}]};
          const nonfinite = {...laidOut, children: laidOut.children.map(child =>
            child.id === 'frame:outer' ? {...child, x: Number.NaN} : child)};
          return {route: routes[0], routeCount: routes.length, manualCoverage,
            inputUnchanged: JSON.stringify(geometry) === before,
            nodeIds: Object.keys(decoded.positions).sort(),
            nodeA: decoded.positions['node:a'], frame: decoded.frames['frame:outer'],
            frameIds: Object.keys(decoded.frames).sort(),
            edgeIds: [...decoded.routes.keys()].sort(),
            rejects: [rejects(missing), rejects(duplicate),
              rejects(unexpected), rejects(nonfinite)]};
        }""")
        assert result["routeCount"] == 1
        assert result["route"]["edgeId"] == "edge-ab"
        assert "edge" not in result["route"]
        assert result["route"]["points"][0] != result["route"]["points"][-1]
        assert result["manualCoverage"] == [True, False, False]
        assert result["inputUnchanged"]
        assert result["nodeIds"] == ["node:a", "node:b"]
        assert result["frameIds"] == ["frame:outer"]
        assert result["frame"]["left"] < result["nodeA"]["x"]
        assert result["frame"]["top"] < result["nodeA"]["y"]
        assert result["edgeIds"] == ["edge:edge-ab"]
        assert result["rejects"] == [True, True, True, True]
    finally:
        browser.close()
        playwright.stop()


def test_atlas_layout_builds_and_validates_exact_geometry_inventory():
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _asset_page(api, ["elkjs-0.12.0.bundled.js", "report-layout.js"])
    try:
        result = page.evaluate("""async () => {
          const layout = window.ArchkeelReportLayout;
          const input = {
            componentOverview: true, parentId: null,
            nodes: [{id: 'c1'}, {id: 'c2'}],
            edges: [{id: 'e12', layoutId: 'l12', source: 'c1', target: 'c2', label: '1 import'}],
            components: [], cardWidth: 200, cardHeights: {c1: 100, c2: 100},
          };
          const built = layout.buildAtlasGraph(input);
          const laidOut = await layout.layout(built.graph);
          const decoded = layout.decodeLayout(laidOut, built.expected);
          const corruptions = [];
          const missing = {...laidOut, children: laidOut.children.filter(
            child => child.id !== 'component:c2')};
          const duplicate = {...laidOut, children: [...laidOut.children, {...laidOut.children[1]}]};
          const unexpected = {...laidOut, children: [...laidOut.children,
            {id: 'component:extra', x: 0, y: 0, width: 200, height: 100}]};
          for (const value of [missing, duplicate, unexpected]) {
            try { layout.decodeLayout(value, built.expected); corruptions.push(false); }
            catch { corruptions.push(true); }
          }
          const missingLabel = {...laidOut,
            edges: laidOut.edges.map(edge => ({...edge, labels: []}))};
          try { layout.decodeLayout(missingLabel, built.expected); corruptions.push(false); }
          catch { corruptions.push(true); }
          return {nodeIds: Object.keys(decoded.positions).sort(),
            edgeIds: [...decoded.routes.keys()],
            labelIds: Object.keys(decoded.labels), corruptions};
        }""")
        assert result["nodeIds"] == ["component:c1", "component:c2"]
        assert result["edgeIds"] == ["edge:l12"]
        assert result["labelIds"] == ["label:l12"]
        assert result["corruptions"] == [True, True, True, True]
    finally:
        browser.close()
        playwright.stop()


def test_report_scene_hydrates_only_a_copy_of_packed_atlas_data():
    api = pytest.importorskip("playwright.sync_api")
    atlas = {
        "reference_ids": ["reason"],
        "rule_assessments": [],
        "cells": [],
        "assignments": [[0, None, [], "UNKNOWN", 0]],
        "modules": [{"id": "module:a", "symbol_coverage": 0}],
        "symbol_coverages": [[{"name": "Symbol"}]],
        "levels": [{"modules": [0]}],
        "components": [],
        "findings": [],
        "declared_modules": [],
        "deviations": [],
    }
    data = {"atlas": atlas}
    playwright, browser, page = _asset_page(api, ["report-scene.js"])
    try:
        result = page.evaluate(
            """data => {
          const before = JSON.stringify(data);
          const model = window.ArchkeelReportScene.create(data);
          return {
            unchanged: JSON.stringify(data) === before,
            atlasCopied: model.atlas !== data.atlas,
            hydratedAssignment: model.atlas.assignments[0],
            levelUsesHydratedAssignment:
              model.atlas.levels[0].modules[0] === model.atlas.assignments[0],
            moduleCoverageScope: model.atlas.modules[0].symbol_coverage[0].scope_id,
          };
        }""",
            data,
        )
        assert result["unchanged"]
        assert result["atlasCopied"]
        assert result["hydratedAssignment"]["ownership_reason"] == "reason"
        assert result["levelUsesHydratedAssignment"]
        assert result["moduleCoverageScope"] == "module:a"
    finally:
        browser.close()
        playwright.stop()


def test_nested_layout_routes_use_the_elk_container_coordinate_system():
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _asset_page(api, ["elkjs-0.12.0.bundled.js", "report-layout.js"])
    try:
        result = page.evaluate("""async () => {
          const layout = window.ArchkeelReportLayout;
          const input = {componentOverview: false, parentId: null, cardWidth: 200,
            cardHeights: {a: 92, b: 92, c: 92},
            nodes: [{id: 'a', ownerId: 'inner', label: 'a'},
              {id: 'b', ownerId: 'inner', label: 'b'},
              {id: 'c', ownerId: 'outer', label: 'c'}],
            components: [{id: 'outer', parentId: null, label: 'outer'},
              {id: 'inner', parentId: 'outer', label: 'inner'}],
            edges: [{id: 'ab', source: 'a', target: 'b'},
              {id: 'bc', source: 'b', target: 'c'}]};
          const built = layout.buildAtlasGraph(input);
          const raw = await layout.layout(built.graph);
          const decoded = layout.decodeLayout(raw, built.expected);
          const anchored = input.edges.map(edge => {
            const route = decoded.routes.get(`edge:${edge.id}`);
            const source = decoded.positions[`module:${edge.source}`];
            const target = decoded.positions[`module:${edge.target}`];
            const onSide = ([x, y], card) => (x === card.x || x === card.x + 200)
              && y >= card.y && y <= card.y + 92;
            return onSide(route.points[0], source) && onSide(route.points.at(-1), target);
          });
          const invalid = structuredClone(raw);
          invalid.edges[0].container = 'missing-frame';
          let rejectsUnknownContainer = false;
          try { layout.decodeLayout(invalid, built.expected); }
          catch { rejectsUnknownContainer = true; }
          return {anchored, rejectsUnknownContainer};
        }""")
        assert result["anchored"] == [True, True]
        assert result["rejectsUnknownContainer"]
    finally:
        browser.close()
        playwright.stop()
