# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exact module ownership is distinct from recursive package ownership."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_declared_module_targets import _contract as _target_contract

from archkeel.cli.observe import observe
from archkeel.ir.codec import contract_bytes, contract_digest, parse_contract
from archkeel.ir.renames import rename_candidates, renamed_contract
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
