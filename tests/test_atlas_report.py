# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Atlas presents Core facts without embedding every source detail."""

import json
import re
import sys
from cProfile import Profile
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_module_explore import _sample

from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.observe import observe
from archkeel.ir.baseline import select_violations
from archkeel.ir.codec import (
    canonical_report_bytes,
    decode_canonical_model,
    parse_observation,
    value_bytes,
)
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import ReportFilter, RunResult
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import architecture_projection
from archkeel.render import html as html_renderer
from archkeel.render.html import render_architecture_html


def _result(model):
    return RunResult(
        "report",
        0,
        "PASS",
        "FAIL",
        "n/a",
        coverage=model.coverage,
        rule_assessments=rule_assessments(model, undecided_by_rule={}),
        architecture_projection=architecture_projection(
            model, architecture_report(model), (), violation_remedy="Review native findings"
        ),
    )


def _page(model):
    return render_architecture_html(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).decode()


def test_report_pages_derive_one_graph_per_page(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(tmp_path, uml=True)
    result = _result(model)
    encoded = canonical_report_bytes(model)
    with Profile() as work:
        page = render_architecture_html(
            result, encoded, repository="One target", architecture_href="architecture.json"
        )
        details = render_architecture_details(
            result, encoded, repository="One target", architecture_href="architecture.json"
        )
    assert page and len(details) == 1
    graph_builds = sum(
        entry.callcount for entry in work.getstats() if entry.code is architecture_report.__code__
    )
    assert graph_builds == 2


def test_atlas_structure_overview_retains_canonical_component_route(tmp_path):
    model = _sample(
        tmp_path,
        extra_files={
            "sample/core/helper.py": "def one():\n    return 1\n",
            "sample/core/helper2.py": "def two():\n    return 2\n",
        },
    )
    page = _page(model)
    component_id = next(
        item.id
        for item in _result(model).architecture_projection.components
        if item.scope == "core"
    )

    assert '<details class="report-section report-evidence atlas-structure-overview">' in page
    assert "<summary>Structure overview</summary>" in page
    assert "Top-level context" in page
    assert "Architecture boundaries require authored decisions" in page
    assert (
        f'<a href="?component={component_id}" data-atlas-component-route="{component_id}">core</a>'
    ) in page


def test_html_graph_omits_resolvable_record_id_lists_only(tmp_path):
    from archkeel.ir.graph_codec import report_bytes
    from archkeel.render.html import render_architecture_details, render_html

    model = _sample(tmp_path, uml=True)
    report = architecture_report(model)
    canonical = parse_observation(decode_canonical_model(json.loads(canonical_report_bytes(model))))
    canonical_ids = {item.id for section in canonical.sections for item in section.records}
    graph_record_ids = {
        record_id
        for graph in (report.observed, report.target)
        if graph is not None
        for item in (*graph.entities, *graph.relationships)
        for record_id in item.record_ids
    }
    assert graph_record_ids and graph_record_ids <= canonical_ids

    result = _result(model)
    documents = [
        render_html(result, model, repository="One target", architecture_href="architecture.json"),
        *render_architecture_details(
            result,
            canonical_report_bytes(model),
            repository="One target",
            architecture_href="architecture.json",
        ).values(),
    ]
    expected = json.loads(report_bytes(report))
    for document in documents:
        page = document.decode()
        match = re.search(
            r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S
        )
        assert match is not None
        actual = json.loads(match.group(1))
        for side in ("observed", "target"):
            expected_graph = expected[side]
            actual_graph = actual[side]
            for collection in ("entities", "relationships"):
                expected_items = expected_graph[collection]
                actual_items = actual_graph[collection]
                assert len(actual_items) == len(expected_items)
                assert actual_items == [
                    {key: value for key, value in item.items() if key != "record_ids"}
                    for item in expected_items
                ]
                assert all("record_ids" not in item for item in actual_items)


def test_atlas_inlines_pinned_elk_before_flow_script_under_offline_csp(tmp_path):
    model = _sample(tmp_path)
    page = _page(model)

    elk_script = '<script data-elkjs-version="0.12.0">'
    assert elk_script in page
    assert page.count(elk_script) == 1
    assert page.index(elk_script) < page.index('<script data-report-asset="explorer">')
    assert "Generated from flow.js; source-sha256=" in page
    assert "default-src 'none'" in page
    assert "script-src 'unsafe-inline'" in page
    assert "worker-src" not in page
    assert not re.search(r"<script\b[^>]*\bsrc=", page)


def _atlas(page):
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    data = json.loads(match.group(1))["atlas"]
    data["cells"] = [
        {
            "source_id": data["modules"][row[0]]["id"],
            "target_id": data["modules"][row[1]]["id"],
            "import_sites": row[2],
            "status": row[3],
            "permission": "UNKNOWN",
            "permission_reason": data["reference_ids"][data["cell_permission_reason_ref"]],
            "evidence_ids": row[4],
            "finding_ids": row[5],
            "reasons": [data["reference_ids"][index] for index in row[6]],
        }
        for row in data["cells"]
    ]
    data["rule_assessments"] = [
        {
            **row,
            "id": data["reference_ids"][row["id"]],
            "kind": data["reference_ids"][row["kind"]],
            "reason": data["reference_ids"][row["reason"]],
            "scope": data["reference_ids"][row["scope"]],
            "components": [data["reference_ids"][index] for index in row["components"]],
            "uncertainty_actions": [
                {**action, "next_action": data["reference_ids"][action["next_action"]]}
                for action in row["uncertainty_actions"]
            ],
            "evidence": [
                {**entry, "id": data["reference_ids"][entry["id"]]} for entry in row["evidence"]
            ],
        }
        for row in data["rule_assessments"]
    ]
    data["assignments"] = [
        dict(
            zip(
                ("id", "component_id", "candidate_ids", "ownership_status", "ownership_reason"),
                (
                    data["modules"][row[0]]["id"],
                    data["reference_ids"][row[1]] if row[1] is not None else None,
                    [data["reference_ids"][index] for index in row[2]],
                    row[3],
                    data["reference_ids"][row[4]],
                ),
                strict=True,
            )
        )
        for row in data["assignments"]
    ]
    for module in data["modules"]:
        module["symbol_coverage"] = data["symbol_coverages"][module["symbol_coverage"]]
    for level in data["levels"]:
        level["modules"] = [data["assignments"][index] for index in level["modules"]]
    return data


def test_default_report_is_one_authentic_repository_with_sparse_native_cells(tmp_path):
    model = _sample(tmp_path)
    page = _page(model)
    data = _atlas(page)
    assert data["repository"] == "One target"
    result = _result(model)
    audit = json.loads(canonical_report_bytes(model))
    assert data["declared_rules"] == result.declared_rules
    assert data["observation_complete"] == result.observation_complete
    assert (
        not {
            "coverage",
            "required_relationships",
            "analyzer_digest",
            "contract_digest",
            "finding_count",
        }
        & data.keys()
    )
    assert audit["contract"]["digest"] == model.contract.digest
    assert audit["analyzer"]["code_digest"] == model.analyzer.code_digest
    assert str(model.source.git_head) in page
    assert model.source.source_digest in page
    assert model.contract.digest in page
    assert data["rule_assessments"] == [
        {
            "id": item.id,
            "kind": item.kind,
            "status": item.status,
            "count": item.count,
            "undecided": item.undecided,
            "reason": item.reason,
            "scope": item.scope,
            "scope_id": None,
            "components": list(item.components),
            "component_ids": list(item.components),
            "evaluation_proven": item.evaluation_proven,
            "uncertainty_actions": [],
            "evidence_count": 0,
            "evidence": [],
        }
        for item in result.rule_assessments or ()
    ]
    assert {item["id"] for item in data["components"]} == {"core", "peer"}
    projection = _result(model).architecture_projection
    components = {item.id: item for item in projection.components}
    for item in data["components"]:
        public = components[item["id"]].public
        if public is None:
            assert item["public"] is None
        else:
            assert [data["reference_ids"][index] for index in item["public"]] == list(public)
    assert len(data["cells"]) == 1
    cell = data["cells"][0]
    assert cell["status"] == "FAIL" and cell["permission"] == "UNKNOWN"
    assert cell["import_sites"] == 2
    assert cell["evidence_ids"] and cell["finding_ids"] and cell["reasons"]
    assert "data-ds=" not in page
    assert "Simulate violation" not in page
    assert "EXT-TS" not in page
    assert "Worth a look" in page
    assert 'aria-label="Switch to light theme"' in page
    page_bytes = len(page.encode())
    elk_bytes = (
        (Path(__file__).parents[1] / "src/archkeel/render/assets/elkjs-0.12.0.bundled.js")
        .stat()
        .st_size
    )
    # The Explorer adds inline search, perspectives and export; ELK still dominates the file.
    assert page_bytes < 2_000_000
    assert page_bytes - elk_bytes < 400_000


def test_atlas_header_shows_one_verdict_line_with_native_rule_counts(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(tmp_path)
    result = _result(model)
    page = _page(model)
    details = next(
        iter(
            render_architecture_details(
                result,
                canonical_report_bytes(model),
                repository="One target",
                architecture_href="architecture.json",
            ).values()
        )
    ).decode()
    (line,) = re.findall(r'<p class="verdict-line".*?</p>', page, re.S)
    text = re.sub(r"<[^>]+>", "", line)
    counts = {
        status: sum(item.status == status for item in result.rule_assessments)
        for status in ("PASS", "UNKNOWN")
    }
    assert f"Rules {result.declared_rules}" in text
    assert f"{counts['PASS']} PASS · {counts['UNKNOWN']} UNKNOWN" in text
    assert f"Source observation {result.observation_complete}" in text
    assert model.source.git_head[:7] in text
    assert model.source.git_head not in text
    assert model.source.git_head in page.split("Snapshot and audit")[1]
    for document in (page, details):
        assert '<article class="verdict-card"' not in document
        assert "NOT APPLICABLE" not in document
        assert "atlas-status-key" not in document
    assert 'class="verdict-line"' not in details
    assert f"Whole-run rules: {result.declared_rules}" in details
    assert f"Source observation: {result.observation_complete}" in details
    assert '<a href="architecture.report.html">Architecture overview</a>' in details
    assert "Symbol inventory:" in details


def test_partial_lexical_inventory_keeps_symbols_and_uncertainty(tmp_path):
    model = _sample(tmp_path, extra_files={"sample/inventory.py": "def observed():\n    pass\n"})
    data = _atlas(_page(model))
    module = next(item for item in data["modules"] if item["name"] == "sample.inventory")
    assert module["symbols"] == 1
    assert module["symbol_coverage"]
    assert any(item["status"] != "complete" for item in module["symbol_coverage"])
    assert not any(question["kind"] == "heavy" for question in data["questions"])


def test_ambiguous_and_unowned_assignments_remain_distinct(tmp_path):
    data = _atlas(_page(_sample(tmp_path, ambiguous=True)))
    level = next(item for item in data["levels"] if item["parent_id"] is None)
    names = {item["id"]: item["name"] for item in data["modules"]}
    ambiguous = next(item for item in level["modules"] if names[item["id"]] == "sample.core")
    assert ambiguous["component_id"] is None
    assert ambiguous["candidate_ids"] == ["core", "overlap"]
    assert ambiguous["ownership_status"] == "UNKNOWN"
    unowned = next(item for item in level["modules"] if names[item["id"]] == "sample.unowned")
    assert unowned["candidate_ids"] == [] and unowned["ownership_status"] == "UNKNOWN"


def test_atlas_findings_and_balances_match_core_by_level(tmp_path):
    model = _sample(tmp_path)
    result = _result(model)
    data = _atlas(_page(model))
    records = {item.id: item for item in model.records("violations") or ()}
    finding_id = {index: item["id"] for index, item in enumerate(data["findings"])}
    evidence = {item.id: item for item in model.evidence}
    assert {finding_id[index] for index in data["levels"][0]["finding_ids"]} == set(records)
    for component in result.architecture_projection.components:
        level = next(item for item in data["levels"] if item["parent_id"] == component.id)
        selected = select_violations(
            model, ReportFilter(only_violations=True, component=component.scope)
        )
        assert {finding_id[index] for index in level["finding_ids"]} == {
            item.id for item in selected
        }
    for entry in data["findings"]:
        record = records[entry["id"]]
        assert entry["rule_ids"] == list(record.rule_ids)
        assert entry["kind"] == record.kind
        assert entry["title"] == record.title
        assert (
            data["reference_ids"][entry["remedy_ref"]]
            == result.architecture_projection.violation_remedy
        )
        source = min(
            (evidence[item] for item in record.evidence_ids if item in evidence),
            key=lambda item: (item.file, item.line),
        )
        assert (entry["path"], entry["line"]) == (source.file, source.line)
    for expected in result.architecture_projection.levels:
        actual = next(item for item in data["levels"] if item["parent_id"] == expected.parent_id)
        assert actual["balance"] == {
            "declared": expected.declared,
            "used": expected.used,
            "allowed_unused": expected.unused,
            "undeclared": expected.undeclared,
        }
        assert len(actual["deviation_ids"]) == (expected.unused or 0) + (expected.undeclared or 0)
    projection_level_ids = {item.parent_id for item in result.architecture_projection.levels}
    for component in result.architecture_projection.components:
        if component.id not in projection_level_ids:
            leaf = next(item for item in data["levels"] if item["parent_id"] == component.id)
            assert leaf["balance"] == {
                "declared": 0,
                "used": 0,
                "allowed_unused": 0,
                "undeclared": 0,
            }
    assert data["balance"] == {
        field: sum(getattr(level, attr) or 0 for level in result.architecture_projection.levels)
        for field, attr in (
            ("declared", "declared"),
            ("used", "used"),
            ("allowed_unused", "unused"),
            ("undeclared", "undeclared"),
        )
    }


def test_atlas_unavailable_projection_does_not_report_zero_balances(tmp_path):
    model = _sample(tmp_path)
    assert architecture_report(model).target is not None
    sections = tuple(
        replace(
            section,
            records=tuple(
                record
                for record in section.records
                if record.kind not in {"architecture_target", "uml_target"}
            ),
        )
        if section.name == "declarations" and section.records is not None
        else section
        for section in model.sections
    )
    unavailable = replace(model, sections=sections)
    result = _result(unavailable)
    assert result.architecture_projection is not None
    assert result.architecture_projection.levels == ()

    data = _atlas(_page(unavailable))
    assert data["levels"]
    for level in data["levels"]:
        assert level["balance"] == {
            "declared": None,
            "used": None,
            "allowed_unused": None,
            "undeclared": None,
        }
    assert data["balance"] == {
        "declared": None,
        "used": None,
        "allowed_unused": None,
        "undeclared": None,
    }


def test_allowed_dependency_without_import_is_a_core_sourced_unused_deviation(tmp_path):
    from test_target_graph import _repository

    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe
    from archkeel.ir.codec import decode_canonical_model, parse_observation

    root, config = _repository(tmp_path)
    contract = json.loads((root / config.contract).read_bytes())
    contract["components"][0]["public"] = ["sample.core:Service"]
    peer = dict(contract["components"][0])
    peer.update(id="peer", label="peer", packages=["sample.peer"], namespace="sample.peer")
    contract["components"].append(peer)
    contract["rules"] = [
        {
            "id": "peer-core-permission",
            "kind": "allowed_dependency",
            "source": "sample.peer",
            "target": "sample.core",
            "rationale": "Allow the peer to use the core interface.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    (root / config.contract).write_text(json.dumps(contract))
    (root / "sample/peer.py").write_text("value = 1\n")
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    data = _atlas(_page(model))
    balance = next(level["balance"] for level in data["levels"] if level["parent_id"] is None)
    assert balance == {"declared": 1, "used": 0, "allowed_unused": 1, "undeclared": 0}
    deviation = next(item for item in data["deviations"] if item["kind"] == "allowed_unused")
    assert (deviation["source_id"], deviation["target_id"]) == ("peer", "core")
    core = next(item for item in data["components"] if item["id"] == "core")
    assert [data["reference_ids"][index] for index in core["public"]] == ["sample.core:Service"]


@pytest.mark.parametrize("only", [None, "architecture"])
def test_rerun_cleans_only_obsolete_generated_detail_pages(tmp_path, capsys, monkeypatch, only):
    root = _prepare_repo(tmp_path, {})
    output = tmp_path / "published" / "architecture.json"
    output.parent.mkdir()
    obsolete = (
        output.parent / "architecture.detail-component-0123456789abcdef.html",
        output.parent / "architecture.detail-unknown.html",
    )
    preserved = (
        output.parent / "architecture.detail-custom.html",
        output.parent / "other.detail-component-0123456789abcdef.html",
    )
    for path in (*obsolete, *preserved):
        path.write_text("old artifact")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    arguments = ["report", "--root", str(root), "--output", str(output)]
    if only is not None:
        arguments.extend(("--only", only))
    assert main(arguments) == 0
    capsys.readouterr()
    if only is None:
        assert not any(path.exists() for path in obsolete)
        assert (output.parent / "architecture.detail.html").exists()
    else:
        assert all(path.exists() for path in obsolete)
        assert not (output.parent / "architecture.detail.html").exists()
    assert all(path.read_text() == "old artifact" for path in preserved)


def test_component_detail_links_are_relative_and_keep_shared_uml(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(tmp_path, uml=True)
    encoded = canonical_report_bytes(model)
    result = _result(model)
    details = render_architecture_details(
        result, encoded, repository="One target", architecture_href="architecture.json"
    )
    data = _atlas(_page(model))
    assert set(details) == {"architecture.detail.html"}
    for component in data["components"]:
        assert component["id"]
        assert data["detail_page"] in details
        page = details["architecture.detail.html"].decode()
        assert 'id="flow-data"' in page
        assert "architecture.json" in page
        assert "fetch(" not in page
        assert "default-src 'none'" in page


def test_findings_show_only_distinct_nested_annotation_without_deduplication(tmp_path):
    model = _sample(tmp_path)
    violations = model.records("violations") or ()
    assert len(violations) >= 2
    replacement = {}
    for index, record in enumerate(violations[:2]):
        values = dict(record.data.entries)
        values["annotation"] = "Base"
        values["nested_annotation"] = "dict[str, float]" if index == 0 else "Base"
        replacement[record.id] = replace(
            record, data=replace(record.data, entries=tuple(values.items()))
        )
    model = replace(
        model,
        sections=tuple(
            replace(
                section,
                records=tuple(replacement.get(record.id, record) for record in section.records),
            )
            for section in model.sections
        ),
    )
    findings = _atlas(_page(model))["findings"]
    assert len(findings) == len(violations)
    by_id = {finding["id"]: finding for finding in findings}
    assert by_id[violations[0].id]["nested_annotation"] == "dict[str, float]"
    assert "nested_annotation" not in by_id[violations[1].id]


def test_shared_detail_snapshot_retains_cross_component_method_context(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(
        tmp_path,
        extra_files={
            "sample/core.py": "from sample.peer import Client\nClient.run()\n",
            "sample/peer.py": (
                "class Client:\n    @staticmethod\n    def run() -> int:\n        return 1\n"
            ),
        },
    )
    details = render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    )
    page = details["architecture.detail.html"].decode()
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    snapshot = json.loads(match.group(1))
    observed = snapshot["observed"]
    entities = {item["id"]: item for item in observed["entities"]}
    method = next(item for item in observed["entities"] if item["kind"] == "method")
    classifier = entities[method["parent_id"]]
    assert classifier["kind"] == "class" and classifier["qualified_name"] == "sample.peer.Client"
    assert any(
        edge["kind"] == "calls" and edge["target_id"] == method["id"]
        for edge in observed["relationships"]
    )


def test_shared_detail_snapshot_retains_nested_component_routes(tmp_path):
    from test_target_graph import _nested_repository

    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe
    from archkeel.ir.codec import decode_canonical_model, parse_observation
    from archkeel.render.html import render_architecture_details

    root, config = _nested_repository(tmp_path)
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    assert any(intent.parent_id for intent in report.target.component_intents)
    details = render_architecture_details(
        _result(model),
        encoded,
        repository="Nested",
        architecture_href="architecture.json",
    )
    page = details["architecture.detail.html"].decode()
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    navigation = json.loads(match.group(1))["navigation"]
    routes = {item["id"]: item for item in navigation["component_path"]}
    for intent in report.target.component_intents:
        assert intent.component_id in routes
        if intent.parent_id:
            assert intent.parent_id in routes
            assert routes[intent.component_id]["parent_id"] == intent.parent_id


def _boundary_permission_report(tmp_path):
    from test_boundary_type_native_iterables import _fixture
    from test_boundary_types_contained_mapping import _commit_report_fixture

    _fixture(tmp_path, facade=True)
    from test_analyzer import _component

    implementation = tmp_path / "sample/app/impl.py"
    implementation.write_text(
        implementation.read_text()
        + "\nclass BaseLiteralGenerator:\n    def generate(self) -> Iterable[object]: return []\n"
    )
    facade = tmp_path / "sample/app/__init__.py"
    facade.write_text(
        facade.read_text()
        + "\nfrom .impl import BaseLiteralGenerator\n__all__.append('BaseLiteralGenerator')\n"
    )
    (tmp_path / "sample/other.py").write_text("def unrelated() -> None: pass\n")
    contract = json.loads((tmp_path / "contract.json").read_text())
    contract["components"].append(_component("other", public=["sample.other:unrelated"]))
    contract["components"][0]["public"].append("sample.app:BaseLiteralGenerator")
    contract["rules"][0]["allowed_positions"].append(
        {
            "qualified_name": "sample.app.BaseLiteralGenerator.generate",
            "position": "return",
            "annotation": "Iterable[object]",
            "container_depth": 1,
        }
    )
    contract["rules"][0]["allowed_positions"].append(
        {
            "qualified_name": "sample.app.unused",
            "position": "return",
            "annotation": "object",
        }
    )
    contract["schema_version"] = "2.2.0"
    contract["declarations"] = {
        "uml": {
            "schema_version": "1.0.0",
            "entities": [
                {
                    "id": "literal-class",
                    "kind": "class",
                    "qualified_name": "sample.app.BaseLiteralGenerator",
                    "parent_id": "COMP-APP",
                    "language": "python",
                    "presence": "planned",
                    "responsibilities": ["Generate literal values."],
                    "provenance": ["docs/architecture/sample.md"],
                },
                {
                    "id": "literal-generate",
                    "kind": "method",
                    "qualified_name": "sample.app.BaseLiteralGenerator.generate",
                    "parent_id": "literal-class",
                    "language": "python",
                    "presence": "planned",
                    "responsibilities": ["Generate literal values."],
                    "provenance": ["docs/architecture/sample.md"],
                },
            ],
        }
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0.0.0"\nrequires-python = ">=3.11"\n'
    )
    _commit_report_fixture(tmp_path)
    output = tmp_path / "out/architecture.json"
    assert main(["report", "--root", str(tmp_path), "--output", str(output), "--json"]) == 0
    return output


def _flow_payload(path):
    match = re.search(
        r'<script id="flow-data" type="application/json">(.*?)</script>', path.read_text(), re.S
    )
    assert match
    return json.loads(match.group(1))


def test_boundary_permissions_shared_saved_cli_payload(tmp_path):
    output = _boundary_permission_report(tmp_path)
    overview = _flow_payload(output.with_suffix(".report.html"))
    detail = _flow_payload(output.with_suffix(".detail.html"))
    permissions = overview["boundary_permissions"]
    assert permissions == detail["boundary_permissions"]
    declarations = permissions["declared"]
    applied = permissions["applied"]
    unused = next(row for row in declarations if row["qualified_name"] == "sample.app.unused")
    assert unused["rationale"] and unused["provenance"]
    assert unused["component_ids"] and not unused["entity_ids"]
    assert not any(row["data"]["qualified_name"] == "sample.app.unused" for row in applied)
    opaque = next(row for row in applied if row["data"]["qualified_name"] == "sample.app.read")
    assert opaque["data"]["accepted_opacity"] is True
    assert opaque["declaration_id"]
    assert opaque["entity_ids"] and opaque["locations"]
    assert opaque["id"] not in {row["id"] for row in overview["atlas"]["findings"]}
    assert opaque["id"] not in {row["id"] for row in detail["findings"]}


def test_boundary_permissions_nested_same_labels_keep_exact_contract_scope(tmp_path):
    from test_target_graph import _nested_repository

    from archkeel.render.atlas import boundary_permissions_payload

    root, config = _nested_repository(tmp_path)
    for path in (config.contract, "inside.json", "leaf.json"):
        raw = json.loads((root / path).read_text())
        raw["components"][0]["label"] = "core"
        raw["rules"].append(
            {
                "id": "NATIVE",
                "kind": "boundary_types",
                "source": "sample.core",
                "rationale": "Accept this exact result.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
                "allowed_positions": [
                    {
                        "qualified_name": "sample.core.Service.run",
                        "position": "return",
                        "annotation": "object",
                    }
                ],
            }
        )
        (root / path).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and result.architecture_projection is not None
    assert all(item.kind == "rule_without_subjects" for item in result.diagnostics)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    payload = boundary_permissions_payload(
        model, architecture_report(model), result.architecture_projection
    )
    rows = payload["declared"]
    assert len(rows) == 3
    assert len({row["id"] for row in rows}) == 3
    for row in rows:
        expected = [
            component.id
            for component in result.architecture_projection.components
            if component.parent_id == row["contract_scope_id"]
            and component.namespace == "sample.core"
        ]
        assert row["component_ids"] == expected
        assert len(expected) == 1


def test_boundary_permission_unmapped_ambiguous_and_optional_metadata(tmp_path):
    from archkeel.ir.model import RecordData
    from archkeel.render.atlas import boundary_permissions_payload

    output = _boundary_permission_report(tmp_path)
    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    projection = _result(model).architecture_projection
    fact = next(
        row for row in model.records("typing_signals") if row.kind == "boundary_type_allowance"
    )
    changed = replace(
        fact,
        subjects=(),
        fact_ids=(),
        evidence_ids=(),
        title="</script><img src=x onerror=alert(1)>",
        data=RecordData(
            tuple(
                {
                    **dict(fact.data.entries),
                    "unrelated_metadata": RecordData((("nested", "ignored"),)),
                    "annotation": "<script>alert(1)</script>",
                }.items()
            )
        ),
    )
    model = replace(
        model,
        sections=tuple(
            replace(section, records=(changed,)) if section.name == "typing_signals" else section
            for section in model.sections
        ),
    )
    payload = boundary_permissions_payload(model, architecture_report(model), projection)
    row = payload["applied"][0]
    assert row["routes"] == row["component_ids"] == row["entity_ids"] == row["locations"] == []
    assert row["declaration_id"] is None
    assert "unrelated_metadata" not in row["data"]
    json.dumps(payload)
    duplicated = replace(
        projection, permission_rules=(*projection.permission_rules, *projection.permission_rules)
    )
    original = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    duplicate_rows = boundary_permissions_payload(
        original, architecture_report(original), duplicated
    )["applied"]
    assert all(row["declaration_id"] is None for row in duplicate_rows)


def test_boundary_permission_declared_exact_module_owner_without_application(tmp_path):
    root = _prepare_repo(
        tmp_path,
        {
            "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
            "sample/api.py": "def read() -> int: return 1\n",
            "archkeel.toml": (
                '[scan]\nroots = ["sample"]\nnamespace = "sample"\ncontract = "contract.json"\n'
            ),
            "docs/target.md": "Explicit native result decision.\n",
            "contract.json": json.dumps(
                {
                    "schema_version": "2.2.0",
                    "components": [
                        {
                            "id": "API",
                            "label": "api",
                            "role": "component",
                            "packages": [],
                            "exact_modules": ["sample.api"],
                            "responsibilities": ["Own the API."],
                            "forbidden_responsibilities": [],
                            "provenance": ["docs/target.md"],
                            "public": ["sample.api:read"],
                        }
                    ],
                    "rules": [
                        {
                            "id": "NATIVE",
                            "kind": "boundary_types",
                            "source": "sample.api",
                            "rationale": "Accept the planned native result.",
                            "decided_by": "architect",
                            "provenance": ["docs/target.md"],
                            "allowed_positions": [
                                {
                                    "qualified_name": "sample.api.native",
                                    "position": "return",
                                    "annotation": "object",
                                }
                            ],
                        }
                    ],
                }
            ),
        },
    )
    output = root / "out/architecture.json"
    assert main(["report", "--root", str(root), "--output", str(output), "--json"]) == 0
    permissions = _flow_payload(output.with_suffix(".report.html"))["boundary_permissions"]
    assert permissions["applied"] == []
    assert permissions["declared"][0]["component_ids"] == ["API"]
    assert permissions["declared"][0]["entity_ids"] == []


def test_boundary_permission_field_default_keeps_optional_depth_distinct(tmp_path):
    from archkeel.ir.model import RecordData
    from archkeel.render.atlas import boundary_permissions_payload

    output = _boundary_permission_report(tmp_path)
    original = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    projection = _result(original).architecture_projection
    fact = next(
        row
        for row in original.records("typing_signals")
        if row.kind == "boundary_type_allowance"
        and row.data.get("qualified_name") == "sample.app.read"
    )
    declaration_id = boundary_permissions_payload(
        original, architecture_report(original), projection
    )["applied"][0]["declaration_id"]
    assert declaration_id
    for missing, expected in (("field_path", declaration_id), ("container_depth", None)):
        changed = replace(
            fact,
            data=RecordData(
                tuple((key, value) for key, value in fact.data.entries if key != missing)
            ),
        )
        model = replace(
            original,
            sections=tuple(
                replace(section, records=(changed,))
                if section.name == "typing_signals"
                else section
                for section in original.sections
            ),
        )
        row = boundary_permissions_payload(model, architecture_report(model), projection)[
            "applied"
        ][0]
        assert row["declaration_id"] == expected


_ALIAS_PAIR = {
    "origin": "sample.app.impl:Packet",
    "shape": (
        "tuple[tuple[str, list[object]] | tuple[str, list[object], "
        "sample.app.types.Metadata], list[dict[str, object]]]"
    ),
}
_ABSENT_ALIAS_PAIR = object()


def _alias_permission_payload(
    tmp_path,
    declared,
    applied,
    *,
    duplicate=False,
    key_declared=_ABSENT_ALIAS_PAIR,
    key_applied=_ABSENT_ALIAS_PAIR,
    applied_changes=None,
):
    from archkeel.ir.facts_codec import freeze_data
    from archkeel.render.atlas import boundary_permissions_payload

    output = _boundary_permission_report(tmp_path)
    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    projection = _result(model).architecture_projection
    fact = next(
        row for row in model.records("typing_signals") if row.kind == "boundary_type_allowance"
    )
    permission = next(
        row for row in projection.permission_rules if row.declaration.kind == "boundary_types"
    )
    data = json.loads(value_bytes(fact.data))
    selector = {
        key: value
        for key, value in data.items()
        if key
        in {
            "qualified_name",
            "position",
            "field_path",
            "annotation",
            "container_depth",
            "mapping_depth",
        }
    }
    if declared is not _ABSENT_ALIAS_PAIR:
        selector["alias_body"] = declared
    if key_declared is not _ABSENT_ALIAS_PAIR:
        selector["key_alias_body"] = key_declared
    declaration_data = json.loads(value_bytes(permission.declaration.data))
    declaration = replace(
        permission.declaration,
        data=freeze_data({**declaration_data, "allowed_positions": [selector]}),
    )
    permission = replace(permission, declaration=declaration)
    if applied is not _ABSENT_ALIAS_PAIR:
        data["alias_body"] = applied
    if key_applied is not _ABSENT_ALIAS_PAIR:
        data["key_alias_body"] = key_applied
    for name, value in (applied_changes or {}).items():
        if value is _ABSENT_ALIAS_PAIR:
            data.pop(name, None)
        else:
            data[name] = value
    fact = replace(fact, data=freeze_data(data), provenance=("fact-own-provenance",))
    model = replace(
        model,
        sections=tuple(
            replace(section, records=(fact,))
            if section.name == "typing_signals"
            else replace(
                section,
                records=tuple(
                    declaration if row.id == declaration.id else row for row in section.records
                ),
            )
            if section.name == "declarations"
            else section
            for section in model.sections
        ),
    )
    model = parse_observation(decode_canonical_model(json.loads(canonical_report_bytes(model))))
    projection = replace(
        projection, permission_rules=(permission, permission) if duplicate else (permission,)
    )
    return boundary_permissions_payload(model, architecture_report(model), projection), model


@pytest.mark.parametrize(
    "declared,applied,joined",
    [
        (_ALIAS_PAIR, _ALIAS_PAIR, True),
        (_ALIAS_PAIR, dict(reversed(tuple(_ALIAS_PAIR.items()))), True),
        (_ALIAS_PAIR, {**_ALIAS_PAIR, "origin": "sample.app.moved:Packet"}, False),
        (_ALIAS_PAIR, {**_ALIAS_PAIR, "shape": _ALIAS_PAIR["shape"] + " | None"}, False),
        (_ALIAS_PAIR, _ABSENT_ALIAS_PAIR, False),
        (_ABSENT_ALIAS_PAIR, _ALIAS_PAIR, False),
        (_ABSENT_ALIAS_PAIR, _ABSENT_ALIAS_PAIR, True),
        *[
            (bad, bad, False)
            for bad in [
                None,
                [],
                "Packet",
                {},
                {"origin": "only"},
                {"shape": "only"},
                {**_ALIAS_PAIR, "extra": "no"},
                {**_ALIAS_PAIR, "origin": ""},
                {**_ALIAS_PAIR, "shape": ""},
                {**_ALIAS_PAIR, "shape": " "},
                {**_ALIAS_PAIR, "origin": 7},
                {**_ALIAS_PAIR, "shape": []},
            ]
        ],
    ],
)
def test_bound_alias_permission_join_requires_exact_valid_pair(tmp_path, declared, applied, joined):
    payload, model = _alias_permission_payload(tmp_path, declared, applied)
    row = payload["applied"][0]
    assert bool(row["declaration_id"]) is joined
    assert bool(row["rationale"]) is joined
    assert row["provenance"] == ("fact-own-provenance",)
    if applied is not _ABSENT_ALIAS_PAIR:
        assert row["data"]["alias_body"] == applied
    if declared is not _ABSENT_ALIAS_PAIR:
        assert payload["declared"][0]["alias_body"] == declared
    json.dumps(payload)
    audit = json.loads(value_bytes(model.records("typing_signals")[0].data))
    assert ("alias_body" in audit) is (applied is not _ABSENT_ALIAS_PAIR)
    if applied is not _ABSENT_ALIAS_PAIR:
        assert audit["alias_body"] == applied


@pytest.mark.parametrize(
    "declared",
    [
        _ALIAS_PAIR,
        {**_ALIAS_PAIR, "shape": _ALIAS_PAIR["shape"] + " | None"},
        {**_ALIAS_PAIR, "origin": "sample.app.other:Packet"},
    ],
)
def test_bound_alias_duplicate_exact_or_near_declarations_do_not_join(tmp_path, declared):
    payload, _ = _alias_permission_payload(tmp_path, declared, _ALIAS_PAIR, duplicate=True)
    assert payload["applied"][0]["declaration_id"] is None


def _bound_alias_report(tmp_path, *, facade=True):
    from test_boundary_type_bound_aliases import _fixture
    from test_boundary_types_contained_mapping import _commit_report_fixture

    _fixture(tmp_path, facade=facade)
    _commit_report_fixture(tmp_path)
    output = tmp_path / "out/architecture.json"
    assert main(["report", "--root", str(tmp_path), "--output", str(output), "--json"]) == 0
    return output


@pytest.mark.parametrize("facade", [False, True])
def test_bound_alias_real_cli_wire_and_shared_reports(tmp_path, facade):
    output = _bound_alias_report(tmp_path, facade=facade)
    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    assert canonical_report_bytes(model) == output.read_bytes()
    overview = _flow_payload(output.with_suffix(".report.html"))
    detail = _flow_payload(output.with_suffix(".detail.html"))
    assert overview["boundary_permissions"] == detail["boundary_permissions"]
    permissions = overview["boundary_permissions"]
    assert len(permissions["declared"]) == len(permissions["applied"]) == 4
    assert all(row["alias_body"] == _ALIAS_PAIR for row in permissions["declared"])
    for row in permissions["applied"]:
        assert row["data"]["alias_body"] == _ALIAS_PAIR
        assert row["declaration_id"] and row["rationale"] and row["routes"]
        assert row["data"]["observed_container_depth"] == (
            3 if row["data"].get("accepted_opacity") else 2
        )
        assert ("container_depth" in row["data"]) is bool(row["data"].get("accepted_opacity"))
        assert row["locations"] and row["evidence_ids"] and row["fact_ids"]
    assert len(model.records("violations")) == 1
    assert model.records("unknowns")


@pytest.mark.parametrize("pair_name", ["alias_body", "key_alias_body"])
@pytest.mark.parametrize(
    "mutation,joined",
    [
        ("valid", True),
        ("reordered", True),
        ("missing", False),
        ("undeclared", False),
        ("provider", False),
        ("shape", False),
        *[
            (bad, False)
            for bad in [
                None,
                [],
                "Alias",
                {},
                {"origin": "only"},
                {"shape": "only"},
                {"origin": "provider:Alias", "shape": "str | None", "extra": "no"},
                {"origin": "", "shape": "str | None"},
                {"origin": "provider:Alias", "shape": " "},
                {"origin": 7, "shape": "str | None"},
                {"origin": "provider:Alias", "shape": []},
            ]
        ],
    ],
)
def test_both_alias_permission_pairs_join_exactly(tmp_path, pair_name, mutation, joined):
    from test_boundary_type_bound_aliases import _GROUP_BINDING, _KEY_BINDING

    declared = {"alias_body": _GROUP_BINDING, "key_alias_body": _KEY_BINDING}
    applied = dict(declared)
    good = declared[pair_name]
    if mutation == "reordered":
        applied[pair_name] = dict(reversed(tuple(good.items())))
    elif mutation == "missing":
        applied[pair_name] = _ABSENT_ALIAS_PAIR
    elif mutation == "undeclared":
        declared[pair_name] = _ABSENT_ALIAS_PAIR
    elif mutation == "provider":
        applied[pair_name] = {**good, "origin": "sample.app.other:Alias"}
    elif mutation == "shape":
        applied[pair_name] = {**good, "shape": good["shape"] + " | None"}
    elif mutation != "valid":
        declared[pair_name] = applied[pair_name] = mutation
    payload, model = _alias_permission_payload(
        tmp_path,
        declared["alias_body"],
        applied["alias_body"],
        key_declared=declared["key_alias_body"],
        key_applied=applied["key_alias_body"],
    )
    row = payload["applied"][0]
    assert bool(row["declaration_id"]) is joined
    assert bool(row["rationale"]) is joined
    audit = json.loads(value_bytes(model.records("typing_signals")[0].data))
    for name, pair in applied.items():
        assert (name in row["data"]) is (pair is not _ABSENT_ALIAS_PAIR)
        if pair is not _ABSENT_ALIAS_PAIR:
            assert row["data"][name] == audit[name] == pair
    assert row["provenance"] == ("fact-own-provenance",)
    json.dumps(payload)


_TYPED_UNION_BODY = "dict[str, float] | dict[tuple[int, int], float] | dict[SexKey, float]"
_EXPANDED_UNION_BODY = _TYPED_UNION_BODY.replace("SexKey", "str | None")


def _typed_union_report(
    tmp_path, *, facade=False, annotation="GroupMask", body=_TYPED_UNION_BODY, local_key=False
):
    from test_boundary_type_bound_aliases import _typed_union_fixture
    from test_boundary_types_contained_mapping import _commit_report_fixture

    _typed_union_fixture(
        tmp_path, facade=facade, annotation=annotation, body=body, local_key=local_key
    )
    _commit_report_fixture(tmp_path)
    output = tmp_path / "out/architecture.json"
    assert main(["report", "--root", str(tmp_path), "--output", str(output), "--json"]) == 0
    return output


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize(
    "annotation,body,local_key,root_pair,key_pair,count",
    [
        ("GroupMask", _TYPED_UNION_BODY, False, True, True, 3),
        (_TYPED_UNION_BODY, _TYPED_UNION_BODY, False, False, True, 3),
        (_EXPANDED_UNION_BODY, _TYPED_UNION_BODY, False, False, False, 3),
        ("GroupMask", _EXPANDED_UNION_BODY, False, True, False, 3),
        ("GroupMask", _TYPED_UNION_BODY, True, True, True, 3),
        (_TYPED_UNION_BODY, _TYPED_UNION_BODY, True, False, True, 3),
        (
            "dict[str, float] | dict[tuple[int, int], int]",
            _TYPED_UNION_BODY,
            False,
            False,
            False,
            2,
        ),
    ],
)
def test_typed_union_real_cli_wire_and_shared_reports(
    tmp_path,
    facade,
    annotation,
    body,
    local_key,
    root_pair,
    key_pair,
    count,
):
    output = _typed_union_report(
        tmp_path, facade=facade, annotation=annotation, body=body, local_key=local_key
    )
    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    assert canonical_report_bytes(model) == output.read_bytes()
    permissions = _flow_payload(output.with_suffix(".report.html"))["boundary_permissions"]
    assert permissions == _flow_payload(output.with_suffix(".detail.html"))["boundary_permissions"]
    assert len(permissions["declared"]) == 1 and len(permissions["applied"]) == count
    declaration = permissions["declared"][0]
    grants = {
        row.id: json.loads(value_bytes(row.data))
        for row in model.records("typing_signals")
        if row.kind == "boundary_type_allowance"
    }
    for applied in permissions["applied"]:
        assert applied["declaration_id"] == declaration["id"] and applied["rationale"]
        for pair_name, present in [("alias_body", root_pair), ("key_alias_body", key_pair)]:
            assert (pair_name in applied["data"]) is (pair_name in declaration) is present
            if present:
                assert (
                    applied["data"][pair_name]
                    == declaration[pair_name]
                    == grants[applied["id"]][pair_name]
                )
        assert (
            applied["routes"]
            and applied["locations"]
            and applied["fact_ids"]
            and applied["evidence_ids"]
        )
    assert len(model.records("violations")) == 1 and model.records("unknowns")


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.other"},
        {"position": "argument"},
        {"annotation": "Changed"},
        {"field_path": "payload"},
        {"container_depth": 2},
        {"container_depth": _ABSENT_ALIAS_PAIR},
        {"mapping_depth": 1},
    ],
)
def test_both_alias_permission_pairs_cannot_cross_selector_coordinates(tmp_path, change):
    from test_boundary_type_bound_aliases import _GROUP_BINDING, _KEY_BINDING

    payload, _ = _alias_permission_payload(
        tmp_path,
        _GROUP_BINDING,
        _GROUP_BINDING,
        key_declared=_KEY_BINDING,
        key_applied=_KEY_BINDING,
        applied_changes=change,
    )
    applied = payload["applied"][0]
    assert applied["declaration_id"] is None and applied["rationale"] is None


@pytest.mark.parametrize(
    "filter",
    [
        None,
        ReportFilter(only_violations=True),
        ReportFilter(only_calls=True),
        ReportFilter(only_architecture=True),
        ReportFilter(only_architecture=True, full_architecture=True),
        ReportFilter(rule="R1"),
        ReportFilter(component="core"),
    ],
)
def test_pair_preserves_every_filter(tmp_path, filter):
    model = _sample(tmp_path, uml=True)
    result = replace(_result(model), report_filter=filter)
    payload = canonical_report_bytes(model)
    kw = dict(repository="One target", architecture_href="custom.name.json")
    expected = html_renderer.render_architecture_details(result, payload, **kw)
    expected["custom.name.report.html"] = html_renderer.render_architecture_html(
        result, payload, **kw
    )
    assert html_renderer.render_architecture_pages(result, payload, **kw) == tuple(expected.items())


def test_pair_without_projection_preserves_legacy_page(tmp_path):
    model = _sample(tmp_path)
    result = replace(_result(model), architecture_projection=None)
    payload = canonical_report_bytes(model)
    kw = dict(repository="One target", architecture_href="architecture.json")
    assert html_renderer.render_architecture_pages(result, payload, **kw) == (
        ("architecture.report.html", html_renderer.render_architecture_html(result, payload, **kw)),
    )


def test_pair_decodes_and_projects_once(tmp_path, monkeypatch):
    model = _sample(tmp_path, uml=True)
    result = _result(model)
    payload = canonical_report_bytes(model)
    calls = []
    parse = html_renderer.parse_observation
    graph = html_renderer.architecture_report

    def decode(*args):
        calls.append("decode")
        return parse(*args)

    def project(*args):
        calls.append("graph")
        return graph(*args)

    monkeypatch.setattr(html_renderer, "parse_observation", decode)
    monkeypatch.setattr(html_renderer, "architecture_report", project)
    assert (
        len(
            html_renderer.render_architecture_pages(
                result, payload, repository="One target", architecture_href="architecture.json"
            )
        )
        == 2
    )
    assert calls == ["decode", "graph"]


def test_pair_rejects_mismatched_projection(tmp_path):
    model = _sample(tmp_path)
    result = _result(model)
    projection = result.architecture_projection
    assert projection is not None
    result = replace(
        result,
        architecture_projection=replace(
            projection, source=replace(projection.source, source_digest="0" * 64)
        ),
    )
    with pytest.raises(ValueError, match="matching authenticated Core projection"):
        html_renderer.render_architecture_pages(
            result,
            canonical_report_bytes(model),
            repository="One",
            architecture_href="architecture.json",
        )


@pytest.mark.parametrize("payload", [b"{}", b"not JSON"])
def test_pair_keeps_strict_decode(tmp_path, payload):
    model = _sample(tmp_path)
    result = _result(model)
    with pytest.raises((ValueError, KeyError, TypeError)):
        html_renderer.render_architecture_pages(
            result, payload, repository="One", architecture_href="architecture.json"
        )


def test_cli_main_render_failure_publishes_no_html(tmp_path, monkeypatch, capsys):
    root = _prepare_repo(tmp_path, {})
    output = tmp_path / "published" / "architecture.json"

    def fail_main(*_args, **_kwargs):
        raise ValueError("injected main render failure")

    monkeypatch.setattr(html_renderer, "_atlas_document", fail_main)
    assert main(["report", "--root", str(root), "--output", str(output), "--json"]) == 2
    assert "injected main render failure" in capsys.readouterr().out
    assert output.is_file()
    assert not tuple(output.parent.glob("*.html"))


@pytest.mark.parametrize("open_map", [True, False])
def test_paired_page_carrier_preserves_original_render_type_rule(tmp_path, open_map):
    from test_analyzer import _component

    from archkeel.ir.trace import trace_valid_violations

    original = json.loads((Path(__file__).parents[1] / "architecture-contract.json").read_text())
    rule = next(rule for rule in original["rules"] if rule["id"] == "RENDER-TYPES-DECLARED")
    package = tmp_path / "archkeel/render"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    annotation = (
        "dict[str, bytes]"
        if open_map
        else html_renderer.render_architecture_pages.__annotations__["return"]
    )
    (package / "html.py").write_text(
        "def render_architecture_details() -> dict[str, bytes]: pass\n"
        f"def render_architecture_pages() -> {annotation}: pass\n"
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component(
                        "render",
                        packages=["archkeel.render"],
                        public=[
                            "archkeel.render.html:render_architecture_details",
                            "archkeel.render.html:render_architecture_pages",
                        ],
                    )
                ],
                "rules": [rule],
            }
        )
    )
    result = observe(
        tmp_path,
        roots=(".",),
        namespace="archkeel",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert len(violations) == int(open_map)
    assert not [
        record
        for record in result.observation.records("unknowns") or ()
        if record.kind == "boundary_type_position"
    ]
    assert not result.diagnostics
