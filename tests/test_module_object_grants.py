# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exact module-object permissions use native import evidence and one public inventory."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model
from test_dependency_api_target import _source_members

from archkeel.check.declarations import project_rule_declaration
from archkeel.check.evaluation.rules import _interface_verdicts, profile_failures
from archkeel.check.ports import ScanConfig
from archkeel.check.validation.references import reference_diagnostics
from archkeel.ir.codec import contract_bytes, parse_contract, parse_record
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import module_references
from archkeel.ir.profiles import DART, TYPESCRIPT
from archkeel.ir.renames import renamed_contract
from archkeel.ir.trace import trace_valid_violations
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.widening import contract_widening_changes

ROOT = Path(__file__).parents[1]
GRANT = {"source_module": "demo.registry", "target_module": "demo.plugins"}


def _contract(grants=(GRANT,), *, version="3.6.0"):
    return {
        "schema_version": version,
        "components": [
            {
                "id": name,
                "label": name,
                "role": "component",
                "packages": [f"demo.{name}"] if name in {"plugins", "registry"} else [],
                "exact_modules": [f"demo.{name}"]
                if name == "consumer"
                else ["demo"]
                if name == "root"
                else [],
                "public": ["demo.plugins:Allowed"] if name == "plugins" else [],
                "requires": [],
                "responsibilities": [f"Own synthetic {name}."],
                "forbidden_responsibilities": [],
                "provenance": ["target.md"],
            }
            for name in ("plugins", "registry", "consumer", "root")
        ],
        "rules": [
            {
                "id": "INTERFACE",
                "kind": "interface_boundary",
                "rationale": "Let the registry discover packages without publishing internals.",
                "provenance": ["target.md"],
                "decided_by": "architect",
                **({"module_object_grants": list(grants)} if grants is not None else {}),
            }
        ],
    }


def _repository(tmp_path, *, registry="", consumer="", child="", contract=None):
    contract = _contract() if contract is None else contract
    files = {
        "demo/__init__.py": "",
        "demo/plugins/__init__.py": ("class Allowed: pass\n"
                                    "class Secret: pass\nclass _Private: pass\n"),
        "demo/plugins/extra.py": "class Other: pass\n",
        "demo/plugins/forwarder.py": 'from . import Secret\n__all__ = ["Secret"]\n',
        "demo/registry/__init__.py": registry,
        "demo/consumer.py": consumer,
        "contract.json": json.dumps(contract),
        "target.md": "Synthetic plugins, composition registry, consumer and root owners.\n",
    }
    if child:
        files["demo/registry/child.py"] = child
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("demo",), "demo", "contract.json", "0" * 64)


def _interface(model, rule_id="INTERFACE"):
    return next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == rule_id)


@pytest.mark.parametrize(
    "statement",
    [
        "import demo.plugins",
        "import demo.plugins as plugins",
        "from .. import plugins",
        "from demo import plugins as discovered",
    ],
)
def test_native_exact_registry_can_obtain_the_package_object(tmp_path, statement):
    root, config = _repository(tmp_path, registry=statement + "\n")
    model = _model(root, config)
    rule = _interface(model)
    assert rule.status == "PASS" and rule.evaluation_proven, rule
    imported = next(
        row for row in model.records("imports") if row.data.get("source_module") == "demo.registry"
    )
    assert imported.data.get("target_module") == "demo.plugins"
    assert imported.data.get("symbol") is None and imported.data.get("symbols_known") is True
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    "caller,statement",
    [
        ("consumer", "import demo.plugins as plugins"),
        ("child", "import demo.plugins as plugins"),
        ("registry", "import demo.plugins.extra as plugins"),
        ("registry", "from demo.plugins import Secret"),
        ("consumer", "from demo.plugins import Secret"),
        ("registry", "from demo.plugins import _Private"),
        ("registry", "from demo.plugins import *"),
        ("consumer", "from demo.plugins.forwarder import Secret"),
        ("registry", "from demo.plugins.forwarder import Secret"),
    ],
)
def test_native_grants_do_not_publish_names_or_prefixes(tmp_path, caller, statement):
    root, config = _repository(tmp_path, **{caller: statement + "\n"})
    model = _model(root, config)
    rule = _interface(model)
    assert rule.status == "FAIL" and rule.evaluation_proven, rule
    assert any(row.rule_ids == ("INTERFACE",) for row in trace_valid_violations(model))


def test_native_valid_named_public_import_still_passes(tmp_path):
    root, config = _repository(
        tmp_path,
        registry="from demo.plugins import Allowed\n",
        consumer="from demo.plugins import Allowed as Public\n",
    )
    model = _model(root, config)
    assert _interface(model).status == "PASS"
    assert not trace_valid_violations(model)


