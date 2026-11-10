# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-349: the host keeps the template of a macro out of the graph and counts it as coupling.

Consumer: `split_imports` and `count_macro_bodies` of the evaluation.
"""

from __future__ import annotations

from archkeel.check.evaluation.imports import count_macro_bodies, split_imports
from archkeel.ir.facts_codec import RawRecord


def _import(identity: str, kind: str, source: str, target: str) -> RawRecord:
    data = {"source_module": source, "target_module": target}
    return {"id": identity, "kind": kind, "data": data}  # type: ignore[typeddict-item]


def _module(name: str) -> RawRecord:
    return {"data": {"qualified_name": name, "fan_in": 0, "fan_out": 0}}  # type: ignore[typeddict-item]


def test_the_template_of_a_macro_leaves_the_edges_and_the_unresolved_stay_apart() -> None:
    imports = [
        _import("I1", "import", "a", "b"),
        _import("I2", "macro_body", "m", "b"),
        _import("I3", "import", "a", "gone"),
    ]

    resolved, unknown, templates = split_imports(imports, {"I3": object()})

    assert [item["id"] for item in resolved] == ["I1"]
    assert [item["id"] for item in unknown] == ["I3"]
    assert [item["id"] for item in templates] == ["I2"]


def test_a_pair_that_only_a_template_names_counts_once_as_coupling() -> None:
    templates = [
        _import("I1", "macro_body", "m", "b"),
        _import("I2", "macro_body", "m", "b"),
        _import("I3", "macro_body", "a", "b"),
    ]
    modules = [_module("a"), _module("b"), _module("m")]

    count_macro_bodies(modules, templates, [("a", "b")])

    fans = {
        item["data"]["qualified_name"]: (item["data"]["fan_in"], item["data"]["fan_out"])
        for item in modules
    }
    assert fans == {"a": (0, 0), "b": (1, 0), "m": (0, 1)}
