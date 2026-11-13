# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Literal dynamic dependencies obey the same target policy as static imports."""

import pytest
from test_absent_import_namespace import _observe_namespace

from archkeel.ir.decisions import rule_assessments


@pytest.mark.parametrize(
    "body, expected",
    [
        ('import importlib\nimportlib.import_module("sample.retired.old")\n', "FAIL"),
        ('import importlib as loader\nloader.import_module("sample.retired.old")\n', "FAIL"),
        ('from importlib import import_module as load\nload("sample.retired.old")\n', "FAIL"),
        ('__import__("sample.retired.old")\n', "FAIL"),
        ('import importlib\nimportlib.import_module(".retired.old", package="sample")\n', "FAIL"),
        ('import importlib\nimportlib.import_module(name="sample.retired.old")\n', "FAIL"),
        ('import importlib\nimportlib.import_module("sample.errors")\n', "PASS"),
        ("import importlib\ndef run(name):\n    return importlib.import_module(name)\n", "UNKNOWN"),
        (
            "from importlib import import_module\n"
            "def import_module(name):\n    return name\n"
            'import_module("sample.retired.old")\n',
            "UNKNOWN",
        ),
    ],
)
@pytest.mark.parametrize("mounted", [False, True])
def test_native_dynamic_dependency_policy(tmp_path, body, expected, mounted):
    result = _observe_namespace(tmp_path, body, mounted=mounted)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected, row
    if expected != "UNKNOWN":
        assert row.evaluation_proven
    findings = result.observation.records("violations") or ()
    if expected == "FAIL":
        assert all(item.rule_ids and item.fact_ids and item.evidence_ids for item in findings)


