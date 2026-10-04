# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Adversarial integration guards for exact module ownership."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_exact_module_ownership import (
    _component,
    _contract,
    _observe_tree,
    _report,
    _rule,
    _target_contract,
)

from archkeel.check.validation import (
    closed_world_diagnostics,
    target_component_edges,
)
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    canonical_report_bytes,
    decode_canonical_model,
    parse_contract,
    parse_observation,
    result_bytes,
    result_payload,
)
from archkeel.ir.decisions import open_decisions, rule_assessments
from archkeel.ir.graph_codec import parse_report
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.levels import inside_levels
from archkeel.ir.model import Observation, RuleAssessment, RunResult
from archkeel.ir.trace import trace_valid_violations


def _assessment(observation: Observation) -> RuleAssessment:
    return next(
        item for item in rule_assessments(observation, undecided_by_rule={}) if item.id == "RULE"
    )


def test_ambiguous_exact_rule_root_does_not_escape_complete_assignment(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [
            _component("registry", [], exact_modules=["sample.registry"]),
            _component("recursive", ["sample.registry"]),
        ],
        [_rule("complete_assignment", source="sample.registry")],
    )
    result = _observe_tree(
        tmp_path,
        {"sample/registry/__init__.py": "VALUE = 1\n"},
        contract,
    )

    assert result.observation is not None, result.diagnostics
    assert result.observation.coverage.status == "PASS"
    assert any(
        item.data.get("qualified_name") == "sample.registry"
        for item in result.observation.records("modules") or ()
    )
    assessment = _assessment(result.observation)
    assert (assessment.status, assessment.evaluation_proven) != ("PASS", True)


def test_source_free_exact_target_remains_a_leaf_beside_recursive_sibling(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [
            _component("registry", [], exact_modules=["sample.core"]),
            _component("api", ["sample.core.api"]),
        ]
    )
    _, _, payload, actual = _report(tmp_path, contract, source_paths=[])

    assert actual == set()
    report = parse_report(payload)
    intents = {item.label: item for item in report.target.component_intents}
    names = {item.id: item.qualified_name for item in report.observed.entities}
    assigned = {
        item.component_id: {names[identity] for identity in item.module_ids}
        for item in report.memberships
    }
    assert intents["registry"].exact_modules == ("sample.core",)
    assert intents["registry"].packages == ()
    assert intents["api"].packages == ("sample.core.api",)
    assert intents["api"].parent_id is None and not assigned[intents["registry"].component_id]


def test_exact_initializer_public_boundary_is_not_omitted_from_type_checks(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [
            _component(
                "registry",
                [],
                exact_modules=["sample.core"],
                public=["sample.core:run"],
            )
        ],
        [_rule("boundary_types", source="sample.core")],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/core/__init__.py": (
                "__all__ = ['run']\ndef run(value: dict) -> str:\n    return str(value)\n"
            )
        },
        contract,
    )

    assert result.observation is not None, result.diagnostics
    (finding,) = trace_valid_violations(result.observation)
    assert finding.kind == "boundary_types"
    assert finding.data.get("module") == "sample.core"
    assert finding.data.get("qualified_name") == "sample.core.run"


def test_exact_ownership_covers_modules_across_multiple_roots_and_keeps_missing_unknown(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [_component("registry", [], exact_modules=["sample.core", "sample.cli"])],
        [_rule("no_component_cycles", level="module", components=["registry"])],
    )
    files = {
        "first/sample/core/__init__.py": "VALUE = 1\n",
        "second/sample/cli/__init__.py": "VALUE = 2\n",
    }
    full = _observe_tree(
        tmp_path / "full",
        files,
        contract,
        roots=("first/sample", "second/sample"),
    )

    assert full.observation is not None, full.diagnostics
    assert {
        item.data.get("qualified_name") for item in full.observation.records("modules") or ()
    } == {"sample.core", "sample.cli"}
    assert (
        _assessment(full.observation).status,
        _assessment(full.observation).evaluation_proven,
    ) == (
        "PASS",
        True,
    )

    partial = _observe_tree(
        tmp_path / "partial",
        files,
        contract,
        roots=("first/sample/core",),
    )
    assert partial.observation is not None, partial.diagnostics
    assert (
        _assessment(partial.observation).status,
        _assessment(partial.observation).evaluation_proven,
    ) == (
        "UNKNOWN",
        False,
    )


