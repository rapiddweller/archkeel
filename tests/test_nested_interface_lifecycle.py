# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nested interface lifecycle checks use evidence from the owning level."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_recursive_inside_independent_contracts import (
    _commit_tree,
    _scan_config,
    _write_three_levels,
)

from archkeel.analyzer import observe
from archkeel.check.validation import COMPONENT_GRAPH_MARKER, run_validate

_ENTRY = "sample.layer.source.api:Payload"
_INTERFACE_RULE = {
    "id": "INTERFACE",
    "kind": "interface_boundary",
    "rationale": "Require intentional local APIs.",
    "provenance": ["docs/architecture/sample.md"],
    "decided_by": "architect",
}


def _prepare(
    root: Path,
    *,
    source_code: str = "class Payload:\n    pass\n",
    target_code: str = "VALUE = 1\n",
    public: list[str] | None = None,
    planned: list[str] | None = None,
    interface_rule: bool = True,
    unrelated_facade: bool = False,
    parent_facade: bool = False,
) -> None:
    _write_three_levels(root)
    root_path = root / "contract.json"
    root_contract = json.loads(root_path.read_text())
    root_contract["rules"] = []
    leaf_parent = root_contract["components"][0]
    if unrelated_facade:
        leaf_parent["packages"] = ["sample.layer"]
        root_contract["rules"] = [_INTERFACE_RULE]
        root_contract["components"].append(
            _component(
                "foreign",
                packages=["sample.foreign"],
                public=["sample.foreign.api:consume"],
            )
        )
        root_contract["components"].append(
            _component("client", packages=["sample.client"], public=[])
        )
        (root / "sample/foreign").mkdir(parents=True)
        (root / "sample/foreign/__init__.py").write_text("")
        (root / "sample/foreign/api.py").write_text(
            "from sample.layer.source.api import Payload\n\n"
            "def consume(payload: Payload) -> None:\n    return None\n\n"
            "__all__ = ['consume']\n"
        )
        (root / "sample/client").mkdir(parents=True)
        (root / "sample/client/__init__.py").write_text("")
        (root / "sample/client/api.py").write_text(
            "from sample.foreign.api import consume\n\nVALUE = consume\n"
        )
    if parent_facade:
        leaf_parent["public"] = ["sample.layer:wrap"]
        (root / "sample/layer/__init__.py").write_text(
            "from sample.layer.source.api import Payload\n\n"
            "def wrap(payload: Payload) -> str:\n    return 'ok'\n\n"
            "__all__ = ['wrap']\n"
        )
    root_path.write_text(json.dumps(root_contract))

    middle_path = root / "contracts/one.json"
    middle_contract = json.loads(middle_path.read_text())
    middle_contract["rules"] = []
    middle_path.write_text(json.dumps(middle_contract))

    leaf_path = root / "contracts/two.json"
    leaf_contract = json.loads(leaf_path.read_text())
    leaf_contract["rules"] = [_INTERFACE_RULE] if interface_rule else []
    source = leaf_contract["components"][0]
    source["public"] = public if public is not None else []
    if planned is not None:
        source["planned"] = planned
    leaf_path.write_text(json.dumps(leaf_contract))
    (root / "sample/layer/source/api.py").write_text(source_code)
    (root / "sample/layer/target/api.py").write_text(target_code)
    if unrelated_facade:
        (root / "docs/architecture/sample.md").write_text(
            f"# Architecture\n\n{COMPONENT_GRAPH_MARKER}\n"
            "```mermaid\ngraph TD\n  foreign --> app\n  client --> foreign\n```\n"
        )
    _commit_tree(root)


@pytest.mark.parametrize(
    ("source_code", "entry", "expected_code"),
    [
        ("class Payload:\n    pass\n", _ENTRY, "interface.unused"),
        ("VALUE = 1\n", "sample.layer.source.api:VALUE", "interface.unused"),
    ],
    ids=["unused-type", "unused-constant"],
)
def test_nested_unused_public_is_reported_at_its_mounted_pointer(
    tmp_path: Path, source_code: str, entry: str, expected_code: str
) -> None:
    _prepare(tmp_path, source_code=source_code, public=[entry])

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert result.exit_code == 2, result
    assert [(item.code, item.pointer, item.subject) for item in result.diagnostics] == [
        (
            expected_code,
            "/components/0/inside/components/0/inside/components/0/public/0",
            entry,
        )
    ]


@pytest.mark.parametrize(
    ("target_code", "parent_facade"),
    [
        (
            "from sample.layer.source.api import Payload\nVALUE = Payload()\n",
            False,
        ),
        ("VALUE = 1\n", True),
    ],
    ids=["local-sibling-import", "parent-facade-signature"],
)
def test_nested_public_use_is_proven_by_a_sibling_or_parent_facade(
    tmp_path: Path, target_code: str, parent_facade: bool
) -> None:
    _prepare(
        tmp_path,
        target_code=target_code,
        public=[_ENTRY],
        parent_facade=parent_facade,
    )

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert result.exit_code == 0, result.diagnostics
    assert not any(item.code == "interface.unused" for item in result.diagnostics)
    if parent_facade:
        observed = _observe(tmp_path)
        assert observed.observation is not None, observed.diagnostics
        facade = next(
            item
            for item in observed.observation.records("symbols") or ()
            if item.data.get("module") == "sample.layer" and item.data.get("name") == "wrap"
        )
        assert "sample.layer.source.api.Payload" in facade.data.get("facade_types", ())


def test_unrelated_facade_signature_does_not_satisfy_nested_public_usage(
    tmp_path: Path,
) -> None:
    _prepare(tmp_path, public=[_ENTRY], unrelated_facade=True)

    result, _ = run_validate(tmp_path, _scan_config(), observe)
    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    facade = next(
        item
        for item in observed.observation.records("symbols") or ()
        if item.data.get("module") == "sample.foreign.api" and item.data.get("name") == "consume"
    )
    assert "sample.layer.source.api.Payload" in facade.data.get("facade_types", ())
    assert any(item.code == "rule.violated" for item in result.diagnostics), result

    assert [
        (item.code, item.pointer, item.subject)
        for item in result.diagnostics
        if item.code == "interface.unused"
    ] == [
        (
            "interface.unused",
            "/components/0/inside/components/0/inside/components/0/public/0",
            _ENTRY,
        )
    ]


@pytest.mark.parametrize(
    ("target_code", "expected_codes"),
    [
        ("VALUE = 1\n", ()),
        (
            "from sample.layer.source.api import Payload\nVALUE = Payload()\n",
            ("interface.planned_built", "rule.violated"),
        ),
    ],
    ids=["built-unused-remains-planned", "used-planned-needs-promotion"],
)
def test_nested_planned_entry_lifecycle(
    tmp_path: Path, target_code: str, expected_codes: tuple[str, ...]
) -> None:
    _prepare(tmp_path, target_code=target_code, planned=[_ENTRY])

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert {item.code for item in result.diagnostics} == set(expected_codes), result
    assert result.exit_code == (2 if expected_codes else 0), result
    if "interface.planned_built" in expected_codes:
        assert any(
            item.pointer == "/components/0/inside/components/0/inside/components/0/planned/0"
            and item.subject == _ENTRY
            for item in result.diagnostics
        )


def test_nested_public_without_interface_rule_stays_ungated(tmp_path: Path) -> None:
    _prepare(tmp_path, public=[_ENTRY], interface_rule=False)

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert result.exit_code == 0
    assert result.diagnostics == ()
