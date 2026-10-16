# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Binding controls use owned types; native source observations remain explicitly scoped."""

import ast
import copy
import json
from enum import Enum
from pathlib import Path
from typing import get_type_hints
from unittest.mock import patch

import pytest
from test_analyzer import _observe_one_rule, _parsed_module
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.analyzer.python.binding_types import (
    AliasBinding as OwnedAliasBinding,
)
from archkeel.analyzer.python.binding_types import (
    BindingKind,
    CompilerScopeKind,
    ImportKind,
    compiler_scope_kind,
)
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.scopes import LexicalScopes, NameBinding
from archkeel.analyzer.python.source import AliasBinding
from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
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


@pytest.mark.parametrize("api,expected", [(AliasBinding, ImportKind), (NameBinding, BindingKind)])
def test_binding_api_kind_annotation_is_nominal(api, expected):
    annotation = get_type_hints(api)["kind"]
    assert annotation is expected and issubclass(annotation, Enum), annotation


@pytest.mark.parametrize("name", ["engine", "Name"])
def test_import_collection_and_lexical_lookup_produce_nominal_kinds(name):
    module = _parsed_module(
        "import sample.engine as engine\nfrom sample.engine import Name\nengine\nName\n"
    )
    collect_imports([module], {"sample.engine"}, {}, namespace="sample")
    expected_import = ImportKind.MODULE if name == "engine" else ImportKind.SYMBOL
    assert module.aliases[name].kind is expected_import
    use = next(
        node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id == name
    )
    expected_lexical = BindingKind.MODULE if name == "engine" else BindingKind.SYMBOL
    assert LexicalScopes(module).lookup(use, name).kind is expected_lexical


@pytest.mark.parametrize("filename,qualified_scope", CONTROL_FUNCTIONS)
def test_actual_binding_control_functions_have_no_raw_dispatch(tmp_path, filename, qualified_scope):
    # The module is observed in full; unrelated raw grammars may still fail its rule.
    # Only these six function observations are asserted, without a module PASS claim.
    source = (ROOT / "src/archkeel/analyzer/python" / filename).read_text()
    owner = f"sample.core.{qualified_scope}"
    result = _observe_one_rule(
        tmp_path,
        {
            "kind": "forbidden_construct",
            "source": "sample.core",
            "constructs": ["string_literal_compare"],
        },
        {"core.py": source},
    )
    assert result.diagnostics == () and result.observation is not None
    observed = [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare" and row.data.get("owner") == owner
    ]
    assert observed == [], [(row.title, row.evidence_ids) for row in observed]
    assert not [row for row in trace_valid_violations(result.observation) if owner in row.subjects]


def test_unknown_compiler_scope_kind_cannot_authorize_module_fallback():
    module = _parsed_module(
        "def outer():\n    captured = 1\n"
        "    def inner():\n        return captured\n    return inner\n"
    )
    scopes = LexicalScopes(module)
    use = next(
        node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id == "captured"
    )
    parent = scopes.by_node[use].parent
    assert parent is not None and parent.table is not None
    with patch.object(parent.table, "get_type", return_value="future compiler scope"):
        binding = scopes.lookup(use, use.id)
    assert binding.owner is None


def test_binding_types_are_nominal_and_existing_source_port_is_retained():
    assert AliasBinding is OwnedAliasBinding
    assert ImportKind.MODULE != "module"
    assert BindingKind.MODULE != "module"
    assert ImportKind.MODULE is not BindingKind.MODULE


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("module", CompilerScopeKind.MODULE),
        ("function", CompilerScopeKind.FUNCTION),
        ("class", CompilerScopeKind.CLASS),
        ("annotation", None),
        ("future scope", None),
        ("FUNCTION", None),
        ("", None),
    ],
)
def test_compiler_protocol_classification_preserves_unknown(raw, expected):
    assert compiler_scope_kind(raw) is expected


def _binding_contract():
    contract = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/python.json").read_text())
    )
    contract.pop("$schema", None)
    root = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [
        rule for rule in root["rules"] if rule["id"] == "PYTHON-BINDINGS-TYPED-CONTROL"
    ]
    contract["declarations"]["uml"]["entities"] = [
        entity
        for entity in contract["declarations"]["uml"]["entities"]
        if entity["id"].startswith("PYTHON-BINDING-")
    ]
    return contract


def _binding_repository(tmp_path):
    files = {
        "archkeel/__init__.py": "",
        "archkeel/analyzer/__init__.py": "",
        "archkeel/analyzer/python/__init__.py": "",
        "contract.json": json.dumps(_binding_contract()),
        "docs/architecture/typed-python-bindings.md": "Owned Python binding types.\n",
    }
    for filename in ("binding_types.py", "scopes.py", "source.py"):
        relative = f"archkeel/analyzer/python/{filename}"
        files[relative] = (ROOT / "src" / relative).read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _binding_comparison(model):
    comparison = architecture_report(model).comparison
    assert comparison is not None
    return comparison