@pytest.mark.parametrize("other_kind", ["forbidden_dependency", "complete_requires"])
def test_native_grant_does_not_override_other_dependency_policies(tmp_path, other_kind):
    contract = _contract()
    contract["rules"].append(
        {
            "id": "OTHER",
            "kind": other_kind,
            "rationale": "Keep the independent dependency restriction.",
            "provenance": ["target.md"],
            "decided_by": "architect",
            **(
                {"source": "demo.registry", "target": "demo.plugins", "include_type_checking": True}
                if other_kind == "forbidden_dependency"
                else {}
            ),
        }
    )
    root, config = _repository(
        tmp_path, registry="import demo.plugins as plugins\n", contract=contract
    )
    model = _model(root, config)
    assert any(row.rule_ids == ("OTHER",) for row in trace_valid_violations(model))


def test_unknown_names_are_not_converted_to_a_module_object_permission(tmp_path):
    root, config = _repository(tmp_path, registry="import demo.plugins as plugins\n")
    model = _model(root, config)
    item = next(
        row for row in model.records("imports") if row.data.get("source_module") == "demo.registry"
    )
    # A separate evaluator control removes knowledge from actual native evidence.
    # It never supplies the evidence chain for the native acceptance assertions.
    raw = {"id": item.id, "data": dict(item.data.entries)}
    raw["data"].update(
        symbols_known=False, reexport=False, symbol_visibility="unknown", under_type_checking=False
    )
    rows = list(_interface_verdicts([raw], parse_contract(_contract()), {}, frozenset()))
    assert len(rows) == 1 and rows[0][-1] == "undecided"


