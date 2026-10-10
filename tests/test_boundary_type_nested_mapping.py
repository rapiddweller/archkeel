# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #432: independent decisions for one nested map and its native value."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_type_opaque_map_values import _OUTER as _LEGACY_OUTER
from test_boundary_type_opaque_map_values import _VALUE as _LEGACY_VALUE
from test_boundary_type_opaque_map_values import _app
from test_boundary_types_contained_mapping import _commit_report_fixture
from test_contract_model import VALIDATOR

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    contract_bytes,
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.ir.model import RecordData
from archkeel.ir.trace import trace_valid_violations
from archkeel.ir.widening import contract_widenings

_ANNOTATION = "Mapping[str, list[dict[str, object]]]"
_OUTER = {
    "qualified_name": "sample.app.impl.capture",
    "position": "products",
    "annotation": _ANNOTATION,
}
_INNER = {**_OUTER, "mapping_depth": 2}
_VALUE = {**_INNER, "container_depth": 3}


def _fixture(
    root: Path,
    allowances: tuple[dict[str, object], ...],
    *,
    annotation: str = _ANNOTATION,
    position: str = "products",
    facade: bool = False,
    prefix: str = "from typing import Mapping\n",
) -> None:
    declaration = (
        f"def capture(products: {annotation}) -> None: pass\n"
        if position == "products"
        else f"def capture() -> {annotation}: return {{}}\n"
    )
    _app(
        root,
        source=prefix + declaration,
        declared=(f"sample.app{'' if facade else '.impl'}:capture",),
        allowances=allowances,
    )
    if facade:
        (root / "sample/app/__init__.py").write_text(
            "from .impl import capture\n__all__ = ['capture']\n"
        )
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["."]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )


