# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-244: an empty literal `__all__` states an empty surface instead of no surface."""

from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_delta import _model, _record
from test_inside_publication import _rule, _write_project

from archkeel.check.evaluation.evaluate import api_surface_limits
from archkeel.check.validation import public_api_diagnostics
from archkeel.ir.codec import parse_contract, parse_observation
from archkeel.ir.model import ContractDeclarations
from archkeel.ir.trace import trace_valid_violations


def _violations(
    tmp_path: Path,
    all_line: str,
    use: str = "from sample.core import sub\nfrom sample.core import helper\n",
) -> set[tuple[object, object]]:
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=["sample.core"]),
            _component("client", packages=["sample.client"]),
        ],
        rules=[_rule("INTERFACE", "interface_boundary")],
        insides={},
        files={
            "sample/core/__init__.py": all_line + "def helper(): pass\nother = 1\n",
            "sample/core/sub.py": "def run(): pass\n",
            "sample/client/__init__.py": "",
            "sample/client/use.py": use,
        },
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    return {
        (item.data.get("target_module"), item.data.get("symbol"))
        for item in trace_valid_violations(result.observation)
    }


@pytest.mark.parametrize(
    ("all_line", "helper_exposed"),
    [("", True), ("__all__ = []\n", False), ("__all__ = ['other']\n", False)],
    ids=["no-all", "empty-literal", "other-name"],
)
def test_module_facade_exposes_only_its_stated_surface(tmp_path, all_line, helper_exposed):
    violations = _violations(tmp_path, all_line)
    assert (("sample.core", "helper") not in violations) is helper_exposed
    # A submodule import targets the submodule, never the package's own names.
    assert ("sample.core.sub", None) in violations


@pytest.mark.parametrize(
    "all_line", ["", "__all__ = []\n", "__all__ = ['other']\n"], ids=["no-all", "empty", "other"]
)
def test_star_import_binds_exactly_the_stated_surface(tmp_path, all_line):
    assert _violations(tmp_path, all_line, "from sample.core import *\n") == set()


def _module(all_exports: list[str], all_literal: bool) -> dict[str, object]:
    return _record(
        "MOD-sample.core",
        kind="module",
        data={
            "qualified_name": "sample.core",
            "all_exports": all_exports,
            "all_literal": all_literal,
        },
    )


@pytest.mark.parametrize(
    ("all_exports", "all_literal", "missing"),
    [([], True, True), ([], False, False), (["Widget"], True, False)],
    ids=["empty-literal", "no-all", "listed"],
)
def test_promised_name_is_checked_against_an_empty_literal_all(all_exports, all_literal, missing):
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [],
            "rules": [],
            "declarations": {"public_api": ["sample.core:Widget"]},
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, modules=[_module(all_exports, all_literal)], imports=[])
    )
    codes = [item.code for item in public_api_diagnostics(contract, observation)]
    assert codes == (["api_surface.missing"] if missing else [])


@pytest.mark.parametrize(("stated", "unknown"), [(None, True), (frozenset(), False)])
def test_api_surface_unknown_only_for_a_module_without_stated_surface(stated, unknown):
    limits = api_surface_limits(
        ContractDeclarations(public_api=("sample.core:Widget",)),
        [],
        {"sample.core": stated},
        "reason",
    )
    assert bool(limits) is unknown