def test_parse_error_in_an_exact_initializer_preserves_unknown_scope(tmp_path: Path) -> None:
    contract = _contract(
        [_component("registry", [], exact_modules=["sample.core"])],
        [_rule("no_component_cycles", level="module", components=["registry"])],
    )
    result = _observe_tree(
        tmp_path,
        {"sample/core/__init__.py": "if True\n    pass\n"},
        contract,
    )

    assert result.exit_code == 2
    assert any(diagnostic.kind == "parse_error" for diagnostic in result.diagnostics)
    assert result.observation is not None
    assert result.observation.coverage.status == "FAIL"
    assert (
        _assessment(result.observation).status,
        _assessment(result.observation).evaluation_proven,
    ) == ("UNKNOWN", False)


def test_missing_parent_exact_module_blocks_inside_complete_requires(tmp_path: Path) -> None:
    parent = _contract(
        [
            _component(
                "parent",
                [],
                exact_modules=["sample.core", "sample.missing"],
                inside="inside.json",
            )
        ]
    )
    child = _contract(
        [_component("child", [], exact_modules=["sample.core"])],
        [_rule("complete_requires")],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/core/__init__.py": "VALUE = 1\n",
            "inside.json": json.dumps(child),
        },
        parent,
    )

    assert result.observation is not None, result.diagnostics
    assessment = next(
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "parent:RULE"
    )
    assert (assessment.status, assessment.evaluation_proven) == ("UNKNOWN", False)


def test_missing_exact_parent_module_blocks_mixed_package_child_completeness(
    tmp_path: Path,
) -> None:
    parent = _contract(
        [
            _component(
                "parent",
                ["sample.core"],
                exact_modules=["sample.missing"],
                inside="inside.json",
            )
        ]
    )
    child = _contract(
        [_component("child", ["sample.core"])],
        [_rule("complete_requires")],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/core/__init__.py": "VALUE = 1\n",
            "inside.json": json.dumps(child),
        },
        parent,
    )

    assert result.observation is not None, result.diagnostics
    assessment = next(
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "parent:RULE"
    )
    assert (assessment.status, assessment.evaluation_proven) == ("UNKNOWN", False)


def test_exact_only_components_keep_pair_decision_obligations(tmp_path: Path) -> None:
    components = [_component(label, [], exact_modules=[f"sample.{label}"]) for label in ("a", "b")]
    result = _observe_tree(
        tmp_path,
        {
            "sample/a.py": "import sample.b\n",
            "sample/b.py": "VALUE = 1\n",
        },
        _contract(components),
    )

    assert result.observation is not None, result.diagnostics
    assert {
        (item.source, item.target, item.observed) for item in open_decisions(result.observation)
    } == {("a", "b", True), ("b", "a", False)}


def test_diff_keeps_ambiguous_exact_initializer_visible(tmp_path: Path) -> None:
    contract = _contract(
        [_component(label, [], exact_modules=["sample.core"]) for label in ("one", "two")]
    )
    _, _, payload, _ = _report(
        tmp_path,
        contract,
        extra_files={"sample/core/__init__.py": "VALUE = 1\n"},
    )

    assert payload is not None
    report = parse_report(payload)
    names = {item.id: item.qualified_name for item in report.observed.entities}
    assigned = {
        item.component_id: {names[identity] for identity in item.module_ids}
        for item in report.memberships
    }
    module = next(
        item
        for item in report.observed.entities
        if item.kind == "module" and item.qualified_name == "sample.core"
    )
    assert module.file_path == "sample/core/__init__.py"
    assert not any("sample.core" in values for values in assigned.values())


def test_partly_present_exact_component_reports_only_missing_leaf(tmp_path: Path) -> None:
    contract = _contract([_component("one", [], exact_modules=["sample.core", "sample.missing"])])
    _, _, payload, _ = _report(tmp_path, contract)

    assert payload is not None
    report = parse_report(payload)
    intents = {item.label: item for item in report.target.component_intents}
    names = {item.id: item.qualified_name for item in report.observed.entities}
    assigned = {
        item.component_id: {names[identity] for identity in item.module_ids}
        for item in report.memberships
    }
    assert intents["one"].exact_modules == ("sample.core", "sample.missing")
    assert "sample.core" in assigned[intents["one"].component_id]
    assert "sample.missing" not in names.values()


