# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from dataclasses import replace
from typing import Literal

import pytest
from test_delta import _evidence, _model, _record, _violation

from archkeel.check.validation import _observed_result
from archkeel.check.validation.observation import _responsibility_diagnostics
from archkeel.ir.codec import contract_bytes, contract_digest, parse_observation
from archkeel.ir.codec_inside import load_inside_contract_tree
from archkeel.ir.model import ArchitectureContract, ContractComponent


def _contract(
    responsibilities: tuple[str, ...],
    *,
    decided_by: Literal["architect", "agent"] | None = "architect",
) -> ArchitectureContract:
    return ArchitectureContract(
        "2.1.0",
        (
            ContractComponent(
                id="COMP-CORE",
                label="core",
                role="component",
                packages=("sample.core",),
                responsibilities=responsibilities,
                forbidden_responsibilities=(),
                provenance=("docs/architecture/sample.md",),
                decided_by=decided_by,
            ),
        ),
        (),
    )


@pytest.mark.parametrize(
    "responsibilities",
    [("TODO",), ("tbd",), ("Placeholder",), ("  ToDo  ",), ("TODO:",), ("TODO", "TBD")],
)
def test_architect_placeholder_only_responsibilities_name_component_and_location(
    responsibilities: tuple[str, ...],
) -> None:
    diagnostics = _responsibility_diagnostics(_contract(responsibilities), None, "contract.json")

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert (diagnostic.code, diagnostic.subject, diagnostic.pointer, diagnostic.contract_path) == (
        "responsibility.missing",
        "core",
        "/components/0/responsibilities",
        "contract.json",
    )
    assert "placeholder" in diagnostic.unknown_claim
    assert "architect" in diagnostic.remedy


@pytest.mark.parametrize(
    "responsibilities",
    [
        ("Own stable domain data.",),
        ("TODO", "Own stable domain data."),
        ("Handle TODO items.",),
        ("TODO item processing.",),
        ("TBD is a supported status.",),
        ("Placeholder resolution.",),
        ("Replace placeholder values.",),
        ("TODOs",),
        ("placeholder_value",),
    ],
)
def test_substantive_responsibilities_may_mention_placeholder_words(
    responsibilities: tuple[str, ...],
) -> None:
    assert _responsibility_diagnostics(_contract(responsibilities), None, "contract.json") == []


@pytest.mark.parametrize("decided_by", ["agent", None])
@pytest.mark.parametrize("responsibilities", [(), ("TODO",), ("TODO", "TBD")])
def test_draft_responsibilities_remain_accepted(
    decided_by: Literal["architect", "agent"] | None, responsibilities: tuple[str, ...]
) -> None:
    contract = _contract(responsibilities, decided_by=decided_by)
    assert _responsibility_diagnostics(contract, None, "contract.json") == []


def test_empty_architect_responsibilities_keep_existing_diagnostic() -> None:
    [diagnostic] = _responsibility_diagnostics(_contract(()), None, "contract.json")
    assert diagnostic.code == "responsibility.missing"
    assert diagnostic.unknown_claim == (
        "The architect-decided component has no responsibility declaration."
    )


def test_mounted_placeholder_responsibilities_name_inside_contract() -> None:
    contract = _contract(("Own domain logic.",))
    contract = replace(
        contract,
        components=(replace(contract.components[0], inside="contracts/core.json"),),
    )
    nested = _contract(("TODO", "placeholder"))
    nested = replace(
        nested,
        components=(
            replace(
                nested.components[0], id="COMP-API", label="api", packages=("sample.core.api",)
            ),
        ),
    )
    tree = load_inside_contract_tree(
        "contract.json",
        contract,
        contract_digest(contract),
        "contract.json",
        lambda path: (contract_bytes(nested), path),
    )
    assert tree.issues == ()

    [diagnostic] = _responsibility_diagnostics(contract, tree, "contract.json")

    assert (diagnostic.code, diagnostic.subject, diagnostic.pointer, diagnostic.contract_path) == (
        "responsibility.missing",
        "api in contracts/core.json",
        "/components/0/responsibilities",
        "contracts/core.json",
    )


@pytest.mark.parametrize("verdict", ["PASS", "FAIL", "UNKNOWN"])
def test_placeholder_diagnostic_rejects_validation_without_changing_rule_verdict(
    verdict: str,
) -> None:
    raw = _model(git_head="a" * 40)
    if verdict == "FAIL":
        raw["violations"] = [_violation("VIO-boundary", "EVD-import")]
        raw["violations"][0]["fact_ids"] = ["FACT-import"]
        rule = _record(
            "DEP-TASKS-NO-CLIENTS",
            kind="forbidden_dependency",
            evidence_class="DECLARED_RULE",
            data={"source": "datamimic_ee.tasks", "target": "datamimic_ee.clients"},
        )
        rule["provenance"] = ["docs/architecture/sample.md"]
        raw["declarations"] = [rule]
        raw["imports"] = [
            _record(
                "FACT-import",
                kind="import",
                evidence_id="EVD-import",
                data={
                    "source_package": "datamimic_ee.tasks",
                    "target_package": "datamimic_ee.clients",
                },
            )
        ]
        raw["evidence"] = [_evidence("EVD-import", 1)]
    elif verdict == "UNKNOWN":
        raw["unknowns"] = [_record("UNKN-boundary", kind="rule_unknown", evidence_class="UNKNOWN")]
    observation = parse_observation(raw)
    before = _observed_result(observation, [])
    diagnostics = _responsibility_diagnostics(_contract(("TODO",)), None, "contract.json")

    result = _observed_result(observation, diagnostics)

    assert before.exit_code == 0
    assert result.exit_code == 2
    assert before.declared_rules == result.declared_rules == verdict
    assert result.observation_complete == before.observation_complete == "PASS"
    assert result.measurements == before.measurements
