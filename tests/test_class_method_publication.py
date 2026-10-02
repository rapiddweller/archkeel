# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A public method publishes its return type at each declared boundary."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_inside_publication import _child, _inside, _rule, _write_project

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import inside_diagnostics, interface_diagnostics
from archkeel.ir.codec import parse_contract


@pytest.mark.parametrize(
    ("class_name", "method_name", "used"),
    [("Service", "make", True), ("Service", "_make", False), ("Unrelated", "make", False)],
    ids=["public-method", "private-method", "unpublished-class"],
)
def test_class_method_type_usage_is_bound_to_the_published_class(
    tmp_path: Path, class_name: str, method_name: str, used: bool
) -> None:
    public = ["sample.core.api:Service", "sample.core.api:Payload"]
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=public) | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[_rule("ROOT-INTERFACE", "interface_boundary")],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api", public=public),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": "class Payload: pass\n"
            + ("class Service: pass\n" if class_name != "Service" else "")
            + f"class {class_name}:\n    def {method_name}(self) -> Payload: ...\n",
            "sample/client.py": "from sample.core.api import Service\nVALUE = Service()\n",
        },
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    contract = parse_contract(json.loads((tmp_path / "contract.json").read_text()))
    root_diagnostics = interface_diagnostics(contract, result.observation)
    nested_diagnostics = inside_diagnostics(
        tmp_path,
        contract,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )
    for diagnostics in (root_diagnostics, nested_diagnostics):
        assert any(
            item.code == "interface.unused" and item.subject == public[1] for item in diagnostics
        ) is (not used)
