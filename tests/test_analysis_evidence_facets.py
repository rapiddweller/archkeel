# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Known evidence facets recognize tags; their readers confer no proof authority."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir import facts, model
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/analysis-evidence-facets.md"
VOCAB = {
    "SourceEvidenceKind": {
        "RESOLUTION_GAP": "source_resolution_gap",
        "MISSING_CROSS_PACKAGE_ANNOTATION": "missing_cross_package_annotation",
        "PRIVATE_ATTRIBUTE_ACCESS_LIMIT": "private_attribute_access_limit"
    },
    "SourceResolutionDimension": {
        "IMPORTS": "imports",
        "SIGNATURE": "signature"
    },
    "CoreAnalysisEvidenceKind": {
        "BOUNDARY_TYPE_POSITION": "boundary_type_position",
        "BOUNDARY_TYPE_ROUTE": "boundary_type_route",
        "BOUNDARY_TYPE_LIMIT": "boundary_type_limit",
        "BOUNDARY_TYPE_ALLOWANCE": "boundary_type_allowance",
        "TYPE_IGNORE_ALLOWANCE": "type_ignore_allowance",
        "RULE_OWNERSHIP_BLOCKER": "rule_ownership_blocker",
        "INSIDE_SOURCE_DOMAIN_INCOMPLETE": "inside_source_domain_incomplete",
        "COMPONENT_SCOPE_ASSIGNMENT_INCOMPLETE": "component_scope_assignment_incomplete",
        "RULE_UNSUPPORTED_BY_PROFILE": "rule-unsupported-by-profile",
        "MEMBER_INVENTORY_PROOF": "member_inventory_proof",
        "INSIDE_CONTRACT_INCOMPLETE": "inside_contract_incomplete",
        "DYNAMIC_CALL_LIMIT": "dynamic_call_limit",
        "CONTEXT_ALIAS_LIMIT": "context_alias_limit"
    }
}
PORTS = [
    (facts, "SourceEvidenceKind", "parse_source_evidence_kind"),
    (facts, "SourceResolutionDimension", "parse_source_resolution_dimension"),
    (model, "CoreAnalysisEvidenceKind", "parse_core_analysis_evidence_kind"),
]
GUARDS = {"EVIDENCE-FACET-" + fn + "-CONTROL" for _, _, fn in PORTS}


def _port(module, name, fn):
    assert hasattr(module, name), "evidence facets need their actual semantic owner"
    return getattr(module, name), getattr(module, fn)


def test_source_and_core_evidence_have_distinct_owners_and_open_record_envelopes():
    for module, name, fn in PORTS:
        kind, reader = _port(module, name, fn)
        assert {item.name: item.value for item in kind} == VOCAB[name]
        assert kind.__module__ == module.__name__
    assert get_type_hints(facts.Record)["kind"] is str
    assert type(facts.SOURCE_RESOLUTION_GAP_KIND) is str
    assert facts.SOURCE_RESOLUTION_GAP_KIND == facts.SourceEvidenceKind.RESOLUTION_GAP.value


@pytest.mark.parametrize("module,name,fn", PORTS)
def test_all_supported_legacy_and_nominal_values_keep_wire_text(module, name, fn):
    kind, reader = _port(module, name, fn)
    for item in kind:
        assert reader(item.value) is item and reader(item) is item
        record = facts.Record("r", facts.EvidenceClass.UNKNOWN, "source", item.value,
                              "observed", (), (), (), (), (), facts.RecordData())
        assert json.loads(json.dumps(asdict(record)))["kind"] == item.value
        assert record.evidence_class is facts.EvidenceClass.UNKNOWN


@pytest.mark.parametrize("module,name,fn", PORTS)
@pytest.mark.parametrize("value", ["vendor.future", "", "class", None, False, 3, [], {}])
def test_unknown_or_other_facet_data_remains_unrecognized(module, name, fn, value):
    _, reader = _port(module, name, fn)
    assert reader(value) is None


