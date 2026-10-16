# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Binding controls use owned types; native source observations remain explicitly scoped."""

import ast
from enum import Enum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_analyzer import _observe_one_rule, _parsed_module

from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.scopes import LexicalScopes, NameBinding
from archkeel.analyzer.python.source import AliasBinding
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
CONTROL_FUNCTIONS = [
    ("source.py", "_member_binding_roots"),
    ("scopes.py", "LexicalScopes._owner"),
    ("resolve.py", "call_result_type"),
    ("resolve.py", "_resolve_name_node"),
    ("resolve.py", "_resolve_dotted"),
    ("calls.py", "_value_receiver_type"),
]


@pytest.mark.parametrize("api", [AliasBinding, NameBinding])
def test_binding_api_kind_annotation_is_nominal(api):
    annotation = get_type_hints(api)["kind"]
    assert isinstance(annotation, type) and issubclass(annotation, Enum), annotation


@pytest.mark.parametrize("name", ["engine", "Name"])
def test_import_collection_and_lexical_lookup_produce_nominal_kinds(name):
    module = _parsed_module(
        "import sample.engine as engine\nfrom sample.engine import Name\nengine\nName\n"
    )
    collect_imports([module], {"sample.engine"}, {}, namespace="sample")
    assert isinstance(module.aliases[name].kind, Enum)
    use = next(
        node for node in ast.walk(module.tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id == name
    )
    assert isinstance(LexicalScopes(module).lookup(use, name).kind, Enum)


@pytest.mark.parametrize("filename,qualified_scope", CONTROL_FUNCTIONS)
def test_actual_binding_control_functions_have_no_raw_dispatch(
    tmp_path, filename, qualified_scope
):
    # These six function observations do not certify their complete source modules.
    source = (ROOT / "src/archkeel/analyzer/python" / filename).read_text()
    owner = f"sample.core.{qualified_scope}"
    result = _observe_one_rule(
        tmp_path,
        {"kind": "forbidden_construct", "source": owner,
         "constructs": ["string_literal_compare"]},
        {"core.py": source},
    )
    assert result.diagnostics == () and result.observation is not None
    observed = [
        row for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare" and row.data.get("owner") == owner
    ]
    assert observed == [], [(row.title, row.evidence_ids) for row in observed]
    assert trace_valid_violations(result.observation) == ()
