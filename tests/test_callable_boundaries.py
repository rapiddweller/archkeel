# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explicit callback signatures use the existing boundary policy at each leaf."""

from pathlib import Path

import pytest
from test_boundary_types_reexport_proofs import _observe_facade

from archkeel.ir.trace import trace_valid_violations

_LOOKUP_API = (
    "from collections.abc import Callable\n\n"
    '__all__ = ["use_lookup", "build_lookup"]\n\n'
    "def use_lookup(lookup: Callable[[str], int | None]) -> bool:\n"
    '    return lookup("id") is not None\n\n'
    "def build_lookup() -> Callable[[str], int | None]:\n"
    "    return lambda key: 1\n"
)


def test_explicit_lookup_parameter_and_return_are_decidable(tmp_path: Path) -> None:
    observation = _observe_facade(tmp_path, api=_LOOKUP_API, public="sample.app.api")
    assert not trace_valid_violations(observation)
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


@pytest.mark.parametrize("alias", [False, True])
@pytest.mark.parametrize("facade", [False, True])
def test_callable_named_model_references_keep_alias_and_facade_safety(
    tmp_path: Path, alias: bool, facade: bool
) -> None:
    annotation = "Lookup" if alias else "Callable[[Payload], Payload]"
    body = (
        "from typing import Callable\n"
        "class Payload:\n    value: str\n__all__ = ['lookup', 'Payload']\n"
        + ("Lookup = Callable[[Payload], Payload]\n" if alias else "")
        + f"def lookup(value: {annotation}) -> bool: return True\n"
    )
    observation = _observe_facade(
        tmp_path,
        api=(
            "from .impl import lookup, Payload\n__all__ = ['lookup', 'Payload']\n"
            if facade
            else body
        ),
        implementation=body if facade else "",
        public="sample.app.api",
    )
    assert not trace_valid_violations(observation)
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


@pytest.mark.parametrize(
    ("annotation", "routes", "unknown"),
    [
        ("Callable[[object], int]", ("argument[0]",), False),
        ("Callable[[str], object]", ("result",), False),
        ("Callable[[object, object], object]", ("argument[0]", "argument[1]", "result"), False),
        ("Callable[[Missing], object]", ("result",), True),
    ],
)
def test_callable_leaves_retain_each_violation_beside_unknowns(
    tmp_path: Path, annotation: str, routes: tuple[str, ...], unknown: bool
) -> None:
    observation = _observe_facade(
        tmp_path,
        api=(
            "from typing import Callable\n__all__ = ['lookup']\n"
            f"def lookup(value: {annotation}) -> bool: return True\n"
        ),
        public="sample.app.api",
    )
    findings = trace_valid_violations(observation)
    assert len(findings) == len(routes)
    assert all(
        any(f"Callable {route}" in str(item.data.get("reason")) for item in findings)
        for route in routes
    )
    assert all(item.data.get("annotation") == annotation for item in findings)
    assert all(item.data.get("nested_annotation") == "object" for item in findings)
    assert all(
        item.data.get("path") is None and item.data.get("container_depth") is None
        for item in findings
    )
    unknowns = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]
    assert bool(unknowns) is unknown
    if unknown:
        positions = [item for item in unknowns if item.kind == "boundary_type_position"]
        assert len(positions) == 1
        assert positions[0].data.get("reason") == "unresolved_name"
        assert "Callable argument[0]" in positions[0].title and "Missing" in positions[0].title
        assert positions[0].data.get("path") is None
        assert positions[0].data.get("nested_annotation") is None
        limits = [item for item in unknowns if item.kind == "boundary_type_limit"]
        assert len(limits) == 1
        assert limits[0].data.get("positions") == 2
        assert limits[0].data.get("undecided") == 1
        assert limits[0].data.get("unresolved_name") == 1


@pytest.mark.parametrize(
    ("provider", "head", "intermediate"),
    [
        ("from typing import Callable as C", "C", None),
        ("from collections.abc import Callable as C", "C", None),
        ("import typing as t", "t.Callable", None),
        ("import collections.abc as abc", "abc.Callable", None),
        (
            "from .intermediate import Callback",
            "Callback",
            "from typing import Callable as Callback\n__all__ = ['Callback']\n",
        ),
    ],
)
@pytest.mark.parametrize("leaf", ["str", "object"])
def test_callable_requires_provider_origin_through_each_route(
    tmp_path: Path, provider: str, head: str, intermediate: str | None, leaf: str
) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        intermediate=intermediate,
        api=(
            f"{provider}\n__all__ = ['lookup']\n"
            f"def lookup(value: {head}[[{leaf}], int]) -> bool: return True\n"
        ),
    )
    findings = trace_valid_violations(observation)
    assert len(findings) == (leaf == "object")
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