def _findings(root: Path) -> tuple[list[RecordData], list[RecordData]]:
    result = _observe(root)
    assert result.observation is not None and result.diagnostics == ()
    violations = [item.data for item in trace_valid_violations(result.observation)]
    facts = [
        item.data
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    return violations, facts


def test_nested_map_coordinates_are_valid_and_canonical() -> None:
    from test_boundary_type_allowances import _contract

    raw = _contract()
    raw["rules"][0]["allowed_positions"] = [_OUTER, _INNER, _VALUE]
    assert not list(VALIDATOR.iter_errors(raw))
    encoded = json.loads(contract_bytes(parse_contract(raw)))
    assert encoded["rules"][0]["allowed_positions"] == [
        {**selector, "field_path": ""} for selector in (_OUTER, _INNER, _VALUE)
    ]


@pytest.mark.parametrize("value", [True, 0, -1, 2.0, "2", None])
def test_mapping_depth_requires_positive_integer_token(value: object) -> None:
    from test_boundary_type_allowances import _contract

    raw = _contract()
    raw["rules"][0]["allowed_positions"] = [{**_INNER, "mapping_depth": value}]
    with pytest.raises(ValueError, match="mapping_depth must be a positive integer"):
        parse_contract(raw)


def test_mapping_value_depth_must_follow_selected_map() -> None:
    from test_boundary_type_allowances import _contract

    raw = _contract()
    raw["rules"][0]["allowed_positions"] = [{**_INNER, "container_depth": 2}]
    with pytest.raises(ValueError, match="container_depth must be mapping_depth plus one"):
        parse_contract(raw)


def test_mapping_depth_does_not_select_dto_fields() -> None:
    from test_boundary_type_allowances import _contract

    raw = _contract()
    raw["rules"][0]["allowed_positions"] = [{**_INNER, "field_path": "payload"}]
    with pytest.raises(ValueError, match="mapping_depth cannot select a DTO field"):
        parse_contract(raw)


def test_new_mapping_coordinate_is_a_widening() -> None:
    from test_boundary_type_allowances import _contract

    before = _contract(allowance=_OUTER)
    after = _contract(allowance=_OUTER)
    after["rules"][0]["allowed_positions"].append(_INNER)
    [change] = contract_widenings(parse_contract(before), parse_contract(after))
    assert "mapping_depth=2" in change


def test_legacy_widening_text_omits_absent_mapping_coordinate() -> None:
    from test_boundary_type_allowances import _contract

    before = _contract(allowance=_LEGACY_OUTER)
    after = _contract(allowance=_LEGACY_OUTER)
    after["rules"][0]["allowed_positions"].append(_LEGACY_VALUE)
    [message] = contract_widenings(parse_contract(before), parse_contract(after))
    assert "container_depth=1" in message
    assert "mapping_depth" not in message


def test_outer_inner_and_native_value_are_independent(tmp_path: Path) -> None:
    _fixture(tmp_path, ())
    baseline, _ = _findings(tmp_path)
    assert {(item.get("container_depth"), item.get("nested_annotation")) for item in baseline} == {
        (None, _ANNOTATION),
        (2, "dict[str, object]"),
        (3, "object"),
    }

    _fixture(tmp_path, (_OUTER,))
    outer, _ = _findings(tmp_path)
    assert len(outer) == 2

    _fixture(tmp_path, (_OUTER, _INNER))
    inner, facts = _findings(tmp_path)
    assert [(item.get("container_depth"), item.get("nested_annotation")) for item in inner] == [
        (3, "object")
    ]
    assert not any(fact.get("accepted_opacity") for fact in facts)

    _fixture(tmp_path, (_OUTER, _INNER, _VALUE))
    accepted, facts = _findings(tmp_path)
    assert accepted == []
    assert sum(fact.get("accepted_opacity") is True for fact in facts) == 1
    assert {fact.get("mapping_depth") for fact in facts if fact.get("mapping_depth")} == {2}


def test_existing_outer_fact_id_stays_stable(tmp_path: Path) -> None:
    _fixture(tmp_path, (_OUTER,))
    previous = _observe(tmp_path)
    assert previous.observation is not None
    [old] = [
        item
        for item in previous.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    _fixture(tmp_path, (_OUTER, _INNER, _VALUE))
    current = _observe(tmp_path)
    assert current.observation is not None
    [unchanged] = [
        item
        for item in current.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance" and item.data.get("mapping_depth") is None
    ]
    assert unchanged.id == old.id


@pytest.mark.parametrize(
    ("selector", "remaining_depths"),
    [
        (_INNER, {None, 3}),
        (_VALUE, {None, 2}),
        ({**_INNER, "mapping_depth": 1}, {None, 2, 3}),
        ({**_INNER, "mapping_depth": 3}, {None, 2, 3}),
    ],
    ids=("inner-only", "value-only", "wrong-map-depth-one", "wrong-map-depth-three"),
)
def test_one_coordinate_cannot_grant_its_neighbors(
    tmp_path: Path, selector: dict[str, object], remaining_depths: set[int | None]
) -> None:
    _fixture(tmp_path, (selector,))
    findings, _ = _findings(tmp_path)
    assert {item.get("container_depth") for item in findings} == remaining_depths


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize("position", ["products", "return"])
def test_nested_permissions_work_at_both_signature_positions(
    tmp_path: Path, facade: bool, position: str
) -> None:
    qualified_name = f"sample.app{'' if facade else '.impl'}.capture"
    selectors = tuple(
        {**selector, "qualified_name": qualified_name, "position": position}
        for selector in (_OUTER, _INNER, _VALUE)
    )
    _fixture(tmp_path, selectors, facade=facade, position=position)
    findings, facts = _findings(tmp_path)
    assert findings == []
    assert len(facts) == 3
    assert sum(fact.get("accepted_opacity") is True for fact in facts) == 1


@pytest.mark.parametrize(
    ("annotation", "prefix"),
    [
        ("Mapping[str, tuple[dict[str, object]]]", "from typing import Mapping\n"),
        (
            "Mapping[str, list[dict[str, object] | dict[str, object]]]",
            "from typing import Mapping\n",
        ),
        (
            "Mapping[str, list[tuple[dict[str, object], dict[str, object]]]]",
            "from typing import Mapping\n",
        ),
        ("Mapping[str, list[dict[str, object]]] | None", "from typing import Mapping\n"),
        ("Mapping[str, list[dict[str, object]]]", "from typing import Mapping\nclass list: pass\n"),
        ("Mapping[str, list[dict[str, object]]]", "from typing import Mapping\nclass str: pass\n"),
        (
            "Mapping[str, list[dict[str, object]]]",
            "from typing import Mapping\nclass object: pass\n",
        ),
        ("Mapping[str, list[dict[str, object]]]", "from typing import Mapping\nclass dict: pass\n"),
        (
            "Payload",
            "from typing import Mapping\nPayload = Mapping[str, list[dict[str, object]]]\n",
        ),
        (
            "Mapping[str, list[Envelope]]",
            "from typing import Mapping\nEnvelope = dict[str, object]\n",
        ),
        ("Mapping[str, list[Unknown[dict[str, object]]]]", "from typing import Mapping\n"),
        (
            "Mapping[str, list[dict[str, object]]]",
            "from typing import Mapping\nclass Mapping: pass\n",
        ),
    ],
    ids=(
        "tuple-wrapper",
        "duplicate-union",
        "sibling-maps",
        "nullable-union",
        "shadowed-list",
        "shadowed-str",
        "shadowed-object",
        "shadowed-map",
        "alias",
        "inner-alias",
        "unknown-wrapper",
        "shadowed-outer",
    ),
)
def test_only_the_exact_unambiguous_chain_can_use_mapping_depth(
    tmp_path: Path, annotation: str, prefix: str
) -> None:
    selectors = ({**_INNER, "annotation": annotation}, {**_VALUE, "annotation": annotation})
    _fixture(tmp_path, selectors, annotation=annotation, prefix=prefix)
    _, facts = _findings(tmp_path)
    assert not any(fact.get("mapping_depth") for fact in facts)


def test_cli_report_retains_all_three_decisions(tmp_path: Path) -> None:
    _fixture(tmp_path, (_OUTER, _INNER, _VALUE))
    _observe(tmp_path)
    _commit_report_fixture(tmp_path)
    output = tmp_path / "architecture.json"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from archkeel.cli import main; raise SystemExit(main())",
            "report",
            "--root",
            str(tmp_path),
            "--output",
            str(output),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    assert trace_valid_violations(observation) == ()
    facts = [
        item
        for item in observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert len(facts) == 3
    assert sum(item.data.get("accepted_opacity") is True for item in facts) == 1
    [declaration] = [
        item
        for item in observation.records("declarations") or ()
        if item.id == "APP-TYPES-NOT-DICT"
    ]
    positions = declaration.data.get("allowed_positions")
    assert positions is not None
    assert [entry.get("mapping_depth") for entry in positions] == [None, 2, 2]
    assert [entry.get("container_depth") for entry in positions] == [None, None, 3]


def test_nested_permissions_require_and_survive_amendment(tmp_path: Path) -> None:
    _fixture(tmp_path, (_OUTER,))
    _observe(tmp_path)
    _commit_report_fixture(tmp_path)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    _fixture(tmp_path, (_OUTER, _INNER, _VALUE))
    config = ScanConfig((".",), "sample", "contract.json", "0" * 64)

    blocked, _ = run_validate(tmp_path, config, observe, against=base)
    assert blocked.exit_code == 1
    assert any("mapping_depth=2" in item for item in blocked.failures)
    assert any("container_depth=3" in item for item in blocked.failures)

    amendment = tmp_path / "amendment.json"
    written, files = run_validate(
        tmp_path,
        config,
        observe,
        against=base,
        amendment=amendment,
        write_amendment=True,
        decided_by="architect",
        rationale="Accept only this nested product envelope.",
    )
    assert written.exit_code == 0, written.diagnostics
    amendment.write_bytes(files[str(amendment)])
    accepted, _ = run_validate(tmp_path, config, observe, against=base, amendment=amendment)
    assert accepted.exit_code == 0 and accepted.failures == ()
