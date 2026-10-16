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