def test_native_binding_api_matches_owned_target_and_model_guard(tmp_path):
    root, config = _binding_repository(tmp_path)
    model = _model(root, config)
    assert _binding_comparison(model).status == "PASS", _binding_comparison(model)
    assessment = next(
        row
        for row in rule_assessments(model, undecided_by_rule={})
        if row.id == "PYTHON-BINDINGS-TYPED-CONTROL"
    )
    assert assessment.status == "PASS" and assessment.evaluation_proven
    assert not trace_valid_violations(model)


@pytest.mark.parametrize(
    "filename,annotation",
    [("binding_types.py", "kind: ImportKind"), ("scopes.py", "kind: BindingKind")],
)
def test_native_binding_kind_widening_fails_unchanged_target(tmp_path, filename, annotation):
    root, config = _binding_repository(tmp_path)
    path = root / "archkeel/analyzer/python" / filename
    source = path.read_text()
    assert annotation in source
    path.write_text(source.replace(annotation, "kind: str", 1))
    contract = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assert any(
        row.aspect == "annotation" and row.status == "FAIL"
        for row in _binding_comparison(model).assessments
    )
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == contract


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "module"\n',
        'def _probe(value):\n    return value in ("module", "symbol")\n',
        "def _probe(value):\n    return value == ImportKind.MODULE.value\n",
    ],
    ids=["raw-equality", "raw-membership", "enum-value-extraction"],
)
def test_native_binding_model_rejects_raw_dispatch(tmp_path, probe):
    root, config = _binding_repository(tmp_path)
    path = root / "archkeel/analyzer/python/binding_types.py"
    path.write_text(path.read_text() + "\n" + probe)
    model = _model(root, config)
    assert [
        row
        for row in trace_valid_violations(model)
        if "PYTHON-BINDINGS-TYPED-CONTROL" in row.rule_ids
    ]


def test_actual_complete_binding_model_has_positive_native_guard(self_observation):
    assessment = next(
        row
        for row in rule_assessments(self_observation, undecided_by_rule={})
        if row.id == "PYTHON-BINDINGS-TYPED-CONTROL"
    )
    assert assessment.status == "PASS" and assessment.evaluation_proven


@pytest.mark.parametrize("kind", list(ImportKind))
def test_alias_binding_normalizes_valid_legacy_constructor_kind(kind):
    binding = AliasBinding("sample.engine", kind.value, "Engine")
    assert binding.kind is kind
    assert binding.target == "sample.engine" and binding.imported_name == "Engine"


@pytest.mark.parametrize("kind", list(BindingKind))
def test_name_binding_normalizes_valid_legacy_constructor_kind(kind):
    binding = NameBinding(None, ("sample.engine",), kind.value, True)
    assert binding.kind is kind
    assert binding.owner is None and binding.targets == ("sample.engine",) and binding.uncertain


@pytest.mark.parametrize("kind", list(ImportKind))
def test_legacy_alias_constructor_preserves_real_lexical_lookup(kind):
    module = _parsed_module("import sample.engine as engine\nengine\n")
    collect_imports([module], {"sample.engine"}, {}, namespace="sample")
    __site, aliases = next(iter(module.import_aliases.items()))
    aliases["engine"] = AliasBinding("sample.engine", kind.value)
    use = next(
        node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id == "engine"
    )
    expected = BindingKind.MODULE if kind is ImportKind.MODULE else BindingKind.SYMBOL
    assert LexicalScopes(module).lookup(use, "engine").kind is expected


@pytest.mark.parametrize("kind", list(ImportKind))
def test_alias_binding_preserves_nominal_constructor_identity(kind):
    assert AliasBinding("sample.engine", kind).kind is kind


@pytest.mark.parametrize("kind", list(BindingKind))
def test_name_binding_preserves_nominal_constructor_identity(kind):
    assert NameBinding(None, kind=kind).kind is kind


def test_name_binding_default_remains_nominal_unknown():
    assert NameBinding(None).kind is BindingKind.UNKNOWN


@pytest.mark.parametrize("raw", ["", "future kind", None, 7])
@pytest.mark.parametrize("api,args", [(AliasBinding, ("sample.engine",)), (NameBinding, (None,))])
def test_binding_constructor_rejects_invalid_kind(api, args, raw):
    with pytest.raises(ValueError):
        api(*args, kind=raw)
