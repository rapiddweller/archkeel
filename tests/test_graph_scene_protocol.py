# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The actual browser scene boundary rejects invalid closed protocol values."""

from __future__ import annotations

import pytest
from scene_test_support import evaluate_scene


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
    result = evaluate_scene(
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
            "report-graph-schema.ts",
            "id: string; kind: G.EntityKind; entity: Entity;",
            "id: string; kind: string; entity: Entity;",
        ),
        (
            "report-graph-scene.js",
            "@param {Context} context @param {Options} [options] @returns {Scene}",
            "@param {Context} context @param {Options} [options] @returns {object}",
        ),
        (
            "report-graph-schema.ts",
            "case ViewMode.REVIEW: return ViewMode.DIAGRAM;",
            "case ViewMode.REVIEW: return ViewMode.REVIEW;",
        ),
        (
            "report-graph-schema.ts",
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
    from pathlib import Path

    compiler = shutil.which("npx")
    if compiler is None:
        pytest.skip("The browser development compiler requires Node/npx")
    root = Path(__file__).parents[1]
    assets = root / "src/archkeel/render/assets"
    sources = (
        "report-graph-vocabulary.ts",
        "report-graph-schema.ts",
        "report-graph-scene.js",
        "report-atlas-deviations.js",
    )
    for name in sources:
        shutil.copyfile(assets / name, tmp_path / name)
    target = tmp_path / "browser_graph_scene_target.ts"
    shutil.copyfile(root / "tests/browser_graph_scene_target.ts", target)
    target.write_text(target.read_text().replace("../src/archkeel/render/assets/", "./"))
    valid = _typecheck_sources(tmp_path, root)
    assert valid.returncode == 0, valid.stdout + valid.stderr
    candidate = tmp_path / path
    source = candidate.read_text(encoding="utf-8")
    assert source.count(before) == 1, "Mutation must hit exactly one actual consumer declaration"
    candidate.write_text(source.replace(before, after), encoding="utf-8")
    mutated = _typecheck_sources(tmp_path, root)
    assert mutated.returncode != 0, "Compiler accepted actual source widening/domain corruption"
    assert "error TS" in mutated.stdout, mutated.stdout + mutated.stderr


def test_graph_scene_keeps_wire_identity_json_and_primitive_tokens():
    result = evaluate_scene(
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


def test_native_scene_validates_each_graph_once_at_its_index_lifetime():
    result = evaluate_scene(
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


def test_offline_report_embeds_the_checked_module_bundle():
    from archkeel.render.html import _asset, _explorer_section

    page = _explorer_section("{}")
    vendor = _asset("elkjs-0.12.0.bundled.js").decode()
    bundle = _asset("explorer.runtime.js").decode()
    assert vendor in page and bundle in page
    assert page.index(vendor) < page.index(bundle)
    assert page.count('<script data-elkjs-version="0.12.0">') == 1
    assert "<script src=" not in page


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
    result = evaluate_scene(
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


def _typecheck_sources(directory, root):
    import subprocess

    compiler = ["node", str(root / "tools/browser-runtime/node_modules/typescript/bin/tsc")]
    declarations = directory / "report-graph-protocol.types.d.ts"
    generated = subprocess.run(
        [
            *compiler,
            "--strict",
            "--target",
            "ES2022",
            "--module",
            "none",
            "--declaration",
            "--emitDeclarationOnly",
            "--outFile",
            str(declarations),
            str(directory / "report-graph-vocabulary.ts"),
            str(directory / "report-graph-schema.ts"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if generated.returncode:
        return generated
    with declarations.open("a") as stream:
        stream.write((root / "tools/browser-runtime/protocol-exports.types.d.ts").read_text())
    return subprocess.run(
        [
            *compiler,
            "--strict",
            "--target",
            "ES2022",
            "--module",
            "esnext",
            "--moduleResolution",
            "node",
            "--moduleSuffixes",
            ".types,",
            "--allowJs",
            "--checkJs",
            "--noEmit",
            str(directory / "report-graph-scene.js"),
            str(directory / "report-atlas-deviations.js"),
            str(directory / "browser_graph_scene_target.ts"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
