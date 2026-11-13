# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Guarded-effect receipts require full coverage of their selected source domain."""

from __future__ import annotations

import json
from pathlib import Path

from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.ir.decisions import rule_assessments


def _guard_rule(source: str) -> dict[str, object]:
    return _rule(
        "forbidden_effect_under_condition",
        id="NO-EFFECT-WHEN-SEEDED",
        source=source,
        target="sample.safe.core._effect",
        condition={"kind": "parameter", "owner": "sample.safe.core.generate", "name": "seeded"},
    )


def _contract(*, mounted: bool, source: str) -> dict[str, object]:
    rule = _guard_rule(source)
    inside = {
        "schema_version": "3.13.0",
        "components": [_component("inside", ["sample"])],
        "rules": [rule],
    }
    if not mounted:
        return {
            "schema_version": "3.13.0",
            "components": [_component("all", ["sample"])],
            "rules": [rule],
        }
    return {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"], inside="inside.json")],
        "rules": [],
        "_inside": inside,
    }


def _observe(
    tmp_path: Path,
    *,
    roots: tuple[str, ...],
    mounted: bool,
    source: str,
    violating: bool,
):
    contract = _contract(mounted=mounted, source=source)
    branch = "if seeded" if violating else "if not seeded"
    files = {
        "sample/__init__.py": "",
        "sample/safe/__init__.py": "",
        "sample/safe/core.py": f"""def _effect():
    return None

def generate(seeded: bool):
    {branch}:
        _effect()
""",
        "sample/core.py": """from .safe.core import _effect

def hidden(seeded: bool):
    if seeded:
        _effect()
""",
    }
    inside = contract.pop("_inside", None)
    if inside is not None:
        files["inside.json"] = json.dumps(inside)
    return _observe_tree(tmp_path, files, contract, roots=roots)


def _assessment(observation):
    [row] = [
        item
        for item in rule_assessments(observation, undecided_by_rule={})
        if item.kind == "forbidden_effect_under_condition"
    ]
    return row
