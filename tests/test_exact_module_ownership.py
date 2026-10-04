# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exact module ownership is distinct from recursive package ownership."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_dart_profile import _component as _dart_component
from test_dart_profile import _observe as _observe_dart
from test_dart_profile import _rule as _dart_rule
from test_declared_module_targets import _contract as _target_contract
from test_declared_module_targets import _report

from archkeel.cli.observe import observe
from archkeel.ir.codec import contract_bytes, contract_digest, parse_contract
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.graph_codec import parse_report
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.renames import rename_candidates, renamed_contract
from archkeel.ir.trace import trace_valid_violations
from archkeel.ir.widening import Amendment, contract_widenings, verify_amendment

ROOT = Path(__file__).parents[1]
_PROVENANCE = ["docs/architecture/sample.md"]
_SCHEMA = json.loads((ROOT / "schema/architecture-contract.schema.json").read_bytes())


def _component(label: str, packages: list[str], **fields: object) -> dict[str, object]:
    return {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": packages,
        "responsibilities": [f"Own {label}."],
        "forbidden_responsibilities": [],
        "provenance": _PROVENANCE,
        **fields,
    }


def _contract(
    components: list[dict[str, object]],
    rules: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {"schema_version": "2.1.0", "components": components, "rules": rules or []}


def _rule(kind: str, **fields: object) -> dict[str, object]:
    return {
        "id": "RULE",
        "kind": kind,
        "rationale": "Probe exact ownership without changing the rule contract.",
        "provenance": _PROVENANCE,
        "decided_by": "architect",
        **fields,
    }


def _observe_tree(
    tmp_path: Path,
    files: dict[str, str],
    contract: dict[str, object],
    *,
    roots: tuple[str, ...] = ("sample",),
):
    for relative, source in {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/sample.md": "Decision.\n",
        "contract.json": json.dumps(contract),
        **files,
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return observe(
        tmp_path,
        roots=roots,
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )


def test_omitted_and_empty_exact_modules_keep_legacy_bytes_and_digest() -> None:
    legacy = _target_contract()
    omitted = parse_contract(legacy)
    empty = json.loads(json.dumps(legacy))
    empty["components"][0]["exact_modules"] = []

    assert contract_bytes(omitted) == contract_bytes(parse_contract(empty))
    assert contract_digest(omitted) == (
        "36f1e3a6d5ba01969c2005d53c9a9ccec765ef3f5500798fe813051a7777b129"
    )


def test_exact_only_component_roundtrips_and_matches_the_contract_schema() -> None:
    raw = _contract([_component("registry", [], exact_modules=["sample.registry"])])
    Draft202012Validator.check_schema(_SCHEMA)

    assert not list(Draft202012Validator(_SCHEMA).iter_errors(raw))
    parsed = parse_contract(raw)
    encoded = json.loads(contract_bytes(parsed))
    assert encoded["components"][0]["exact_modules"] == ["sample.registry"]
    assert encoded["components"][0]["packages"] == []
    assert parse_contract(encoded) == parsed
    assert parsed.component_for("sample.registry") == parsed.components[0]
    assert parsed.component_for("sample.registry.child") is None


@pytest.mark.parametrize(
    "exact_modules",
    [
        None,
        "sample.registry",
        [""],
        [" sample.registry"],
        ["sample.registry", "sample.registry"],
        [],
        ["sample/registry"],
        ["sample.registry:Registry"],
        ["sample.*"],
        [".sample.registry"],
        ["sample.registry."],
    ],
)
def test_exact_module_identifiers_fail_closed(exact_modules: object) -> None:
    raw = _contract([_component("registry", [], exact_modules=exact_modules)])

    assert list(Draft202012Validator(_SCHEMA).iter_errors(raw))
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_exact_and_prefix_claims_count_components_without_precedence() -> None:
    exact = _component("registry", [], exact_modules=["sample.registry"])
    prefix = _component("api", ["sample.registry"])
    assert parse_contract(_contract([exact, prefix])).component_for("sample.registry") is None

    exact_peer = _component("other", [], exact_modules=["sample.registry"])
    assert parse_contract(_contract([exact, exact_peer])).component_for("sample.registry") is None

    overlap_in_one_component = _component("registry", ["sample"], exact_modules=["sample.registry"])
    parsed = parse_contract(_contract([overlap_in_one_component]))
    assert parsed.component_for("sample.registry") == parsed.components[0]
    assert parsed.component_for("sample.registry.child") == parsed.components[0]


def test_two_level_exact_child_stays_on_initializer_and_target_actual_diff_agree(
    tmp_path: Path,
) -> None:
    contract = _target_contract()
    inner = _contract([_component("core", ["sample.core"], inside="contracts/two.json")])
    deep = _contract(
        [
            _component("registry", [], exact_modules=["sample.core"]),
            _component("api", ["sample.core.api"]),
            _component("private", ["sample.core.private"]),
            # `_report` supplies this subtree; claim it so complete_requires sees the whole fixture.
            _component("authoring", ["sample.core.authoring"]),
        ],
        [_rule("complete_requires")],
    )
    result, _, payload, _actual = _report(
        tmp_path,
        contract,
        extra_files={
            "contracts/inside.json": json.dumps(inner),
            "contracts/two.json": json.dumps(deep),
            "sample/core/__init__.py": "VALUE = 1\n",
            "sample/core/api.py": "VALUE = 2\n",
            "sample/core/private.py": "VALUE = 3\n",
        },
    )

    assert result.exit_code == 0, result.diagnostics
    assert result.declared_rules == "PASS"
    report = parse_report(payload)
    names = {item.id: item.qualified_name for item in report.observed.entities}
    intents = {item.label: item for item in report.target.component_intents}
    memberships = {
        item.component_id: {names[identity] for identity in item.module_ids}
        for item in report.memberships
    }
    assert memberships[intents["registry"].component_id] == {"sample.core"}
    assert memberships[intents["api"].component_id] == {"sample.core.api"}
    assert memberships[intents["private"].component_id] == {"sample.core.private"}
    assert memberships[intents["authoring"].component_id] == {
        "sample.core.authoring",
        "sample.core.authoring.scaffold",
    }
    assert intents["registry"].exact_modules == ("sample.core",)
    assert next(
        item
        for item in report.observed.entities
        if item.qualified_name == "sample.core" and item.kind == "module"
    ).file_path == ("sample/core/__init__.py")


def test_exact_parent_does_not_admit_child_claim_outside_exact_scope_at_second_mount(
    tmp_path: Path,
) -> None:
    contract = _target_contract()
    inner = _contract(
        [_component("registry", [], exact_modules=["sample.core"], inside="contracts/two.json")]
    )
    deep = _contract([_component("api", ["sample.core.api"])])
    result, _, _, _ = _report(
        tmp_path,
        contract,
        extra_files={
            "contracts/inside.json": json.dumps(inner),
            "contracts/two.json": json.dumps(deep),
        },
    )

    assert any("sample.core.api" in item.unknown_claim for item in result.diagnostics)


def test_owned_initializer_keeps_forbidden_import_and_component_cycle_findings(
    tmp_path: Path,
) -> None:
    contract = _contract(
        [
            _component("registry", [], exact_modules=["sample.core"]),
            _component("api", ["sample.core.api"]),
            _component("private", ["sample.core.private"]),
        ],
        [
            _rule(
                "no_component_cycles",
                id="CYCLE",
                level="module",
                components=["registry"],
            ),
            _rule(
                "forbidden_dependency",
                id="FORBIDDEN",
                source="sample.core",
                target="sample.core.private",
                include_type_checking=True,
            ),
        ],
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/core/__init__.py": (
                "import sample.core.api\nfrom sample.core.private import SECRET\n"
            ),
            "sample/core/api.py": "import sample.core\n",
            "sample/core/private.py": "SECRET = 1\n",
        },
        contract,
    )

    assert result.observation is not None, result.diagnostics
    findings = trace_valid_violations(result.observation)
    assert {item.kind for item in findings} >= {"module_cycle", "forbidden_dependency"}
    assert {rule_id for item in findings for rule_id in item.rule_ids} >= {"CYCLE", "FORBIDDEN"}


