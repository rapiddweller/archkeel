# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The standard Target preserves independent intent and render direction."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_target_graph import _nested_repository

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.graph_codec import parse_report, report_bytes
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.target_records import recorded_target_graph
from archkeel.render.html import render_html


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_target_navigation_receives_only_the_authenticated_graph(tmp_path, version):
    root, config = _nested_repository(tmp_path, root_version=version)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    descriptor = next(item for item in model.records("declarations") if item.kind == "uml_target")
    graph = recorded_target_graph(model, descriptor)
    html = render_html(result, model, repository="sample", architecture_href=None).decode()
    start = html.index(">", html.index('id="flow-data"')) + 1
    report = parse_report(json.loads(html[start : html.index("</script>", start)]))
    expected = json.loads(report_bytes(architecture_report(model)))
    for side in ("observed", "target"):
        for collection in ("entities", "relationships"):
            for item in expected[side][collection]:
                del item["record_ids"]
    assert report == parse_report(expected)
    assert report.target == replace(
        graph,
        entities=tuple(replace(item, record_ids=()) for item in graph.entities),
        relationships=tuple(replace(item, record_ids=()) for item in graph.relationships),
    )
    assert graph.component_intents and graph.layout_rules and graph.module_inventories
    assert '"explorers"' not in html and '"target_diagrams"' not in html


@pytest.mark.parametrize("backward_importer", [None, "summary", "atlas"])
def test_own_render_contract_enforces_output_direction(tmp_path, backward_importer):
    root_path = Path(__file__).parents[1]
    contract_path = "docs/architecture/contracts/render.json"
    inside = json.loads((root_path / contract_path).read_bytes())
    provenance = "docs/architecture/decisions/ad-179-reports-render-one-graph-boundary.md"
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "src/archkeel/__init__.py": "",
        "src/archkeel/render/__init__.py": "",
        "src/archkeel/render/atlas.py": (
            "def atlas_payload(): return {}\n"
            + ("from . import html\n" if backward_importer == "atlas" else "")
        ),
        "src/archkeel/render/summary.py": (
            "def report_summary(): return None\n"
            + ("from . import html\n" if backward_importer == "summary" else "")
        ),
        "src/archkeel/render/terminal.py": "from . import summary\n",
        "src/archkeel/render/html.py": (
            "from .atlas import atlas_payload\n"
            "from .summary import report_summary\n"
            "def _flow_section(observation):\n    return ''\n"
        ),
        provenance: "One report input; summary has no output dependency.\n",
        "docs/architecture/render-target.md": "Payload and summary do not depend on HTML.\n",
        "docs/architecture/decisions/ad-213-renderer-responsibility-boundaries.md": (
            "Separate payload construction from HTML composition.\n"
        ),
        contract_path: json.dumps(inside),
        "architecture-contract.json": json.dumps(
            {
                "schema_version": "2.2.0",
                "rules": [],
                "components": [
                    {
                        "id": "RENDER",
                        "label": "render",
                        "role": "projection",
                        "packages": ["archkeel.render"],
                        "public": ["archkeel.render.html"],
                        "responsibilities": ["Render Core evidence."],
                        "forbidden_responsibilities": [],
                        "provenance": [provenance],
                        "inside": contract_path,
                    }
                ],
            }
        ),
    }
    root = _prepare_repo(tmp_path, files)
    config = ScanConfig(("src/archkeel",), "archkeel", "architecture-contract.json", "0" * 64)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and result.observation_complete == "PASS" and not result.diagnostics
    assessments = {item.id: item for item in result.rule_assessments}
    for rule in ("RENDER-COMPLETE-REQUIRES", "RENDER-NO-CYCLES"):
        assessment = assessments[f"render:{rule}"]
        assert assessment.status == ("FAIL" if backward_importer else "PASS")
        assert assessment.count == (1 if backward_importer else 0)
    interface = assessments["render:RENDER-INTERFACE"]
    assert (interface.status, interface.count) == ("PASS", 0)