@pytest.mark.parametrize(
    ("provider", "annotation", "extra", "implementation"),
    [
        ("from .impl import Callable", "Callable[[str], int]", "", "def Callable(): pass\n"),
        ("from .impl import Callable", "Callable[[str], int]", "", "class Callable: pass\n"),
        ("from typing import Callable", "Callable[[str], int]", "Callable.attr = 1\n", None),
        ("from typing import Callable", "Callable[[str], int]", "mutate(Callable)\n", None),
        ("from typing import Callable", "Callable[[str], int]", "Callable(object)\n", None),
        (
            "from typing import Callable",
            "Lookup",
            "Lookup = Callable[[str], int]\nmutate(Lookup)\n",
            None,
        ),
        (
            "from typing import Callable",
            "Callable[[Payload], int]",
            "class Payload: value: str\nmutate(Payload)\n",
            None,
        ),
        ("import collections.abc", "collections.abc.Callable[[str], int]", "", None),
        ("import collections.abc as collections", "collections.Callable[[str], int]", "", None),
        ("from typing import Callable", "Callable[..., int]", "", None),
        ("from typing import Callable", "Callable", "", None),
        (
            "from typing import Callable, Concatenate",
            "Callable[Concatenate[str, P], int]",
            "",
            None,
        ),
        ("from typing import Callable", "Callable[[*Ts], int]", "", None),
        ("from typing import Callable", "Callable[['Missing'], int]", "", None),
        ("from typing import Callable", "Callable[[factory()], int]", "", None),
        ("from typing import Callable", "Loop", "Loop = Loop\n", None),
        ("from typing import Callable", "Lookup[str]", "Lookup = Callable[[str], int]\n", None),
        (
            "from typing import Callable",
            "Callable[[str], int]",
            "if condition: Callable = other\n",
            None,
        ),
        ("from typing import Callable", "Callable[[str], int]", "from unknown import *\n", None),
        ("from typing import Callable", "Callable[P, int]", "", None),
        ("from typing import Callable", "Callable[(str,), int]", "", None),
        ("from typing import Callable", "Callable[[str]]", "", None),
        ("from typing import Callable", "Callable[[str], int, bool]", "", None),
    ],
)
def test_unproven_or_unsupported_callable_stays_unknown(
    tmp_path: Path, provider: str, annotation: str, extra: str, implementation: str | None
) -> None:
    declared = ["lookup", "Payload"] if "class Payload" in extra else ["lookup"]
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        implementation=implementation,
        api=(
            f"{provider}\n{extra}__all__ = {declared!r}\n"
            f"def lookup(value: {annotation}) -> bool: return True\n"
        ),
    )
    assert not trace_valid_violations(observation)
    positions = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
        and item.kind == "boundary_type_position"
        and item.data.get("position") == "value"
    ]
    assert len(positions) == 1


@pytest.mark.parametrize(
    "annotation",
    [
        "Callable[[Missing, Other], int]",
        "Callable[[Callable[[Missing], object] | None], object]",
        "Lookup",
    ],
)
def test_callable_unknown_context_keeps_first_leaf_and_known_siblings(
    tmp_path: Path, annotation: str
) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        api=(
            "from typing import Callable\n"
            "Lookup = Callable[[Callable[[Missing], object] | None], object]\n"
            "__all__ = ['lookup']\n"
            f"def lookup(value: {annotation}) -> bool: return True\n"
        ),
    )
    positions = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids and item.kind == "boundary_type_position"
    ]
    assert len(positions) == 1
    assert positions[0].data.get("reason") == "unresolved_name"
    assert "Callable argument[0]" in positions[0].title and "Missing" in positions[0].title
    assert "Other" not in positions[0].title
    assert positions[0].data.get("path") is None
    assert len(trace_valid_violations(observation)) == (0 if "Other" in annotation else 2)


@pytest.mark.parametrize(
    "body",
    [
        "from typing import TypeAlias\nLookup: TypeAlias = Callable[[str], int]\n",
        "Lookup = Callable[[], None]\n",
        "Lookup = Callable[[str], int | None]\n",
        "Lookup = Callable[[str | int], bool | int]\n",
    ],
)
def test_explicit_and_empty_callback_aliases_are_decidable(tmp_path: Path, body: str) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        api=(
            "from typing import Callable\n" + body + "__all__ = ['lookup']\n"
            "def lookup(value: Lookup) -> bool: return True\n"
        ),
    )
    assert not trace_valid_violations(observation)
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


