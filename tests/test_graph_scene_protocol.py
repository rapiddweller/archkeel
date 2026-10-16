# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The actual browser scene boundary rejects invalid closed protocol values."""

from __future__ import annotations

import pytest
from test_report_renderer_units import _asset_page


@pytest.mark.parametrize(
    "field",
    [
        "origin",
        "entity_kind",
        "presence",
        "relationship_kind",
        "resolution",
        "visibility",
        "parameter_kind",
    ],
)
def test_scene_create_rejects_unknown_graph_protocol_values(field):
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _asset_page(api, ["report-scene.js"])
    try:
        result = page.evaluate(
            """field => {
              const entity = {id: "item", kind: "class", qualified_name: "sample.Item",
                parent_id: null, presence: "defined", responsibilities: [], modifiers: [],
                visibility: {kind: "public"},
                signature: {parameters: [{name: "value", kind: "positional",
                  annotation: null, default: null, default_known: false}], returns: null}};
              const site = {id: "site", kind: "references", source_id: "item",
                target_id: "item", candidate_ids: [], resolution: "resolved"};
              const graph = {origin: "observed", entities: [entity],
                relationships: [site], component_intents: []};
              const data = {observed: graph, target: null, memberships: [],
                findings: [], decision_gaps: []};
              const invalid = "unsupported-protocol-value";
              const edits = {
                origin: () => { graph.origin = invalid; },
                entity_kind: () => { entity.kind = invalid; },
                presence: () => { entity.presence = invalid; },
                relationship_kind: () => { site.kind = invalid; },
                resolution: () => { site.resolution = invalid; },
                visibility: () => { entity.visibility.kind = invalid; },
                parameter_kind: () => { entity.signature.parameters[0].kind = invalid; },
              };
              edits[field]();
              try { window.ArchkeelReportScene.create(data); }
              catch (error) { return {rejected: error instanceof TypeError}; }
              return {rejected: false};
            }""",
            field,
        )
        assert result["rejected"], f"scene.create accepted unknown {field}"
    finally:
        browser.close()
        playwright.stop()


def test_scene_vocabulary_is_generated_from_canonical_owners():
    from tools.browser_graph_protocol import _OUTPUT, vocabulary_source

    assert _OUTPUT.read_bytes() == vocabulary_source().encode("utf-8")


@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        (
            "report-graph-scene.js",
            "return { id, kind: entity.kind, entity, sourceGraph, assessments,",
            'return { id, kind: "component", entity, sourceGraph, assessments,',
        ),
        (
            "report-graph-scene.js",
            "return { id, kind: entity.kind, entity, sourceGraph, assessments,",
            "return { id, kind: G.ComponentRole.COMPONENT, entity, sourceGraph, assessments,",
        ),
        (
            "report-graph-protocol.ts",
            "id: string; kind: G.EntityKind; entity: Entity;",
            "id: string; kind: string; entity: Entity;",
        ),
        (
            "report-graph-scene.js",
            "@param {Context} context @param {Options} [options] @returns {Scene}",
            "@param {Context} context @param {Options} [options] @returns {object}",
        ),
        (
            "report-graph-protocol.ts",
            "case ViewMode.REVIEW: return ViewMode.DIAGRAM;",
            "case ViewMode.REVIEW: return ViewMode.REVIEW;",
        ),
        (
            "report-graph-protocol.ts",
            "export function projectViewMode(value: ViewMode): ProjectionMode {",
            "export function projectViewMode(value: ViewMode): ViewMode {",
        ),
    ],
    ids=[
        "raw-field",
        "same-spelling-wrong-domain",
        "field-widening",
        "return-widening",
        "evidence-mode-leaked-into-projection",
        "projection-mode-return-widening",
    ],
)
def test_actual_scene_consumer_rejects_type_mutations(tmp_path, path, before, after):
    import shutil
    import subprocess
    from pathlib import Path

    compiler = shutil.which("npx")
    if compiler is None:
        pytest.skip("The browser development compiler requires Node/npx")
    root = Path(__file__).parents[1]
    assets = root / "src/archkeel/render/assets"
    sources = (
        "report-graph-vocabulary.ts",
        "report-graph-protocol.ts",
        "report-graph-scene.js",
    )
    for name in sources:
        shutil.copyfile(assets / name, tmp_path / name)
    target = tmp_path / "browser_graph_scene_target.ts"
    shutil.copyfile(root / "tests/browser_graph_scene_target.ts", target)
    command = [
        compiler,
        "--yes",
        "--package",
        "typescript@5.9.3",
        "tsc",
        "--strict",
        "--allowJs",
        "--checkJs",
        "--noEmit",
        "--target",
        "ES2022",
        "--module",
        "none",
        *(str(tmp_path / name) for name in sources),
        str(target),
    ]
    valid = subprocess.run(command, text=True, capture_output=True, check=False)
    assert valid.returncode == 0, valid.stdout + valid.stderr
    candidate = tmp_path / path
    source = candidate.read_text(encoding="utf-8")
    assert source.count(before) == 1, "Mutation must hit exactly one actual consumer declaration"
    candidate.write_text(source.replace(before, after), encoding="utf-8")
    mutated = subprocess.run(command, text=True, capture_output=True, check=False)
    assert mutated.returncode != 0, "Compiler accepted actual source widening/domain corruption"
    assert "error TS" in mutated.stdout, mutated.stdout + mutated.stderr