def _repository(tmp_path, mutation=None):
    for args in PORTS:
        _port(*args)
    target = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    target.pop("$schema", None)
    target["components"] = [dict(
        id="facets", label="facets", role="component", packages=["archkeel"],
        responsibilities=["Own shared source and Core semantic facets without changing proof authority."],
        forbidden_responsibilities=[], provenance=[DOC], public=["archkeel"],
    )]
    entities = [dict(item) for item in target["declarations"]["uml"]["entities"]
                if item["id"].startswith("EVIDENCE-FACET-")
                or item["id"] in {"archkeel.ir.facts", "IR-DEPENDENCY-model"}]
    assert len(entities) == 8
    for item in entities:
        if item["kind"] == "module":
            item.pop("parent_id", None)
    target["declarations"] = {"uml": {"schema_version": "1.0.0", "entities": entities, "relationships": [], "scopes": []}}
    target["rules"] = [item for item in target["rules"] if item["id"] in GUARDS]
    assert {item["id"] for item in target["rules"]} == GUARDS
    names = {module.__name__.rsplit(".", 1)[-1]: set() for module, _, _ in PORTS}
    for module, name, fn in PORTS:
        names[module.__name__.rsplit(".", 1)[-1]].update({name, fn})
    files = {
        "archkeel/__init__.py": "", "archkeel/ir/__init__.py": "",
        "contract.json": json.dumps(target), DOC: (ROOT / DOC).read_text(),
        "docs/architecture/language-adapter-target.md": "Actual source values.\n",
        "docs/architecture/dependency-selector-target.md": "Actual Core model owner.\n",
    }
    for module, members in names.items():
        files[f"archkeel/ir/{module}.py"] = (
            "from __future__ import annotations\nfrom enum import StrEnum\n"
            + _source_members(f"src/archkeel/ir/{module}.py", members)
        )
    if mutation:
        path, old, new = mutation
        assert files[path].count(old) == 1
        files[path] = files[path].replace(old, new)
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _valid(observation):
    comparison = architecture_report(observation).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    rows = {row.id: row for row in rule_assessments(observation, undecided_by_rule={}) if row.id in GUARDS}
    assert set(rows) == GUARDS
    assert all(row.status == "PASS" and row.evaluation_proven for row in rows.values())
    assert not trace_valid_violations(observation)


def test_native_actual_scalar_facets_match_independently_authored_ports(tmp_path):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))


@pytest.mark.parametrize("module,name,fn", PORTS)
@pytest.mark.parametrize("position", ["input", "return"])
def test_native_actual_facet_port_weakening_fails_fixed_intent(tmp_path, module, name, fn, position):
    old, new = ("value: JsonValue | RawJson", "value: object") if position == "input" else (f") -> {name} | None:", ") -> object:")
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir" / (module.__name__.rsplit(".", 1)[-1] + ".py")
    original = source.read_text()
    begin = original.index("def " + fn + "(")
    assert original[begin:].count(old) >= 1
    source.write_text(original[:begin] + original[begin:].replace(old, new, 1))
    before = (root / "contract.json").read_bytes()
    assert trace_valid_violations(_model(root, config))
    assert (root / "contract.json").read_bytes() == before


@pytest.mark.parametrize("module,name,fn", PORTS)
def test_native_actual_facet_decoder_raw_regression_fails_fixed_guard(tmp_path, module, name, fn):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir" / (module.__name__.rsplit(".", 1)[-1] + ".py")
    original = source.read_text()
    old = f"return {name}(value)"
    assert original.count(old) == 1
    member, raw = next(iter(VOCAB[name].items()))
    new = f"if value == {raw!r}:\n            return {name}.{member}\n        return {name}(value)"
    source.write_text(original.replace(old, new, 1))
    before = (root / "contract.json").read_bytes()
    assert any("EVIDENCE-FACET-" + fn + "-CONTROL" in row.rule_ids for row in trace_valid_violations(_model(root, config)))
    assert (root / "contract.json").read_bytes() == before
