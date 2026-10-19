# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Violations and uncertainty consume the same effective dependency capability."""

import copy
import json
from dataclasses import replace

import pytest
from test_analyzer import _component
from test_source_evaluation import _typescript_facts

from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.check.evaluation.rules import (
    _interface_verdicts,
    _interface_violations,
    _requires_import_verdicts,
    profile_failures,
    requires_violations,
    symbol_limits,
)
from archkeel.ir.codec import contract_digest, parse_contract
from archkeel.ir.facts_codec import decode_response, encode_response, raw_record
from archkeel.ir.model import InsideContractMount
from archkeel.ir.profiles import TYPESCRIPT
from archkeel.ir.protocol import CollectionResponse

SOURCE = "project.src.app_x2e_ts"
TARGET = "project.src.store_x2e_ts"
DESCRIPTORS = {
    "correct": ("Command", True),
    "wrong": ("Other", True),
    "wildcard": ("*", False),
    "missing": (None, False),
}


def _facts(profile, descriptor):
    payload = json.loads(
        encode_response(CollectionResponse(_typescript_facts(inner_uml=profile != "legacy")))
    )
    facts = payload["facts"]
    if profile == "current":
        facts["capabilities"]["resolution_features"].append("script-globals-v1")
    target = copy.deepcopy(facts["files"][0])
    target.update(id="FILE-store", module=TARGET, rel_path="src/store.ts", evidence_id="E-store")
    facts["files"].append(target)
    facts["inputs"].append({"path": "src/store.ts", "digest": "e" * 64, "role": "selected"})
    evidence = copy.deepcopy(facts["evidence"][0])
    evidence.update(id="E-store", file="src/store.ts")
    facts["evidence"].append(evidence)
    facts["coverage"].update(
        selected_files=["src/app.ts", "src/store.ts"], files_read=2, files_parsed=2
    )
    record = facts["sections"][0]["records"][0]
    symbol, known = DESCRIPTORS[descriptor]
    record["subjects"] = [SOURCE, TARGET]
    record["data"].update(
        target_module=TARGET,
        target_package="project.src",
        symbol=symbol,
        symbols_known=known,
        reexport_chain=[f"{TARGET}.{symbol}"] if symbol is not None else [],
    )
    facts["imports"] = [
        {
            "kind": "local",
            "import_id": record["id"],
            "module": TARGET,
            "file": "src/store.ts",
            "runtime_file": "src/store.ts",
            "declaration_file": None,
        }
    ]
    return decode_response(json.dumps(payload).encode()).facts


def _contract(kind, port):
    caller = _component("caller", packages=[SOURCE])
    target = _component("core", packages=[TARGET])
    selector = TARGET + ":Command" if port == "exact" else TARGET
    if kind == "complete_requires":
        caller["requires"] = [
            {
                "component": "core",
                "through": [] if port == "empty" else [selector],
                "rationale": "Use this port.",
            }
        ]
    else:
        target["public"] = [] if port == "empty" else [selector]
    return parse_contract(
        {
            "schema_version": "2.2.0",
            "components": [caller, target],
            "rules": [
                {
                    "id": "RULE",
                    "kind": kind,
                    "rationale": "Keep the same evidence scope.",
                    "provenance": ["architecture.md"],
                    "decided_by": "architect",
                }
            ],
        }
    )


def _expected(kind, port, descriptor, supported):
    if port == "exact":
        if not supported:
            return "unsupported"
        return {"correct": "PASS", "wrong": "FAIL", "wildcard": "UNKNOWN", "missing": "UNKNOWN"}[
            descriptor
        ]
    return "FAIL" if kind == "interface_boundary" and port == "empty" else "PASS"


@pytest.mark.parametrize("supported", [False, True])
@pytest.mark.parametrize("kind", ["complete_requires", "interface_boundary"])
@pytest.mark.parametrize("port", ["exact", "module", "empty"])
@pytest.mark.parametrize("descriptor", DESCRIPTORS)
def test_dependency_channels_share_selection(supported, kind, port, descriptor):
    contract = _contract(kind, port)
    imports = [raw_record(_facts("current", descriptor).sections[0].records[0])]
    expected = _expected(kind, port, descriptor, supported)
    if kind == "complete_requires":
        selected = list(
            _requires_import_verdicts(
                imports, contract, contract.rules[0], dependency_symbols=supported
            )
        )
        violations = requires_violations(imports, contract, dependency_symbols=supported)
    else:
        selected = list(
            _interface_verdicts(imports, contract, {}, frozenset(), dependency_symbols=supported)
        )
        violations = _interface_violations(
            imports, contract, {}, frozenset(), dependency_symbols=supported
        )
    limits = symbol_limits(imports, contract, {}, dependency_symbols=supported)
    assert len(selected) == (expected != "unsupported")
    assert bool(violations) is (expected == "FAIL")
    assert bool(limits) is (expected == "UNKNOWN")
    if selected:
        assert selected[0][-1] == expected
    failures = profile_failures(contract, replace(TYPESCRIPT, dependency_symbols=supported), ())
    assert bool(failures) is (expected == "unsupported")
    assert all(row["evidence_class"] == "UNKNOWN" for row in failures)


@pytest.mark.parametrize("profile", ["legacy", "inner", "current"])
@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("kind", ["complete_requires", "interface_boundary"])
@pytest.mark.parametrize("port", ["exact", "module", "empty"])
@pytest.mark.parametrize("descriptor", DESCRIPTORS)
def test_effective_typescript_profile_reaches_root_and_mounted_channels(
    profile, mounted, kind, port, descriptor
):
    facts = _facts(profile, descriptor)
    before = encode_response(CollectionResponse(facts))
    contract = _contract(kind, port)
    mounts = ()
    if mounted:
        parent = _component("app", packages=["project.src"])
        parent["inside"] = "inside.json"
        outer = parse_contract({"schema_version": "2.2.0", "components": [parent], "rules": []})
        digest = contract_digest(contract)
        mounts = (
            InsideContractMount(
                outer.components[0],
                outer,
                "",
                "app",
                "/components/0/inside",
                "inside.json",
                "inside.json",
                contract,
                digest,
                digest,
            ),
        )
        contract = outer
    scan = evaluate_source(
        facts, contract, roots=("src",), namespace="project", inside_contracts=mounts
    )
    rule_id = "RULE"
    violations = [row for row in scan.violations if rule_id in row["rule_ids"]]
    limits = [
        row
        for row in scan.unknowns
        if row["kind"] in {"requires_symbol_limit", "interface_symbol_limit"}
        and rule_id in row["rule_ids"]
    ]
    failures = [row for row in scan.unknowns if row["kind"] == "rule-unsupported-by-profile"]
    expected = _expected(kind, port, descriptor, profile == "current")
    assert bool(violations) is (expected == "FAIL")
    assert bool(limits) is (expected == "UNKNOWN")
    assert bool(failures) is (expected == "unsupported")
    assert all(row["evidence_class"] == "UNKNOWN" for row in failures)
    assert scan.coverage["rules"] == ("FAIL" if expected == "unsupported" else "PASS")
    assert encode_response(CollectionResponse(facts)) == before
    if limits:
        assert len(limits) == 1
        assert limits[0]["fact_ids"] == ["IMP-1"]
        assert limits[0]["data"]["undecided"] == 1
    if violations:
        assert len(violations) == 1
        assert violations[0]["fact_ids"] == ["IMP-1"]