def test_partly_present_mixed_component_is_not_wholly_absent(tmp_path: Path) -> None:
    contract = _contract([_component("one", ["sample.missing"], exact_modules=["sample.core"])])
    _, _, payload, actual = _report(tmp_path, contract)

    assert payload is not None
    assert "sample.core" in actual
    report = parse_report(payload)
    intents = {item.label: item for item in report.target.component_intents}
    names = {item.id: item.qualified_name for item in report.observed.entities}
    assigned = {
        item.component_id: {names[identity] for identity in item.module_ids}
        for item in report.memberships
    }
    assert intents["one"].packages == ("sample.missing",)
    assert intents["one"].exact_modules == ("sample.core",)
    assert "sample.core" in assigned[intents["one"].component_id]


def test_package_and_exact_scope_counts_keep_selector_kind(tmp_path: Path) -> None:
    contract = _contract([_component("both", ["sample.core"], exact_modules=["sample.core"])])
    result = _observe_tree(
        tmp_path,
        {
            "sample/core/__init__.py": "VALUE = 1\n",
            "sample/core/api.py": "VALUE = 2\n",
        },
        contract,
    )

    assert result.observation is not None, result.diagnostics
    scope = next(
        item
        for item in result.observation.records("scope_observations") or ()
        if item.kind == "declared_component_scope_observation"
    )
    counts = {
        (item.get("kind"), item.get("scope"), item.get("observed_module_count"))
        for item in scope.data.get("scope_module_counts", ())
    }
    assert counts == {("package", "sample.core", 2), ("exact_module", "sample.core", 1)}


def _saved_open_decisions(result, contract: dict[str, object]):
    assert result.observation is not None, result.diagnostics
    saved_observation = parse_observation(
        decode_canonical_model(json.loads(canonical_report_bytes(result.observation)))
    )
    decisions = open_decisions(saved_observation)
    diagnostics = closed_world_diagnostics(parse_contract(contract), saved_observation)
    open_subjects = {item.subject for item in diagnostics if item.code == "decision.open"}
    assert open_subjects == {f"{item.source} -> {item.target}" for item in decisions}
    return decisions, open_subjects


def test_declared_package_pair_rule_closes_mixed_exact_pair_after_save(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [
            _component("alpha", ["sample.alpha"], exact_modules=["sample.registry"]),
            _component(
                "beta",
                ["sample.beta"],
                exact_modules=["sample.jobs", "sample.worker"],
            ),
        ],
        [
            _rule(
                "allowed_dependency",
                id="ALLOW-ALPHA-BETA-PACKAGES",
                source="sample.alpha",
                target="sample.beta",
            )
        ],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/alpha/api.py": "import sample.beta.api\n",
            "sample/beta/api.py": "VALUE = 1\n",
            "sample/registry.py": "import sample.jobs\n",
            "sample/jobs.py": "VALUE = 2\n",
            "sample/worker.py": "VALUE = 3\n",
        },
        contract,
    )

    decisions, open_subjects = _saved_open_decisions(result, contract)
    assert open_subjects == {"beta -> alpha"}
    assert target_component_edges(parse_contract(contract)) == {("alpha", "beta")}
    assert all((item.source, item.target) != ("alpha", "beta") for item in decisions)


def test_whole_pair_forbid_closes_mixed_exact_pair_and_rejects_member_import(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [
            _component("alpha", ["sample.alpha"], exact_modules=["sample.registry"]),
            _component("beta", ["sample.beta"], exact_modules=["sample.worker"]),
        ],
        [
            _rule(
                "forbidden_dependency",
                id="FORBID-ALPHA-BETA",
                source="sample.alpha",
                target="sample.beta",
                include_type_checking=True,
            )
        ],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/alpha/api.py": "VALUE = 1\n",
            "sample/beta/api.py": "VALUE = 2\n",
            "sample/registry.py": "import sample.worker\n",
            "sample/worker.py": "VALUE = 3\n",
        },
        contract,
    )

    decisions, open_subjects = _saved_open_decisions(result, contract)
    assert open_subjects == {"beta -> alpha"}
    assert target_component_edges(parse_contract(contract)) == set()
    assert all((item.source, item.target) != ("alpha", "beta") for item in decisions)
    (finding,) = trace_valid_violations(result.observation)
    assert finding.kind == "forbidden_dependency"
    assert finding.data.get("source_module") == "sample.registry"
    assert finding.data.get("target_module") == "sample.worker"