def test_callback_unknown_keeps_real_dto_path(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        api=(
            "from typing import Callable\n"
            "class Payload: value: Missing\n__all__ = ['Payload', 'lookup']\n"
            "def lookup(value: Callable[[Payload], object]) -> bool: return True\n"
        ),
    )
    positions = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids and item.kind == "boundary_type_position"
    ]
    assert len(positions) == 1
    assert positions[0].data.get("path") == "value.value"
    assert positions[0].data.get("nested_annotation") == "Missing"
    assert "Callable argument[0]" in positions[0].title
    assert len(trace_valid_violations(observation)) == 1


def test_callback_union_references_keep_both_declared_owners_static(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        api=(
            "from typing import Callable\n"
            "class First: value: str\nclass Second: value: int\n"
            "__all__ = ['lookup', 'First', 'Second']\n"
            "def lookup(value: Callable[[First | Second], First | Second]) -> bool: return True\n"
        ),
    )
    assert not trace_valid_violations(observation)
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


def test_inherited_callback_unknown_keeps_diagnostic_context(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        api=(
            "from typing import Callable\n__all__ = ['Base', 'Public']\n"
            "class Base:\n"
            "    def run(self, value: Callable[[Missing], object]) -> bool: return True\n"
            "class Public(Base): pass\n"
        ),
    )
    positions = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
        and item.kind == "boundary_type_position"
        and item.data.get("qualified_name") == "sample.app.api.Public.run"
    ]
    assert len(positions) == 1
    assert "Callable argument[0]" in positions[0].title and "Missing" in positions[0].title
    assert positions[0].data.get("reason") == "unresolved_name"


@pytest.mark.requires_python(12)
@pytest.mark.parametrize("parameters", ["", "[T]"])
def test_pep695_callback_alias_keeps_generic_aliases_out_of_scope(
    tmp_path: Path, parameters: str
) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        api=(
            "from typing import Callable\n"
            f"type Lookup{parameters} = Callable[[str], int]\n"
            "__all__ = ['lookup']\ndef lookup(value: Lookup) -> bool: return True\n"
        ),
    )
    positions = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids and item.kind == "boundary_type_position"
    ]
    assert bool(positions) is bool(parameters)
    assert not trace_valid_violations(observation)


@pytest.mark.parametrize("selector", [{}, {"container_depth": 1}, {"mapping_depth": 1}])
def test_existing_map_selectors_cannot_allow_callback_leaves(
    tmp_path: Path, selector: dict[str, int]
) -> None:
    from test_analyzer import _observe
    from test_boundary_types_nested_dtos import _write_app

    annotation = "Callable[[dict[str, str]], dict[str, object]]"
    _write_app(
        tmp_path,
        implementation=(
            f"from typing import Callable\ndef lookup(value: {annotation}) -> bool: return True\n"
        ),
        declared=("sample.app.impl:lookup",),
        allowed_positions=(
            {
                "qualified_name": "sample.app.impl.lookup",
                "position": "value",
                "annotation": annotation,
                "field_path": "",
                **selector,
            },
        ),
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    assert len(trace_valid_violations(result.observation)) == 3
    assert not result.observation.records("boundary_type_allowances")


@pytest.mark.parametrize("unsafe", [False, True])
def test_imported_callback_alias_uses_provider_scope_and_every_hop(
    tmp_path: Path, unsafe: bool
) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        implementation=(
            "from typing import Callable, TypeAlias\n"
            "class Payload: value: str\n"
            "Lookup: TypeAlias = Callable[[Payload], object]\n"
            "__all__ = ['Lookup', 'Payload']\n"
        ),
        intermediate="from .impl import Lookup\n__all__ = ['Lookup']\n",
        api=(
            "from .intermediate import Lookup\n"
            "from .impl import Payload as ProviderPayload\n"
            "class Payload: value: object\n__all__ = ['lookup', 'ProviderPayload']\n"
            + ("mutate(Lookup)\n" if unsafe else "")
            + "def lookup(value: Lookup) -> bool: return True\n"
        ),
    )
    findings = trace_valid_violations(observation)
    assert len(findings) == (0 if unsafe else 1)
    if findings:
        assert "Callable result" in str(findings[0].data.get("reason"))
    positions = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids and item.kind == "boundary_type_position"
    ]
    assert bool(positions) is unsafe
    if unsafe:
        assert positions[0].data.get("annotation") == "Lookup"