@pytest.mark.parametrize(
    "roots",
    [("sample",), ("sample/core/child",)],
    ids=["full-root-with-missing-exact-module", "partial-descendant-scan"],
)
def test_descendant_cannot_satisfy_missing_exact_initializer_or_partial_coverage(
    tmp_path: Path, roots: tuple[str, ...]
) -> None:
    contract = _contract(
        [
            _component("registry", [], exact_modules=["sample.core"]),
            _component("child", ["sample.core.child"]),
        ],
        [_rule("complete_requires")],
    )
    result = _observe_tree(
        tmp_path,
        {"sample/core/child/__init__.py": "VALUE = 1\n"},
        contract,
        roots=roots,
    )

    assert result.observation is not None, result.diagnostics
    assert result.observation.coverage.status == "PASS"
    assert result.observation.records("modules")
    assert result.exit_code == 0
    assert rule_assessments(result.observation, undecided_by_rule={})[0].status == "UNKNOWN"


def test_source_free_target_shows_exact_claim_without_inventing_a_file(tmp_path: Path) -> None:
    contract = _contract([_component("registry", [], exact_modules=["sample.core"])])
    _, _, payload, actual = _report(tmp_path, contract, source_paths=[])

    assert actual == set()
    report = parse_report(payload)
    registry = next(item for item in report.target.component_intents if item.label == "registry")
    assert registry.exact_modules == ("sample.core",) and registry.packages == ()
    assert not any(
        item.kind == "module" and item.presence == "defined" for item in report.observed.entities
    )
    assert not report.target.module_inventories


