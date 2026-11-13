# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Runnable demos must prove independent intent through the production report."""

import json
import re
from dataclasses import replace

import pytest

from archkeel.ir.architecture_graph import EntityKind
from archkeel.ir.graph_codec import parse_report
from fixtures.architecture_demo import CATALOG, replay

# The shared vocabulary includes mixins and Rust macros, but these source-backed demos are
# Python-only.
_PYTHON_DEMO_ENTITY_KINDS = frozenset(EntityKind) - {EntityKind.MIXIN, EntityKind.MACRO}


def _demo_report(output):
    main = output.with_suffix(".report.html")
    payload = re.search(
        r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>', main.read_text(encoding="utf-8"), re.S
    )
    assert payload
    atlas = json.loads(payload.group(1))["atlas"]
    component = next(item for item in atlas["components"] if item["label"] == "demo")
    assert component["id"]
    sidecar = main.with_name(atlas["detail_page"])
    payload = re.search(
        r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>', sidecar.read_text(encoding="utf-8"), re.S
    )
    assert payload
    data = json.loads(payload.group(1))
    assert data["navigation"]["main_href"] == main.name
    return parse_report(
        {
            key: value
            for key, value in data.items()
            if key not in {"initial_scope", "initial_view", "navigation", "boundary_permissions"}
        }
    )


@pytest.mark.parametrize("variant,language", [("uml-typescript", "typescript")])
def test_language_uml_demo_keeps_declared_target_separate_from_observation(
    tmp_path, capsys, variant, language
):
    output = tmp_path / "architecture.json"
    assert replay(variant, output) == 0
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["declared_rules"] == "UNKNOWN"
    report = _demo_report(output)
    assert {e.language for e in report.target.entities if e.kind != "component"} == {language}
    assert {e.kind for e in report.target.entities} >= {
        "module",
        "class",
        "interface",
        "enum",
        "enum_literal",
        "attribute",
        "method",
        "function",
        "binding",
        "type_alias",
        "constant",
    }
    names = {entity.qualified_name: entity for entity in report.observed.entities}
    assert {
        "demo.src.core_x2e_ts.Port",
        "demo.src.core_x2e_ts.Base",
        "demo.src.core_x2e_ts.Client",
        "demo.src.core_x2e_ts.Client.run",
        "demo.src.core_x2e_ts.Client._token",
        "demo.src.core_x2e_ts.State.READY",
        "demo.src.core_x2e_ts.build.item",
    } <= names.keys()
    assert all(entity.language == "typescript" for entity in names.values())
    assert not (
        {entity.id for entity in report.observed.entities}
        & {entity.id for entity in report.target.entities if entity.kind != "component"}
    )
    endpoints = {entity.id: entity.qualified_name for entity in report.observed.entities}
    relationships = {
        (item.kind, endpoints[item.source_id], endpoints[item.target_id])
        for item in report.observed.relationships
        if item.target_id is not None
    }
    assert (
        "inherits",
        "demo.src.core_x2e_ts.Client",
        "demo.src.core_x2e_ts.Base",
    ) in relationships
    assert (
        "realizes",
        "demo.src.core_x2e_ts.Client",
        "demo.src.core_x2e_ts.Port",
    ) in relationships
    assert (
        "instance_of",
        "demo.src.core_x2e_ts.build.item",
        "demo.src.core_x2e_ts.Unit",
    ) in relationships
    assert report.comparison and not any(a.status == "FAIL" for a in report.comparison.assessments)
    assert all(
        any(
            a.subject_id == identity and a.aspect == "existence" and a.status == "PASS"
            for a in report.comparison.assessments
        )
        for identity in ("core-module", "app-module")
    )
    assert any(r.kind == "imports" for r in report.observed.relationships)


def test_typescript_uml_demo_rejects_omitted_standard_global_reference(
    tmp_path, capsys, monkeypatch
):
    from fixtures import architecture_demo

    variant = next(row for row in CATALOG if row.id == "uml-typescript")
    contract = json.loads((variant.fixture / "architecture-contract.json").read_text())
    relationships = contract["declarations"]["uml"]["relationships"]
    relationships.remove(next(row for row in relationships if row["id"] == "core-string-reference"))
    changed = replace(
        variant,
        files={**variant.files, "architecture-contract.json": json.dumps(contract)},
    )
    monkeypatch.setattr(architecture_demo, "CATALOG", (changed,))
    output = tmp_path / "architecture.json"
    assert replay("uml-typescript", output) == 2
    capsys.readouterr()
    report = _demo_report(output)
    names = {entity.id: entity.qualified_name for entity in report.observed.entities}
    reference = next(
        row
        for row in report.observed.relationships
        if row.kind == "references"
        and names[row.source_id] == "demo.src.core_x2e_ts"
        and names.get(row.target_id) == "String"
    )
    assert any(
        row.status == "FAIL" and row.aspect == "completeness" and reference.id in row.observed_ids
        for row in report.comparison.assessments
    )
