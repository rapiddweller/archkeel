# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Legacy Target scenes retain authenticated graph identities and permission evidence."""

import json

import pytest
from test_target_graph import _nested_repository, _permission_contract
from test_uml_evaluation import _repository

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.graph_codec import parse_graph
from archkeel.ir.target_records import recorded_target_graph
from archkeel.render.html import render_html


def _legacy_report(tmp_path, *, nested=False, version="2.2.0", explicit_uml=False):
    root, config = _nested_repository(tmp_path) if nested else _repository(tmp_path)
    paths = (config.contract, "inside.json", "leaf.json") if nested else (config.contract,)
    owner_path = "inside.json" if nested else config.contract
    for path in paths:
        raw = json.loads((root / path).read_bytes())
        raw["schema_version"] = version
        if not explicit_uml:
            raw.get("declarations", {}).pop("uml", None)
        if path == owner_path:
            raw = _permission_contract(raw)
            owner = raw["components"][0]
            owner.update(role="foundation", public=[], planned=["sample.core:Future"])
            owner["requires"].extend(
                [
                    {"component": "peer", "rationale": "Read another published surface."},
                    dict(owner["requires"][0]),
                ]
            )
            raw["components"].append(
                {
                    **raw["components"][1],
                    "id": "OTHER",
                    "label": "other",
                    "namespace": "sample.core.other",
                    "packages": ["sample.core.other"],
                }
            )
        (root / path).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(
        item
        for item in model.records("declarations")
        if item.kind == ("uml_target" if explicit_uml else "architecture_target")
    )
    graph = recorded_target_graph(model, declaration)
    html = render_html(
        result, model, repository="sample", architecture_href="architecture.json"
    ).decode()
    start = html.index('id="flow-data"')
    payload = json.loads(html[html.index(">", start) + 1 : html.index("</script>", start)])
    return html, payload, graph


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
@pytest.mark.parametrize("nested", [False, True])
def test_legacy_permission_projection_keeps_graph_ids_endpoints_and_evidence(
    tmp_path, nested, version
):
    _, payload, graph = _legacy_report(tmp_path, nested=nested, version=version)
    permissions = [item for item in graph.relationships if item.kind == "requires"]
    assert len(permissions) == 3 and len({item.id for item in permissions}) == 3
    projected = parse_graph(payload["target"])
    assert projected == graph
    assert [item for item in projected.relationships if item.kind == "requires"] == permissions
    assert all(item.reason and item.provenance and item.decided_by for item in permissions)
    assert payload["comparison"] is None
    assert not {"uml", "explorers", "components", "modules"}.intersection(payload)


def test_target_graph_is_decoded_once_for_both_rendering_payloads(tmp_path, monkeypatch):
    import archkeel.ir.report_graph as producer

    decoded = []
    original = producer.recorded_target_graph
    original_render = render_html

    def record_decode(observation, declaration):
        decoded.append(declaration.id)
        return original(observation, declaration)

    def measured_render(*args, **kwargs):
        assert len(decoded) == 1
        decoded.clear()
        page = original_render(*args, **kwargs)
        assert len(decoded) == 1
        return page

    monkeypatch.setattr(producer, "recorded_target_graph", record_decode)
    monkeypatch.setattr(f"{__name__}.render_html", measured_render)
    _, payload, graph = _legacy_report(tmp_path, nested=True)
    assert len(decoded) == 1
    assert parse_graph(payload["target"]) == graph