def test_graph_scene_keeps_wire_identity_json_and_primitive_tokens():
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _asset_page(api, ["report-scene.js"])
    try:
        result = page.evaluate(
            """() => {
              const G = ArchkeelGraphProtocol;
              const P = ArchkeelGraphSceneProtocol;
              const first = {id: "a", kind: "module", qualified_name: "free.any.a",
                parent_id: null, presence: "defined", responsibilities: [],
                modifiers: [], file_path: "free/any/a.py"};
              const second = {...first, id: "b", qualified_name: "free.any.b"};
              const site = {id: "import", kind: "imports", source_id: "a", target_id: "b",
                candidate_ids: [], resolution: "resolved"};
              const graph = {origin: "observed", entities: [first, second],
                relationships: [site], component_intents: []};
              const data = {observed: graph, target: null};
              const before = JSON.stringify(data);
              const model = ArchkeelReportScene.create(data);
              const context = {graph, scope: null, comparison: null};
              const options = {viewMode: P.ViewMode.DIAGRAM};
              const scene = model.projectArchitectureScene(context, options);
              const again = model.projectArchitectureScene(context, options);
              const clone = structuredClone(scene);
              const node = scene.nodes.find(node => node.id === first.id);
              const decoded = P.decodeGraph(graph);
              let zeroRejected = false;
              try {
                P.decodeComparison({assessments:[
                  {id:"a", subject_id:"a", observed_ids:[], status:0},
                ]});
              } catch { zeroRejected = true; }
              const mermaid = ArchkeelReportScene.sceneToMermaid({
                nodes: [{id:"a", label:"A", assessments:[{status:G.AssessmentStatus.PASS}]}],
                edges: [],
              });
              return {
                graphIdentity: decoded === graph && node.sourceGraph === graph,
                entityIdentity: node.entity === first,
                siteIdentity: scene.edges[0].sites[0] === site,
                unchanged: JSON.stringify(data) === before,
                stable: JSON.stringify(scene) === JSON.stringify(again),
                clone: clone.nodes[0].kind === G.EntityKind.MODULE,
                origin: decoded.origin,
                status: G.AssessmentStatus.PASS,
                zeroRejected,
                passVisible: mermaid.includes("A · PASS"),
                tokensAreStrings: Object.values(G.AssessmentStatus)
                  .every(token => typeof token === "string"),
              };
            }"""
        )
        assert result == {
            "graphIdentity": True,
            "entityIdentity": True,
            "siteIdentity": True,
            "unchanged": True,
            "stable": True,
            "clone": True,
            "origin": "observed",
            "status": "PASS",
            "zeroRejected": True,
            "passVisible": True,
            "tokensAreStrings": True,
        }
    finally:
        browser.close()
        playwright.stop()


def test_native_scene_validates_each_graph_once_at_its_index_lifetime():
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _asset_page(api, ["report-scene.js"])
    try:
        result = page.evaluate(
            """() => {
              let reads = 0;
              const entity = {id:"sample", kind:"module", qualified_name:"free.name",
                parent_id:null, presence:"defined", responsibilities:[], modifiers:[],
                visibility:{get kind() { reads += 1; return "public"; }}};
              const graph = {origin:"observed", entities:[entity], relationships:[],
                component_intents:[]};
              const model = ArchkeelReportScene.create({observed:graph});
              const initial = reads;
              for (let i = 0; i < 3; i += 1) {
                model.projectArchitectureScene({graph,scope:null}, {viewMode:"diagram"});
              }
              const afterOwn = reads;
              const external = {...graph, entities:[{...entity, id:"external"}]};
              model.projectArchitectureScene({graph:external,scope:null}, {viewMode:"diagram"});
              const afterExternal = reads;
              model.projectArchitectureScene({graph:external,scope:null}, {viewMode:"diagram"});
              return {initial, afterOwn, afterExternal, afterAgain:reads};
            }"""
        )
        assert result == {"initial": 1, "afterOwn": 1, "afterExternal": 2, "afterAgain": 2}
    finally:
        browser.close()
        playwright.stop()


