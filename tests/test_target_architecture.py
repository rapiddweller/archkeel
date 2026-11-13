# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise the compact target without weakening missing-evidence controls."""

import json
from pathlib import Path

import jsonschema
import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.model import requires_covers

ROOT = Path(__file__).parents[1]
CONTRACTS = [
    ROOT / "architecture-contract.json",
    *sorted((ROOT / "docs/architecture/contracts").glob("*.json")),
]


@pytest.mark.parametrize("path", CONTRACTS, ids=lambda path: path.stem)
def test_target_contract_schema_roundtrip_and_closed_owners(path):
    raw = json.loads(path.read_bytes())
    jsonschema.validate(raw, json.loads((ROOT / "schema" / Path(raw["$schema"]).name).read_bytes()))
    encoded = contract_bytes(parse_contract(raw))
    assert encoded == contract_bytes(parse_contract(json.loads(encoded)))
    assert {
        "complete_assignment",
        "complete_requires",
        "interface_boundary",
        "no_component_cycles",
    } <= {rule["kind"] for rule in raw["rules"]}


@pytest.mark.parametrize(
    "module,symbol,allowed",
    [
        ("archkeel.ir.codec", "decode_json", True),
        ("archkeel.ir.codec", "result_bytes", False),
        ("archkeel.ir.codec", None, False),
        ("archkeel.ir.command_view", "decode_json", False),
    ],
)
def test_report_reader_permission_is_symbol_specific(module, symbol, allowed):
    contract = parse_contract(json.loads(CONTRACTS[0].read_bytes()))
    api = next(component for component in contract.components if component.label == "api")
    assert requires_covers(api, "ir", module, symbol) is allowed


PORTS = (
    "archkeel.api.load_violations",
    "archkeel.analyzer.python.collect.PythonProviderCollector.collect",
    "archkeel.ir.renames.renamed_contract",
    "archkeel.check.report.run_report",
    "archkeel.check.report.run_saved_report",
    "archkeel.check.report.observe_repository",
    "archkeel.check.run.run_check",
    "archkeel.check.validation.run_validate",
    "archkeel.check.validation.invalid_result",
    "archkeel.check.onboarding.run_init",
    "archkeel.check.ports.Analyzer.__call__",
    "archkeel.check.ports.Host.__call__",
    "archkeel.check.observe.Observer.__call__",
    "archkeel.check.uml.observe_repository",
    "archkeel.render.html.render_architecture_html",
    "archkeel.render.html.render_architecture_details",
    "archkeel.render.html.render_check_html",
    "archkeel.render.atlas.atlas_payload",
    "archkeel.render.atlas.boundary_permissions_payload",
    "archkeel.render.summary.report_summary",
    "archkeel.render.summary.check_summary",
    "archkeel.render.summary.init_summary",
    "archkeel.render.terminal.print_result",
)


def _port_repository(tmp_path):
    # Keep authored signatures; isolate them from unrelated ownership and rule fixtures.
    entities = {
        entity["qualified_name"]: entity
        for path in CONTRACTS
        for entity in json.loads(path.read_bytes())
        .get("declarations", {})
        .get("uml", {})
        .get("entities", [])
    }
    selected = {entities[name]["id"]: entities[name] for name in PORTS}
    assert all(entity.get("signature") for entity in selected.values())
    by_id = {entity["id"]: entity for entity in entities.values()}
    for entity in list(selected.values()):
        parent = by_id.get(entity.get("parent_id"))
        while parent is not None:
            selected[parent["id"]] = parent
            parent = by_id.get(parent.get("parent_id"))
    selected.update(
        (entity["id"], entity)
        for entity in entities.values()
        if (entity.get("parent_id") == "COMPACT-OBSERVER" and entity["kind"] == "attribute")
        or entity["id"] in {"COMPACT-FILES-TO-WRITE", "COMPACT-FILES-TO-WRITE-ENTRIES"}
    )
    target = []
    files = {
        "archkeel/__init__.py": "",
        "docs/architecture/target/design.md": "Exact compact architecture ports.\n",
    }
    for entity in selected.values():
        row = dict(entity)
        if row["kind"] == "module":
            row.pop("parent_id", None)
            relative = Path(*row["qualified_name"].split("."))
            source = ROOT / "src" / relative.with_suffix(".py")
            if not source.is_file():
                relative /= "__init__.py"
                source = ROOT / "src" / relative
            else:
                relative = relative.with_suffix(".py")
            files[relative.as_posix()] = source.read_text()
            for parent in relative.parents:
                if str(parent) != ".":
                    files.setdefault((parent / "__init__.py").as_posix(), "")
        target.append(row)
    files["contract.json"] = json.dumps(
        {
            "schema_version": "2.3.0",
            "components": [],
            "rules": [],
            "declarations": {
                "uml": {
                    "schema_version": "1.1.0",
                    "entities": target,
                    "relationships": [],
                    "scopes": [],
                }
            },
        }
    )
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _port_comparison(root, config):
    from test_uml_evaluation import _model

    from archkeel.ir.report_graph import architecture_report

    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None
    return comparison