@pytest.mark.parametrize(
    ("before_exact", "after_exact", "transfer"),
    [
        (None, ["sample.tasks"], False),
        (["sample.tasks"], None, False),
        (["sample.tasks"], ["sample.jobs"], False),
        (["sample.tasks"], ["sample.tasks"], True),
    ],
    ids=["add", "remove", "replace", "transfer"],
)
def test_exact_module_changes_need_a_digest_bound_amendment(
    before_exact: list[str] | None,
    after_exact: list[str] | None,
    transfer: bool,
) -> None:
    before_component = _component("registry", ["sample.tasks"])
    after_component = _component("registry", ["sample.tasks"])
    if before_exact is not None:
        before_component["exact_modules"] = before_exact
    if after_exact is not None:
        after_component["exact_modules"] = after_exact
    before_components = [before_component]
    after_components = [after_component]
    if transfer:
        before_components = [_component("registry", [], exact_modules=["sample.tasks"])]
        after_components = [
            _component("other", [], exact_modules=["sample.tasks"]),
        ]
    before = parse_contract(_contract(before_components))
    after = parse_contract(_contract(after_components))
    findings = contract_widenings(before, after)
    assert findings

    amendment = Amendment(
        contract_digest(before),
        contract_digest(after),
        "architect",
        "Assign initializer ownership.",
    )
    assert verify_amendment(
        amendment, before_digest=contract_digest(before), after_digest=contract_digest(after)
    )
    assert not verify_amendment(
        amendment, before_digest=contract_digest(before), after_digest=contract_digest(before)
    )


def test_package_rename_rewrites_exact_reference_but_exact_move_is_not_a_subtree_rename() -> None:
    old = parse_contract(
        _contract([_component("registry", ["sample.tasks"], exact_modules=["sample.tasks"])])
    )
    new = parse_contract(
        _contract([_component("registry", ["sample.jobs"], exact_modules=["sample.jobs"])])
    )
    candidates = rename_candidates(old, new)
    assert candidates == ({"sample.tasks": "sample.jobs"},)
    assert renamed_contract(old, candidates[0]) == new

    exact_only_move = parse_contract(
        _contract([_component("registry", ["sample.tasks"], exact_modules=["sample.jobs"])])
    )
    assert rename_candidates(old, exact_only_move) == ()


def test_dart_exact_library_ownership_does_not_enable_unsupported_type_rule(
    tmp_path: Path,
) -> None:
    files = {
        "lib/registry.dart": "class Registry {}\n",
        "lib/registry_extra.dart": "class Extra {}\n",
    }
    components = [
        _dart_component("registry", "app.registry", packages=[], exact_modules=["app.registry"]),
        _dart_component("sibling", "app.registry_extra"),
    ]
    result = _observe_dart(
        tmp_path,
        files,
        {"components": components, "rules": []},
    )

    assert result.observation is not None, result.diagnostics
    modules = {
        record.data.get("qualified_name") for record in result.observation.records("modules") or ()
    }
    assert {"app.registry", "app.registry_extra"} <= modules
    owners = component_owners(result.observation)
    assert owner_of("app.registry", owners) == "registry"
    assert owner_of("app.registry_extra", owners) == "sibling"

    unsupported_root = tmp_path / "unsupported"
    unsupported_root.mkdir()
    unsupported = _observe_dart(
        unsupported_root,
        files,
        {
            "components": components,
            "rules": [_dart_rule("TYPES", "boundary_types", source="app.registry")],
        },
    )
    assert unsupported.exit_code == 2
    assert [item.kind for item in unsupported.diagnostics] == ["rule_unsupported_by_profile"]
    assert unsupported.observation is not None
    assert [
        (item.id, item.status, item.evaluation_proven)
        for item in rule_assessments(unsupported.observation, undecided_by_rule={})
    ] == [("TYPES", "UNKNOWN", False)]