def test_one_declared_pair_rule_covers_multi_package_endpoints(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [
            _component(
                "alpha",
                ["sample.alpha", "sample.alpha_aux"],
                exact_modules=["sample.registry"],
            ),
            _component(
                "beta",
                ["sample.beta", "sample.beta_aux"],
                exact_modules=["sample.worker"],
            ),
        ],
        [
            _rule(
                "allowed_dependency",
                id="ALLOW-ALPHA-BETA-MULTI-PACKAGE",
                source="sample.alpha",
                target="sample.beta",
            )
        ],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/alpha/api.py": "VALUE = 1\n",
            "sample/alpha_aux/api.py": "VALUE = 2\n",
            "sample/beta/api.py": "VALUE = 3\n",
            "sample/beta_aux/api.py": "VALUE = 4\n",
            "sample/registry.py": "import sample.worker\n",
            "sample/worker.py": "VALUE = 5\n",
        },
        contract,
    )

    _, open_subjects = _saved_open_decisions(result, contract)
    assert open_subjects == {"beta -> alpha"}
    assert target_component_edges(parse_contract(contract)) == {("alpha", "beta")}


def test_single_exact_member_rule_does_not_close_multi_exact_pair_after_save(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [
            _component("alpha", [], exact_modules=["sample.alpha", "sample.alpha_aux"]),
            _component("beta", [], exact_modules=["sample.beta", "sample.beta_aux"]),
        ],
        [
            _rule(
                "forbidden_dependency",
                id="FORBID-ALPHA-BETA-MEMBERS",
                source="sample.alpha",
                target="sample.beta",
                include_type_checking=True,
            )
        ],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/alpha.py": "import sample.beta\n",
            "sample/alpha_aux.py": "VALUE = 1\n",
            "sample/beta.py": "VALUE = 2\n",
            "sample/beta_aux.py": "VALUE = 3\n",
        },
        contract,
    )

    decisions, open_subjects = _saved_open_decisions(result, contract)
    decision = next(item for item in decisions if (item.source, item.target) == ("alpha", "beta"))
    assert "alpha -> beta" in open_subjects
    assert decision.observed is True
    assert decision.import_sites == 1
    assert decision.source_packages == ()
    assert decision.target_packages == ()
    assert decision.source_exact_modules == ("sample.alpha", "sample.alpha_aux")
    assert decision.target_exact_modules == ("sample.beta", "sample.beta_aux")
    assert decision.source_package is None
    assert decision.target_package is None
    assert decision.options_unavailable_reason == "exact_ownership_suggestions_not_generated"
    payload = result_payload(RunResult("init", 0, open_decisions=(decision,)))["open_decisions"][0]
    assert payload["options"] == {}
    assert payload["options_unavailable_reason"] == "exact_ownership_suggestions_not_generated"


def test_rules_for_every_exact_member_still_do_not_close_exact_only_pair(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [
            _component("alpha", [], exact_modules=["sample.alpha", "sample.alpha_aux"]),
            _component("beta", [], exact_modules=["sample.beta", "sample.beta_aux"]),
        ],
        [
            _rule(
                "forbidden_dependency",
                id=f"FORBID-{source}-{target}".replace(".", "-"),
                source=source,
                target=target,
                include_type_checking=True,
            )
            for source in ("sample.alpha", "sample.alpha_aux")
            for target in ("sample.beta", "sample.beta_aux")
        ],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/alpha.py": "import sample.beta\n",
            "sample/alpha_aux.py": "VALUE = 1\n",
            "sample/beta.py": "VALUE = 2\n",
            "sample/beta_aux.py": "VALUE = 3\n",
        },
        contract,
    )

    _, open_subjects = _saved_open_decisions(result, contract)
    assert open_subjects == {"alpha -> beta", "beta -> alpha"}
    assert target_component_edges(parse_contract(contract)) == set()


