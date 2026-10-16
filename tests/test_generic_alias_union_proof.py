# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native union expressions retain only proven builtin GenericAlias providers."""

from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_type_opaque_map_values import _app

from archkeel.ir.trace import trace_valid_violations

_OWNERSHIP = "tuple[str, tuple[str, ...], tuple[str, ...]]"


def _repository(root: Path, *, imported=True, provider=None, suffix="", prefix=""):
    provider = provider or f"Ownership = {_OWNERSHIP}\n"
    source = (
        "from __future__ import annotations\n"
        + prefix
        + ("from .types import Ownership\n" if imported else provider)
        + "PackageOwnership = tuple[str, tuple[str, ...]]\n"
        + "Compatible = Ownership | PackageOwnership\n"
        + suffix
        + "def select(owners: tuple[Ownership, ...]) -> bool:\n    return bool(owners)\n"
    )
    _app(root, source=source, declared=("sample.app.impl:select",))
    (root / "sample/app/types.py").write_text(provider)
    result = _observe(root)
    assert result.observation is not None and not result.diagnostics
    return result.observation


def _position_unknowns(model):
    return [
        row for row in model.records("unknowns")
        if row.kind == "boundary_type_position"
        and row.data.get("qualified_name") == "sample.app.impl.select"
    ]


@pytest.mark.parametrize("imported", [False, True])
def test_native_builtin_alias_union_keeps_the_alias_shape_proven(tmp_path, imported):
    model = _repository(tmp_path, imported=imported)
    assert not _position_unknowns(model)
    assert not trace_valid_violations(model)
    aliases = [
        row for row in model.records("symbols")
        if row.kind == "type_alias" and row.data.get("name") == "Ownership"
    ]
    assert aliases and all(row.data.get("source_member_binding_static") is True for row in aliases)


@pytest.mark.parametrize(
    "mutation",
    ["custom_operator", "custom_subscript", "shadowed_container", "rebound_provider",
     "conditional_provider", "unknown_escape", "import_rebind", "provider_namespace_write"],
)
def test_native_unsafe_union_operands_do_not_gain_builtin_proof(tmp_path, mutation):
    provider = f"Ownership = {_OWNERSHIP}\n"
    suffix = ""
    if mutation == "custom_operator":
        provider = (
            "class Meta(type):\n    def __or__(cls, other):\n        return other\n"
            "class Ownership(metaclass=Meta):\n    pass\n"
        )
    elif mutation == "custom_subscript":
        provider = (
            "class Meta(type):\n    def __getitem__(cls, value):\n        return value\n"
            "class Custom(metaclass=Meta):\n    pass\nOwnership = Custom[str]\n"
        )
    elif mutation == "shadowed_container":
        provider = "tuple = Unknown\n" + provider
    elif mutation == "rebound_provider":
        provider += "Ownership = Unknown\n"
    elif mutation == "conditional_provider":
        provider = "if condition:\n    " + provider
    elif mutation == "unknown_escape":
        suffix = "unknown(Ownership)\n"
    elif mutation == "import_rebind":
        suffix = "Ownership = Unknown\n"
    else:
        suffix = "from . import types\ntypes.Ownership = Unknown\n"
    model = _repository(tmp_path, provider=provider, suffix=suffix)
    assert _position_unknowns(model) or trace_valid_violations(model)


@pytest.mark.parametrize("container", ["tuple", "list", "dict", "set", "frozenset"])
def test_native_builtin_generic_alias_heads_are_read_only_union_operands(tmp_path, container):
    body = f"{container}[str, int]" if container == "dict" else f"{container}[str]"
    model = _repository(tmp_path, provider=f"Ownership = {body}\n")
    alias = next(
        row for row in model.records("symbols")
        if row.kind == "type_alias" and row.data.get("qualified_name") == "sample.app.types.Ownership"
    )
    assert alias.data.get("source_member_binding_static") is True
    assert not _position_unknowns(model)
