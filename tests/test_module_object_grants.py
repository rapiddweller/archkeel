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
from test_contract_model import _maximal_contract
from test_uml_evaluation import _model

from archkeel.check.declarations import project_rule_declaration
from archkeel.check.evaluation.rules import profile_failures
from archkeel.check.ports import ScanConfig
from archkeel.check.validation.references import reference_diagnostics
from archkeel.ir.codec import contract_bytes, parse_contract, parse_record
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import module_references
from archkeel.ir.profiles import DART, TYPESCRIPT, Profile
from archkeel.ir.renames import renamed_contract
from archkeel.ir.trace import trace_valid_violations
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
        "demo/plugins/__init__.py": (
            "class Allowed: pass\nclass Secret: pass\nclass _Private: pass\n"
        ),
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
        [{**GRANT, "source_module": "demo.registry\n"}],
        [{**GRANT, "target_module": "demo.plugins\n"}],
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


def test_encoding_rejects_a_typed_grant_under_an_older_schema_version():
    contract = parse_contract(_contract())
    with pytest.raises(ValueError, match="module.object.grants.*3.6"):
        contract_bytes(replace(contract, schema_version="3.5.0"))


@pytest.mark.parametrize("version", ["3.0.0", "3.1.0", "3.2.0", "3.3.0", "3.4.0", "3.5.0"])
def test_36_preserves_prior_feature_grammars(version):
    raw = json.loads(contract_bytes(parse_contract(_maximal_contract(version))))
    raw["schema_version"] = "3.6.0"
    parsed = parse_contract(raw)
    assert parse_contract(json.loads(contract_bytes(parsed))) == parsed
    schema = json.loads((ROOT / "schema/architecture-contract-3.6.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(raw))


def test_profile_capability_preserves_existing_positional_constructor_arguments():
    profile = Profile("custom-analyzer", ".py", frozenset(), True, False, crate_edges_only=False)
    assert profile.dependency_symbols is True
    assert profile.complete_api_crossings is False
    assert profile.module_object_imports is False