def test_actual_own_graph_scene_preserves_full_wire_json(self_observation):
    import json

    from archkeel.ir.graph_codec import report_bytes
    from archkeel.ir.report_graph import architecture_report

    data = json.loads(report_bytes(architecture_report(self_observation)))
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _asset_page(api, ["report-scene.js"])
    try:
        result = page.evaluate(
            """data => {
              const before = JSON.stringify(data);
              const model = ArchkeelReportScene.create(data);
              const graph = data.observed;
              const module = graph.entities.find(entity =>
                entity.qualified_name === "archkeel.ir.architecture_graph"
                && entity.kind === "module");
              const scene = model.projectArchitectureScene(
                {graph, scope:module.id}, {viewMode:"diagram"});
              const again = model.projectArchitectureScene(
                {graph, scope:module.id}, {viewMode:"diagram"});
              const sceneJSON = value => JSON.stringify(value,
                (key, item) => key === "sourceGraph" ? {origin:item.origin} : item);
              return {
                unchanged: before === JSON.stringify(data),
                stable: sceneJSON(scene) === sceneJSON(again),
                identities: scene.nodes.every(node => node.sourceGraph === graph
                  && graph.entities.includes(node.entity)),
                cards: scene.nodes.length,
              };
            }""",
            data,
        )
        assert result["unchanged"] and result["stable"] and result["identities"]
        assert result["cards"] > 0
    finally:
        browser.close()
        playwright.stop()


def test_offline_report_loads_the_actual_protocol_before_scene_consumers():
    from archkeel.render.html import _explorer_section

    page = _explorer_section("{}")
    assert (
        page.index('data-report-asset="graph-protocol"')
        < page.index('data-report-asset="graph-scene"')
        < page.index('data-report-asset="scene"')
        < page.index('data-report-asset="layout"')
    )


def test_stale_generated_vocabulary_fails_the_actual_check_command(tmp_path, monkeypatch):
    import sys

    from tools import browser_graph_protocol

    stale = tmp_path / "vocabulary.ts"
    source = browser_graph_protocol.vocabulary_source()
    stale.write_text(
        source.replace('OBSERVED = "observed"', 'OBSERVED = "stale"'), encoding="utf-8"
    )
    monkeypatch.setattr(browser_graph_protocol, "_OUTPUT", stale)
    monkeypatch.setattr(sys, "argv", ["browser_graph_protocol", "--check"])
    with pytest.raises(SystemExit, match="Browser graph vocabulary is stale"):
        browser_graph_protocol.main()


def test_native_projection_preserves_legacy_default_options_and_rejects_invalid_modes():
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _asset_page(api, ["report-scene.js"])
    try:
        result = page.evaluate(
            """() => {
              const P = ArchkeelGraphSceneProtocol;
              const graph = {origin:"observed", entities:[
                {id:"a", kind:"module", qualified_name:"pkg.a", parent_id:null,
                 presence:"defined", responsibilities:[], modifiers:[], file_path:"pkg/a.py"},
              ], relationships:[], component_intents:[]};
              const model = ArchkeelReportScene.create({observed:graph, target:null});
              const context = {graph, scope:null, comparison:null};
              const defaults = [undefined, {}, {directChildren:true}, {viewMode:undefined}]
                .map(options => {
                  const expected = model.projectArchitectureScene(context, {
                    viewMode:P.ViewMode.DIAGRAM, directChildren:options?.directChildren ?? false,
                  });
                  const actual = options === undefined
                    ? model.projectArchitectureScene(context)
                    : model.projectArchitectureScene(context, options);
                  return JSON.stringify(actual) === JSON.stringify(expected);
                });
              const modes = Object.values(P.ViewMode).map(viewMode => {
                model.projectArchitectureScene(context, {viewMode});
                return true;
              });
              const invalid = [null, 0, "unsupported-view", "toString"].map(viewMode => {
                try { model.projectArchitectureScene(context, {viewMode}); }
                catch (error) { return error instanceof TypeError; }
                return false;
              });
              return {defaults, modes, invalid};
            }"""
        )
        assert result == {
            "defaults": [True] * 4,
            "modes": [True] * 6,
            "invalid": [True] * 4,
        }
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize(
    ("mode", "label", "heading"),
    [
        ("actual", "Actual", "Observed modules"),
        ("structure", "Structure", "Architecture structure"),
        ("review", "Review", "Recorded findings"),
    ],
)
def test_visible_evidence_views_keep_the_observed_scene(tmp_path, mode, label, heading):
    from browser_report_support import _browser_page
    from test_uml_rendering import _uml_report

    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        button = page.locator("#flow").get_by_role("button", name=label, exact=True)
        api.expect(button).to_be_visible()
        button.click()
        page.wait_for_function(
            "view => document.querySelector('#flow').dataset.view === view", arg=mode
        )
        assert not errors, errors
        api.expect(page.locator(".flow-alternative h2")).to_have_text(heading)
        api.expect(page.locator(".flow-alternative")).to_be_visible()
        assert page.locator(".flow-canvas").is_hidden()
        page.locator('[data-flow-view="diagram"]').click()
        page.wait_for_function(
            "() => document.querySelector('#flow').dataset.layoutState === 'ready'"
        )
        api.expect(page.locator(".flow-canvas")).to_be_visible()
        assert not errors, errors
    finally:
        browser.close()
        playwright.stop()