def test_grants_roundtrip_through_wire_and_projected_rule_records():
    contract = parse_contract(_contract())
    rule = contract.rules[0]
    assert rule.module_object_grants[0].source_module == "demo.registry"
    assert rule.module_object_grants[0].target_module == "demo.plugins"
    assert parse_contract(json.loads(contract_bytes(contract))) == contract
    schema = json.loads((ROOT / "schema/architecture-contract-3.6.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(json.loads(contract_bytes(contract))))
    record = project_rule_declaration(rule)
    assert record["data"]["module_object_grants"] == [GRANT]
    decoded = parse_record(record)
    assert dict(decoded.data.get("module_object_grants")[0].entries) == GRANT


def test_absence_preserves_historical_bytes_and_empty_grants_remain_authored():
    before = _contract(None, version="3.5.0")
    old = parse_contract(before)
    assert "module_object_grants" not in json.loads(contract_bytes(old))["rules"][0]
    empty = parse_contract(_contract(()))
    assert empty.rules[0].module_object_grants == ()
    assert json.loads(contract_bytes(empty))["rules"][0]["module_object_grants"] == []


@pytest.mark.parametrize("version", ["2.1.0", "2.3.0", "3.0.0", "3.3.0", "3.4.0", "3.5.0"])
def test_older_versions_reject_even_empty_module_object_grants(version):
    with pytest.raises(ValueError, match="module.object.grants.*3.6"):
        parse_contract(_contract((), version=version))


@pytest.mark.parametrize(
    "grants",
    [
        None,
        "demo.plugins",
        [None],
        [{}],
        [{"source_module": "demo.registry"}],
        [{**GRANT, "extra": "no"}],
        [{**GRANT, "source_module": "demo.registry:*"}],
        [{**GRANT, "target_module": "demo.plugins.*"}],
        [{**GRANT, "target_module": ".demo.plugins"}],
        [{**GRANT, "source_module": ""}],
        [GRANT, GRANT],
    ],
)
def test_strict_grant_grammar_matches_the_36_schema(grants):
    raw = _contract()
    raw["rules"][0]["module_object_grants"] = grants
    with pytest.raises(ValueError):
        parse_contract(raw)
    schema = json.loads((ROOT / "schema/architecture-contract-3.6.schema.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(raw))


def test_grant_module_references_are_held_nested_pointers_and_renamed():
    contract = parse_contract(_contract())
    references = {row.pointer: (row.value, row.held) for row in module_references(contract)}
    prefix = "/rules/0/module_object_grants/0/"
    assert references[prefix + "source_module"] == ("demo.registry", True)
    assert references[prefix + "target_module"] == ("demo.plugins", True)
    changed = renamed_contract(contract, {"demo": "newdemo"})
    grant = changed.rules[0].module_object_grants[0]
    assert (grant.source_module, grant.target_module) == ("newdemo.registry", "newdemo.plugins")


def test_grant_addition_is_widening_and_removal_is_narrowing():
    absent = parse_contract(_contract(None))
    granted = parse_contract(_contract())
    assert any(
        row.field == "module_object_grants" for row in contract_widening_changes(absent, granted)
    )
    assert not contract_widening_changes(granted, absent)
    different = parse_contract(_contract([{**GRANT, "source_module": "demo.consumer"}]))
    assert any(
        row.field == "module_object_grants" for row in contract_widening_changes(granted, different)
    )


@pytest.mark.parametrize("profile", [DART, TYPESCRIPT])
def test_profiles_without_proven_module_objects_reject_grant_semantics(profile):
    errors = profile_failures(parse_contract(_contract()), profile, ())
    assert errors and any("module" in row["title"].lower() for row in errors)


def test_grant_namespace_diagnostics_retain_endpoint_pointers(tmp_path):
    raw = _contract(
        [{**GRANT, "source_module": "elsewhere.registry", "target_module": "outside.plugins"}]
    )
    root, config = _repository(tmp_path, contract=raw)
    diagnostics = reference_diagnostics(root, config, parse_contract(raw))
    assert {
        (row.pointer, row.subject) for row in diagnostics if row.code == "reference.namespace"
    } == {
        ("/rules/0/module_object_grants/0/source_module", "elsewhere.registry"),
        ("/rules/0/module_object_grants/0/target_module", "outside.plugins"),
    }


def test_native_mounted_grants_remain_local_to_their_rule(tmp_path):
    inside = _contract()
    raw = {
        "schema_version": "3.6.0",
        "components": [
            {
                "id": "all",
                "label": "all",
                "role": "component",
                "packages": ["demo"],
                "inside": "inside.json",
                "responsibilities": ["Own the mounted synthetic application."],
                "forbidden_responsibilities": [],
                "provenance": ["target.md"],
            }
        ],
        "rules": [],
    }
    root, config = _repository(
        tmp_path,
        registry="import demo.plugins as plugins\n",
        consumer="import demo.plugins as plugins\n",
        contract=raw,
    )
    (root / "inside.json").write_text(json.dumps(inside))
    model = _model(root, config)
    assert _interface(model, "all:INTERFACE").status == "FAIL"
    violations = [
        row for row in trace_valid_violations(model) if row.rule_ids == ("all:INTERFACE",)
    ]
    assert len(violations) == 1
    assert violations[0].data.get("source_module") == "demo.consumer"


@pytest.mark.parametrize("widen", [False, True])
def test_native_grant_types_follow_fixed_independent_own_intent(tmp_path, widen):
    source = "from dataclasses import dataclass\nfrom typing import Literal\n\n" + _source_members(
        "src/archkeel/ir/model.py", {"ModuleObjectGrant", "InterfaceBoundaryRule"}
    )
    contract = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    contract.pop("$schema", None)
    contract["rules"] = []
    contract["declarations"]["uml"]["entities"] = [
        item
        for item in contract["declarations"]["uml"]["entities"]
        if item["id"].startswith("IR-MODULE-OBJECT-") or item["id"] == "IR-DEPENDENCY-model"
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    if widen:
        original = "module_object_grants: tuple[ModuleObjectGrant, ...] | None"
        assert original in source
        source = source.replace(original, "module_object_grants: str | None", 1)
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/ir/__init__.py": "",
            "archkeel/ir/model.py": source,
            "contract.json": json.dumps(contract),
            "docs/architecture/module-object-grants.md": "Independent module-object intent.",
        },
    )
    before = (root / "contract.json").read_bytes()
    model = _model(root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64))
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.assessments
    assert comparison.status == ("FAIL" if widen else "PASS")
    assert (root / "contract.json").read_bytes() == before
    protected = next(
        item
        for item in contract["declarations"]["uml"]["entities"]
        if item["qualified_name"] == "archkeel.ir.model.InterfaceBoundaryRule.module_object_grants"
    )
    assert any(
        row.subject_id == protected["id"]
        and row.aspect == "annotation"
        and row.status == ("FAIL" if widen else "PASS")
        for row in comparison.assessments
    )
    assert bool(trace_valid_violations(model)) is widen


def test_encoding_rejects_a_typed_grant_under_an_older_schema_version():
    contract = parse_contract(_contract())
    with pytest.raises(ValueError, match="module.object.grants.*3.6"):
        contract_bytes(replace(contract, schema_version="3.5.0"))


@pytest.mark.parametrize("grants", [None, ()])
def test_native_absent_or_empty_grants_do_not_infer_discovery_permissions(tmp_path, grants):
    root, config = _repository(
        tmp_path, registry="import demo.plugins as plugins\n", contract=_contract(grants)
    )
    model = _model(root, config)
    assert _interface(model).status == "FAIL"
    assert any(row.rule_ids == ("INTERFACE",) for row in trace_valid_violations(model))