@pytest.mark.parametrize("opaque", [False, True])
def test_opaque_callback_heads_keep_ordinary_source_signature_decidable(
    tmp_path: Path, opaque: bool
) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        api=(
            "from typing import Callable\n"
            "class Payload: value: str\nclass Safe: value: str\n"
            + ("mutate(Payload)\n" if opaque else "")
            + "__all__ = ['lookup', 'Payload', 'Safe']\n"
            "def lookup(unsafe: Callable[[Payload], object], safe: Callable[[Safe], int], "
            "ordinary: Payload) -> bool: return True\n"
        ),
    )
    positions = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids and item.kind == "boundary_type_position"
    ]
    assert {(item.data.get("position"), item.data.get("reason")) for item in positions} == (
        {("unsafe", "generic"), ("safe", "generic")} if opaque else set()
    )
    assert len(positions) == (2 if opaque else 0)
    findings = trace_valid_violations(observation)
    assert len(findings) == (0 if opaque else 1)
    if findings:
        assert findings[0].data.get("position") == "unsafe"
        assert "Callable result" in str(findings[0].data.get("reason"))
    [head] = [
        item for item in observation.records("imports") if item.data.get("binding") == "Callable"
    ]
    assert head.data.get("source_binding_unique") is True
    assert head.data.get("source_member_binding_static") is (not opaque)


@pytest.mark.parametrize("unsafe_hop", [False, True])
def test_core_uses_collected_shapes_without_parsing_and_keeps_late_alias_findings(
    unsafe_hop: bool,
) -> None:
    from unittest.mock import patch

    from test_analyzer import _parsed_module

    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports
    from archkeel.analyzer.python.symbols import collect_symbols
    from archkeel.analyzer.python.type_shapes import collect_type_shapes
    from archkeel.check.evaluation.boundary_types import (
        _boundary_type_verdict,
        boundary_type_indexes,
    )

    modules = [
        _parsed_module(
            "from typing import Callable, TypeAlias\nLookup: TypeAlias = Callable[[str], object]\n",
            "sample.impl",
        ),
        _parsed_module("from .impl import Lookup\n__all__ = ['Lookup']\n", "sample.middle"),
        _parsed_module("from .middle import Lookup\n", "sample.api"),
    ]
    evidence = {}
    raw_imports = collect_imports(
        modules, {module.module for module in modules}, evidence, namespace="sample"
    )
    exports = {module.module: module.all_exports for module in modules}
    resolve_reexports(raw_imports, exports, modules)
    symbols, _, _ = collect_symbols(modules, evidence)
    if unsafe_hop:
        for item in raw_imports:
            if item["data"]["source_module"] == "sample.middle":
                item["data"]["source_member_binding_static"] = False
    imports, classes = boundary_type_indexes(symbols, raw_imports, exports_by_module=exports)
    shapes = collect_type_shapes(["Lookup", "Callable[[str], object]"])
    with patch("ast.parse", side_effect=AssertionError("Core reparsed source syntax")):
        verdict = _boundary_type_verdict(
            "Lookup", "sample.api", None, {}, imports, classes, type_shapes=shapes
        )
    assert len(verdict.violations) == 1
    assert "Callable result" in verdict.violations[0][0]
    assert verdict.contains_callable
    assert verdict.referenced_members_static is (not unsafe_hop)
    assert verdict.undecidable == ("other" if unsafe_hop else None)
    if unsafe_hop:
        assert verdict.unknown_context == "Callable reference Lookup"


@pytest.mark.parametrize(
    "missing",
    [
        "source_binding_unique",
        "source_member_binding_static",
        "module_level_import",
        "ordinary_module",
        "under_type_checking",
    ],
)
def test_callable_core_needs_positive_provider_flags(missing: str) -> None:
    from test_analyzer import _parsed_module

    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports
    from archkeel.analyzer.python.type_shapes import collect_type_shapes
    from archkeel.check.evaluation.boundary_types import (
        _boundary_type_verdict,
        boundary_type_indexes,
    )

    module = _parsed_module("from typing import Callable\n", "sample.api")
    imports = collect_imports([module], {module.module}, {}, namespace="sample")
    resolve_reexports(imports, {module.module: module.all_exports}, [module])
    imports[0]["data"].pop(missing)
    bindings, classes = boundary_type_indexes([], imports)
    annotation = "Callable[[object], object]"
    verdict = _boundary_type_verdict(
        annotation,
        module.module,
        None,
        {},
        bindings,
        classes,
        type_shapes=collect_type_shapes([annotation]),
    )
    assert verdict.undecidable is not None
    assert not verdict.violations and verdict.violation is None