@pytest.mark.parametrize(
    "body, expected",
    [
        ('from builtins import __import__ as load\nload("sample.retired.old")\n', "FAIL"),
        ('import importlib\nimportlib.import_module(".old", package=package)\n', "UNKNOWN"),
        ('import importlib\nimportlib.import_module("sample.retired." + name)\n', "UNKNOWN"),
        (
            "import importlib\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
            '    importlib.import_module("sample.retired.old")\n',
            "PASS",
        ),
        (
            "from importlib import import_module as load\ndef other(name):\n    return name\n"
            'load = other\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "from importlib import import_module as load\ndef other(name):\n    return name\n"
            'if condition:\n    load = other\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
    ],
)
def test_loader_proof_limits(tmp_path, body, expected):
    result = _observe_namespace(tmp_path, body, include_type_checking=False)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected, row


@pytest.mark.parametrize(
    "setup, expected",
    [
        ("", "FAIL"),
        ("    importlib.import_module = lambda name: name\n", "UNKNOWN"),
        ("    mutate(importlib)\n", "UNKNOWN"),
    ],
)
def test_local_loader_requires_unchanged_members(tmp_path, setup, expected):
    result = _observe_namespace(
        tmp_path,
        "def run():\n    import importlib\n"
        + setup
        + '    return importlib.import_module("sample.retired.old")\n',
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected


@pytest.mark.parametrize(
    "body, expected",
    [
        (
            "import importlib\ndef other(importlib):\n    mutate(importlib)\n"
            'importlib.import_module("sample.retired.old")\n',
            "FAIL",
        ),
        (
            "import builtins\nbuiltins.__import__ = lambda name: name\n"
            '__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "import importlib\nother = importlib\nother.import_module = lambda name: name\n"
            'importlib.import_module("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "import importlib\nimportlib.import_module = lambda name: name\n"
            'from importlib import import_module as load\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "import importlib\ndef mutate_loader():\n    import importlib as other\n"
            "    other.import_module = lambda name: name\nmutate_loader()\n"
            'importlib.import_module("sample.retired.old")\n',
            "UNKNOWN",
        ),
    ],
)
def test_loader_mutations_use_import_identity_instead_of_spelling(tmp_path, body, expected):
    result = _observe_namespace(tmp_path, body)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected


@pytest.mark.parametrize(
    "mutation", ["importlib.import_module = lambda name: name\n", "mutate(importlib)\n"]
)
def test_loader_mutation_in_another_scanned_module_withholds_proof(tmp_path, mutation):
    from test_absent_import_namespace import _namespace_contract
    from test_exact_module_ownership import _observe_tree

    contract = _namespace_contract()
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller/__init__.py": "import importlib\nfrom sample.errors import marker\n"
            'importlib.import_module("sample.retired.old")\n',
            "sample/errors/__init__.py": "import importlib\n" + mutation + "marker = 1\n",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize(
    "provider, caller",
    [
        ("import importlib as route\n", "route.import_module = lambda name: name\n"),
        ("from importlib import import_module as route\n", "mutate(route)\n"),
        ("import importlib as route\n", 'route.import_module("sample.retired.old")\n'),
        ("from importlib import import_module as route\n", 'route("sample.retired.old")\n'),
    ],
)
def test_reexported_loader_identity_cannot_authorize_a_false_proof(tmp_path, provider, caller):
    from test_absent_import_namespace import _namespace_contract
    from test_exact_module_ownership import _observe_tree

    contract = _namespace_contract()
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller/__init__.py": "import importlib\nfrom sample.errors import route\n"
            + caller
            + 'importlib.import_module("sample.retired.old")\n',
            "sample/errors/__init__.py": provider,
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    if "lambda" in caller or "mutate" in caller:
        assert row.status == "UNKNOWN" and not row.evaluation_proven
    else:
        assert (
            row.status == "FAIL"
        )  # The known direct violation survives the unproved reexport call.
        assert any(
            r.kind == "dynamic_dependency_limit"
            for r in result.observation.records("unknowns") or ()
        )


@pytest.mark.parametrize(
    "body, expected",
    [
        (
            'if condition:\n    __import__ = lambda name: name\n__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "if condition:\n    def __import__(name): return name\n"
            '__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "if condition:\n    __import__ = lambda name: name\n"
            'load = __import__\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__ = lambda name: name\ndel __import__\n__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "def shadow():\n    global __import__\n"
            "    if condition:\n        __import__ = lambda name: name\n"
            '__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "class X:\n    if flag:\n        __import__ = lambda name: name\n"
            '    __import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "__import__ = lambda name: name\n"
            "class X:\n    if flag:\n        __import__ = lambda name: name\n"
            '    __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            'class X:\n    __import__ = lambda name: name\n    __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def outer():\n    __import__ = lambda name: name\n"
            "    class C:\n        if flag:\n            __import__ = lambda name: name\n"
            '        __import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "def outer():\n    __import__ = lambda name: name\n"
            '    class C:\n        __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def outer():\n    __import__ = lambda name: name\n"
            "    class C:\n        nonlocal __import__\n"
            "        if flag:\n            __import__ = lambda name: name\n"
            '        __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            '__import__("sample.retired.old")\n__import__ = lambda name: name\n',
            "UNKNOWN",
        ),
        (
            'load = __import__\n__import__ = lambda name: name\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__ = __import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__ = lambda name: name; __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            '__import__("sample.retired.old"); __import__ = lambda name: name\n',
            "UNKNOWN",
        ),
        (
            'def run():\n    __import__("sample.retired.old")\n'
            "    __import__ = lambda name: name\n",
            "PASS",
        ),
        (
            'class C:\n    __import__ = __import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "__import__ = lambda name: name\n"
            'class C:\n    __import__ = __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def shadow():\n    global __import__\n    __import__ = lambda name: name\n"
            '__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__: object\n__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__ = lambda name: name\n__import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def run():\n    if condition:\n        __import__ = lambda name: name\n"
            '    return __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def outer():\n    if condition:\n        __import__ = lambda name: name\n"
            "    def run():\n        nonlocal __import__\n"
            '        return __import__("sample.retired.old")\n',
            "PASS",
        ),
    ],
)
def test_builtin_import_fallback_respects_lexical_owner(tmp_path, body, expected):
    result = _observe_namespace(tmp_path, body)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected, row
    assert row.evaluation_proven is (expected == "PASS")
    assert any(
        item.kind == "dynamic_dependency_limit"
        for item in result.observation.records("unknowns") or ()
    ) is (expected == "UNKNOWN")
