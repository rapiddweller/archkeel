# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Unsupported inherited generic surfaces stay unproven."""

from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_inside_publication import _rule, _write_project

from archkeel.check.validation import interface_diagnostics
from archkeel.ir.codec import parse_contract


def _interface_result(tmp_path: Path, api: str, *, boundary_types: bool = False):
    components = [
        _component(
            "api",
            packages=["sample.api"],
            public=["sample.api:Child", "sample.api:Payload", "sample.api:Noise"],
        ),
        _component("client", packages=["sample.client"]),
    ]
    rules = [_rule("INTERFACE", "interface_boundary")]
    if boundary_types:
        rules.append(_rule("TYPES", "boundary_types", source="sample.api"))
    contract = {"schema_version": "2.1.0", "components": components, "rules": rules}
    _write_project(
        tmp_path,
        components=components,
        rules=rules,
        insides={},
        files={
            "sample/api.py": api,
            "sample/client.py": "from sample.api import Child\nVALUE = Child()\n",
        },
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    return (
        interface_diagnostics(parse_contract(contract), result.observation),
        result.observation,
    )


@pytest.mark.parametrize(
    "member",
    [
        "payload: T",
        "def __init__(self, payload: T) -> None: ...",
    ],
    ids=["inherited-field", "inherited-constructor"],
)
def test_inherited_field_and_constructor_type_remain_unknown(tmp_path: Path, member: str) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        f"    {member}\n"
        "class Child(Base[Payload]):\n"
        "    pass\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.usage_unknown", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


def test_conditional_override_does_not_publish_base_generic_return(tmp_path: Path) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    if True:\n"
        "        def get(self) -> int: ...\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.usage_unknown", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


def test_direct_non_method_override_does_not_publish_inherited_method_type(
    tmp_path: Path,
) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    get = None\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.unused", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


def test_annotation_only_override_does_not_hide_inherited_method(tmp_path: Path) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    get: object\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" in child.data.get("facade_types", ())


def test_base_class_binding_of_typevar_name_blocks_substitution(tmp_path: Path) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    T = int\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    pass\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.usage_unknown", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


def test_base_typevar_rebinding_after_method_keeps_candidate_unknown(tmp_path: Path) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "    T = int\n"
        "class Child(Base[Payload]):\n"
        "    pass\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.usage_unknown", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


def test_base_conditional_method_binding_withholds_generic_publication(tmp_path: Path) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "    if True:\n"
        "        get = None\n"
        "class Child(Base[Payload]):\n"
        "    pass\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.usage_unknown", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


@pytest.mark.parametrize(
    "replacement",
    [
        "    get = None\n",
        "    if True:\n        def get(self) -> int: ...\n",
    ],
    ids=["direct-assignment", "conditional-definition"],
)
def test_uncertain_base_method_binding_does_not_emit_definitive_type_violation(
    tmp_path: Path, replacement: str
) -> None:
    _, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> dict: ...\n"
        f"{replacement}"
        "class Child(Base[Payload]):\n"
        "    pass\n",
        boundary_types=True,
    )

    assert observation.records("violations") == ()
    assert any(
        item.kind == "boundary_type_position"
        and item.data.get("qualified_name") == "sample.api.Child.__inherited_methods__"
        and item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )


def test_class_import_binding_shadows_inherited_method(tmp_path: Path) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    from builtins import int as get\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.unused", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


def test_deleted_base_method_does_not_publish_generic_return(tmp_path: Path) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "    del get\n"
        "class Child(Base[Payload]):\n"
        "    pass\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.usage_unknown", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


def test_deleted_child_override_keeps_inherited_candidate_unknown(tmp_path: Path) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    get = None\n"
        "    del get\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.usage_unknown", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


@pytest.mark.parametrize(
    "statement", ["(get := int)", "x = (get := int)"], ids=["expression", "assignment-value"]
)
def test_class_body_walrus_keeps_inherited_generic_candidate_unknown(
    tmp_path: Path, statement: str
) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        f"    {statement}\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.usage_unknown", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


@pytest.mark.parametrize(
    "definition",
    [
        "    def helper(self, arg=(get := int)): ...\n",
        "    @(get := lambda function: function)\n    def helper(self): ...\n",
    ],
    ids=["default-argument", "decorator"],
)
def test_definition_time_walrus_keeps_inherited_candidate_unknown(
    tmp_path: Path, definition: str
) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        f"{definition}",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.usage_unknown", "sample.api:Payload"),
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" not in child.data.get("facade_types", ())


def test_unused_second_generic_argument_stays_unused(tmp_path: Path) -> None:
    diagnostics, observation = _interface_result(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "U = TypeVar('U')\n"
        "class Payload: pass\n"
        "class Noise: pass\n"
        "class Base(Generic[T, U]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload, Noise]):\n"
        "    pass\n",
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.unused", "sample.api:Noise"),
    ]
    child = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
    )
    assert "sample.api.Payload" in child.data.get("facade_types", ())
    assert "sample.api.Noise" not in child.data.get("facade_types", ())