def test_submodule_forbid_is_partial_for_mixed_exact_pair(tmp_path: Path) -> None:
    contract = _contract(
        [
            _component("alpha", ["sample.alpha"], exact_modules=["sample.registry"]),
            _component("beta", ["sample.beta"], exact_modules=["sample.worker"]),
        ],
        [
            _rule(
                "forbidden_dependency",
                id="FORBID-ALPHA-SUBMODULE-BETA",
                source="sample.alpha.sub",
                target="sample.beta",
                include_type_checking=True,
            )
        ],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/alpha/sub.py": "import sample.beta.api\n",
            "sample/alpha/api.py": "VALUE = 1\n",
            "sample/beta/api.py": "VALUE = 2\n",
            "sample/registry.py": "import sample.worker\n",
            "sample/worker.py": "VALUE = 3\n",
        },
        contract,
    )

    decisions, open_subjects = _saved_open_decisions(result, contract)
    assert "alpha -> beta" in open_subjects
    decision = next(item for item in decisions if (item.source, item.target) == ("alpha", "beta"))
    assert decision.source_packages == ("sample.alpha",)
    assert decision.target_packages == ("sample.beta",)
    assert decision.options_unavailable_reason == "exact_ownership_suggestions_not_generated"
    payload = result_payload(RunResult("init", 0, open_decisions=(decision,)))["open_decisions"][0]
    assert payload["options"] == {}
    assert payload["options_unavailable_reason"] == "exact_ownership_suggestions_not_generated"
    assert target_component_edges(parse_contract(contract)) == set()
    findings = trace_valid_violations(result.observation)
    assert any(
        item.kind == "forbidden_dependency" and item.data.get("source_module") == "sample.alpha.sub"
        for item in findings
    )


def test_target_symbol_forbid_is_partial_for_mixed_exact_pair(tmp_path: Path) -> None:
    contract = _contract(
        [
            _component("alpha", ["sample.alpha"], exact_modules=["sample.registry"]),
            _component("beta", ["sample.beta"], exact_modules=["sample.worker"]),
        ],
        [
            _rule(
                "forbidden_dependency",
                id="FORBID-ALPHA-BETA-HIDDEN",
                source="sample.alpha",
                target="sample.beta",
                target_symbol="hidden",
                include_type_checking=True,
            )
        ],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/alpha/api.py": "from sample.beta.api import hidden\n",
            "sample/beta/api.py": "def hidden(): pass\ndef visible(): pass\n",
            "sample/registry.py": "import sample.worker\n",
            "sample/worker.py": "VALUE = 1\n",
        },
        contract,
    )

    _, open_subjects = _saved_open_decisions(result, contract)
    assert "alpha -> beta" in open_subjects
    assert target_component_edges(parse_contract(contract)) == set()
    assert any(
        item.kind == "forbidden_dependency" and item.data.get("source_module") == "sample.alpha.api"
        for item in trace_valid_violations(result.observation)
    )


def test_conflicting_whole_pair_rules_never_report_pass(tmp_path: Path) -> None:
    contract = _contract(
        [
            _component("alpha", ["sample.alpha"], exact_modules=["sample.registry"]),
            _component("beta", ["sample.beta"], exact_modules=["sample.worker"]),
        ],
        [
            _rule(
                "allowed_dependency",
                id="ALLOW-ALPHA-BETA-CONFLICT",
                source="sample.alpha",
                target="sample.beta",
            ),
            _rule(
                "forbidden_dependency",
                id="FORBID-ALPHA-BETA-CONFLICT",
                source="sample.alpha",
                target="sample.beta",
                include_type_checking=True,
            ),
        ],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/alpha/api.py": "VALUE = 1\n",
            "sample/beta/api.py": "VALUE = 2\n",
            "sample/registry.py": "import sample.worker\n",
            "sample/worker.py": "VALUE = 3\n",
        },
        contract,
    )

    diagnostics = closed_world_diagnostics(parse_contract(contract), result.observation)
    assert any(item.code == "decision.conflict" for item in diagnostics)
    assert target_component_edges(parse_contract(contract)) == {("alpha", "beta")}


def test_legacy_package_only_open_decision_payload_is_unchanged(tmp_path: Path) -> None:
    contract = _contract(
        [
            _component("alpha", ["sample.alpha"]),
            _component("beta", ["sample.beta"]),
        ]
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/alpha/api.py": "import sample.beta.api\n",
            "sample/beta/api.py": "VALUE = 1\n",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics

    legacy = open_decisions(
        result.observation,
        (("alpha", ("sample.alpha",)), ("beta", ("sample.beta",))),
    )
    explicit_empty = open_decisions(
        result.observation,
        (("alpha", ("sample.alpha",), ()), ("beta", ("sample.beta",), ())),
    )
    run_legacy = RunResult("init", 0, open_decisions=legacy)
    run_explicit_empty = RunResult("init", 0, open_decisions=explicit_empty)

    assert open_decisions(result.observation) == legacy == explicit_empty
    assert result_bytes(run_legacy) == result_bytes(run_explicit_empty)
    payload = result_payload(run_legacy)["open_decisions"][0]
    assert set(payload) == {
        "source",
        "target",
        "observed",
        "import_sites",
        "source_package",
        "target_package",
        "options",
    }
    assert payload["options"].keys() == {"allowed_dependency", "forbidden_dependency"}


def _inventory_report(
    tmp_path: Path,
    contract: dict[str, object],
    module_file: str,
    source: str,
    *,
    extra_files: dict[str, str] | None = None,
    declare_at_root: bool = True,
):
    if declare_at_root:
        contract["declarations"] = {
            "modules": [{"path": module_file, "responsibility": "Inventory this source file."}]
        }
    result, _, payload, actual = _report(
        tmp_path,
        contract,
        extra_files={**(extra_files or {}), module_file: source},
    )
    assert payload is not None, result.diagnostics
    return payload, actual


def _scanned_inventory_observation(tmp_path: Path) -> tuple[Observation, Observation]:
    root = tmp_path / "repo"
    result = observe(
        root,
        roots=("sample",),
        namespace="sample",
        contract="architecture-contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert result.observation is not None, result.diagnostics
    saved = parse_observation(
        decode_canonical_model(json.loads(canonical_report_bytes(result.observation)))
    )
    return result.observation, saved


@pytest.mark.parametrize(
    ("ownership", "module_file", "module_name"),
    [
        pytest.param("exact_exact", "sample/core/__init__.py", "sample.core", id="exact-init"),
        pytest.param("exact_exact", "sample/core/api.py", "sample.core.api", id="exact-module"),
        pytest.param("exact_prefix", "sample/core/__init__.py", "sample.core", id="prefix-init"),
        pytest.param("exact_prefix", "sample/core/api.py", "sample.core.api", id="prefix-module"),
    ],
)
def test_inventory_does_not_hide_same_level_component_ambiguity(
    tmp_path: Path,
    ownership: str,
    module_file: str,
    module_name: str,
) -> None:
    exact = _component("exact", [], exact_modules=[module_name])
    if ownership == "exact_exact":
        components = [exact, _component("other", [], exact_modules=[module_name])]
    else:
        components = [exact, _component("recursive", ["sample.core"])]
    contract = _contract(components)

    payload, actual = _inventory_report(tmp_path, contract, module_file, "VALUE = 11\n")
    root_observation, saved_observation = _scanned_inventory_observation(tmp_path)
    assert owner_of(module_name, component_owners(root_observation)) is None
    assert owner_of(module_name, component_owners(saved_observation)) is None
    assert module_name in actual

    report = parse_report(payload)
    intents = {item.label: item for item in report.target.component_intents}
    names = {item.id: item.qualified_name for item in report.observed.entities}
    assigned = {
        item.component_id: {names[identity] for identity in item.module_ids}
        for item in report.memberships
    }
    module = next(
        item
        for item in report.observed.entities
        if item.kind == "module" and item.qualified_name == module_name
    )
    assert module.file_path == module_file
    assert any(
        item.path == module_file
        for inventory in report.target.module_inventories
        for item in inventory.modules
    )
    assert intents["exact"].exact_modules == (module_name,)
    if ownership == "exact_exact":
        assert intents["other"].exact_modules == (module_name,)
    else:
        assert intents["recursive"].packages == ("sample.core",)
    assert not any(module_name in values for values in assigned.values())


def test_nested_sibling_conflict_stays_visible_with_unique_ancestor_owner(
    tmp_path: Path,
) -> None:
    outer = _target_contract()
    inner = _contract(
        [
            _component("exact", [], exact_modules=["sample.core"]),
            _component("recursive", ["sample.core"]),
        ]
    )
    inner["declarations"] = {
        "modules": [
            {"path": "sample/core/__init__.py", "responsibility": "Inventory the initializer."}
        ]
    }
    outer["components"][0]["inside"] = "contracts/inside.json"
    payload, actual = _inventory_report(
        tmp_path,
        outer,
        "sample/core/__init__.py",
        "VALUE = 1\n",
        extra_files={"contracts/inside.json": json.dumps(inner)},
        declare_at_root=False,
    )
    root_observation, saved_observation = _scanned_inventory_observation(tmp_path)
    root_components = component_owners(saved_observation)
    local = inside_levels(saved_observation)[0]
    local_components = tuple(
        (item.label, item.packages, item.exact_modules) for item in local.components
    )

    assert owner_of("sample.core", root_components) == "app"
    assert owner_of("sample.core", local_components) is None
    assert owner_of("sample.core", component_owners(root_observation)) == "app"
    assert "sample.core" in actual
    report = parse_report(payload)
    intents = {item.label: item for item in report.target.component_intents}
    names = {item.id: item.qualified_name for item in report.observed.entities}
    assigned = {
        item.component_id: {names[identity] for identity in item.module_ids}
        for item in report.memberships
    }
    assert intents["exact"].exact_modules == ("sample.core",)
    assert intents["recursive"].packages == ("sample.core",)
    assert "sample.core" in assigned[intents["app"].component_id]
    assert not assigned[intents["exact"].component_id]
    assert "sample.core" not in assigned[intents["recursive"].component_id]
    assert any(
        item.path == "sample/core/__init__.py"
        for inventory in report.target.module_inventories
        for item in inventory.modules
    )


def test_valid_exact_child_under_package_ancestor_is_not_ambiguous(
    tmp_path: Path,
) -> None:
    outer = _target_contract()
    inner = _contract([_component("registry", [], exact_modules=["sample.core"])])
    inner["declarations"] = {
        "modules": [
            {"path": "sample/core/__init__.py", "responsibility": "Inventory the initializer."}
        ]
    }
    outer["components"][0]["inside"] = "contracts/inside.json"
    payload, actual = _inventory_report(
        tmp_path,
        outer,
        "sample/core/__init__.py",
        "VALUE = 1\n",
        extra_files={"contracts/inside.json": json.dumps(inner)},
        declare_at_root=False,
    )
    root_observation, saved_observation = _scanned_inventory_observation(tmp_path)
    local = inside_levels(saved_observation)[0]
    local_components = tuple(
        (item.label, item.packages, item.exact_modules) for item in local.components
    )

    assert owner_of("sample.core", component_owners(root_observation)) == "app"
    assert owner_of("sample.core", local_components) == "registry"
    assert owner_of("sample.core", component_owners(saved_observation)) == "app"
    assert "sample.core" in actual
    report = parse_report(payload)
    intents = {item.label: item for item in report.target.component_intents}
    names = {item.id: item.qualified_name for item in report.observed.entities}
    assigned = {
        item.component_id: {names[identity] for identity in item.module_ids}
        for item in report.memberships
    }
    assert intents["registry"].exact_modules == ("sample.core",)
    assert "sample.core" in assigned[intents["registry"].component_id]


def test_same_component_package_and_exact_overlap_is_one_inventory_owner(
    tmp_path: Path,
) -> None:
    contract = _contract([_component("registry", ["sample.core"], exact_modules=["sample.core"])])
    payload, actual = _inventory_report(
        tmp_path,
        contract,
        "sample/core/__init__.py",
        "VALUE = 1\n",
    )
    root_observation, saved_observation = _scanned_inventory_observation(tmp_path)

    assert owner_of("sample.core", component_owners(root_observation)) == "registry"
    assert owner_of("sample.core", component_owners(saved_observation)) == "registry"
    assert "sample.core" in actual
    report = parse_report(payload)
    intents = {item.label: item for item in report.target.component_intents}
    names = {item.id: item.qualified_name for item in report.observed.entities}
    assigned = {
        item.component_id: {names[identity] for identity in item.module_ids}
        for item in report.memberships
    }
    assert intents["registry"].exact_modules == ("sample.core",)
    assert intents["registry"].packages == ("sample.core",)
    assert "sample.core" in assigned[intents["registry"].component_id]
