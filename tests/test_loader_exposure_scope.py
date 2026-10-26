# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-273: a module's namespace exposure withholds loader proof in that module only."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_absent_import_namespace import _namespace_contract
from test_exact_module_ownership import _observe_tree

from archkeel.ir.decisions import rule_assessments

EXPOSURES = {
    "globals": "names = globals()\n",
    "globals_read": "keys = sorted(set(globals()))\n",
    "globals_alias": "grab = globals\nnames = grab()\n",
    "builtins_qualified": "import builtins\nnames = builtins.globals()\n",
    "eval": "value = eval('1 + 1')\n",
    "eval_from_builtins": "from builtins import eval as run\nvalue = run('1')\n",
    "exec": "exec('x = 1')\n",
    "exec_with_namespace": "scope = {}\nexec('x = 1', scope)\n",
    "annotations": "table = __annotations__\n",
    "type_hints": "from typing import get_type_hints\nhints = get_type_hints(int)\n",
    "extension_type_hints": (
        "from typing_extensions import get_type_hints\nhints = get_type_hints(int)\n"
    ),
    "inspect_annotations": "import inspect\nhints = inspect.get_annotations(int)\n",
    "inside_function": "def helper():\n    return globals()\n",
    "inside_class": "class Holder:\n    names = globals()\n",
}
LOADS = {
    "import_module": (
        "import importlib\n",
        'importlib.import_module("sample.retired.old")\n',
    ),
    "dunder_import": ("", '__import__("sample.retired.old")\n'),
    "from_import_alias": (
        "from importlib import import_module as load\n",
        'load("sample.retired.old")\n',
    ),
}
LOAD_FAMILY = {
    "import_module": "importlib",
    "dunder_import": "builtins",
    "from_import_alias": "importlib",
}
# A visible mutation of a loader changes that loader everywhere. Any exposure that is not the
# module's own namespace could reach every module, so it changes both loaders everywhere.
ESCAPES = {
    "assign_importlib": ("importlib", "import importlib\nimportlib.import_module = lambda n: n\n"),
    "pass_importlib": ("importlib", "import importlib\nmutate(importlib)\n"),
    "assign_builtins": ("builtins", "import builtins\nbuiltins.__import__ = lambda n: n\n"),
    "pass_builtins": ("builtins", "import builtins\nmutate(builtins)\n"),
    "store_builtins_item": ("both", '__builtins__["__import__"] = lambda *args: None\n'),
    "set_builtins_attribute": ("both", "__builtins__.__import__ = lambda *args: None\n"),
    "read_builtins": ("both", "table = __builtins__\n"),
    "frame_builtins": ("both", "import sys\nsys._getframe().f_builtins['x'] = 1\n"),
    "frame_globals": ("both", "import sys\nsys._getframe(1).f_globals['x'] = 1\n"),
    "frame_locals": ("both", "import sys\nsys._getframe(1).f_locals['x'] = 1\n"),
}


def _status(tmp_path: Path, caller: str, errors: str) -> tuple[str, bool]:
    contract = _namespace_contract()
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller/__init__.py": caller,
            "sample/errors/__init__.py": errors,
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.kind == "forbidden_dependency"
    ]
    return row.status, row.evaluation_proven


def _caller(load: str, exposure: str = "") -> str:
    header, call = LOADS[load]
    return f"{header}from sample.errors import marker\n{exposure}{call}"


@pytest.mark.parametrize("load", LOADS)
def test_a_literal_load_is_proven_when_no_module_exposes_a_namespace(
    tmp_path: Path, load: str
) -> None:
    assert _status(tmp_path, _caller(load), "marker = 1\n") == ("FAIL", True)


@pytest.mark.parametrize("load", LOADS)
@pytest.mark.parametrize("exposure", EXPOSURES)
def test_an_exposure_in_another_module_leaves_the_literal_load_proven(
    tmp_path: Path, exposure: str, load: str
) -> None:
    errors = EXPOSURES[exposure] + "marker = 1\n"
    assert _status(tmp_path, _caller(load), errors) == ("FAIL", True)


@pytest.mark.parametrize("load", LOADS)
@pytest.mark.parametrize("exposure", EXPOSURES)
def test_an_exposure_in_the_loading_module_withholds_its_own_proof(
    tmp_path: Path, exposure: str, load: str
) -> None:
    status, proven = _status(tmp_path, _caller(load, EXPOSURES[exposure]), "marker = 1\n")
    assert (status, proven) == ("UNKNOWN", False)


@pytest.mark.parametrize("load", LOADS)
@pytest.mark.parametrize("escape", ESCAPES)
def test_a_visible_loader_mutation_withholds_proof_of_its_own_loader_in_every_module(
    tmp_path: Path, escape: str, load: str
) -> None:
    family, body = ESCAPES[escape]
    expected = ("UNKNOWN", False) if family in {LOAD_FAMILY[load], "both"} else ("FAIL", True)
    assert _status(tmp_path, _caller(load), body + "marker = 1\n") == expected


def test_exposures_in_two_other_modules_do_not_add_up_to_a_global_escape(tmp_path: Path) -> None:
    contract = _namespace_contract()
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller/__init__.py": _caller("import_module"),
            "sample/errors/__init__.py": "exec('x = 1')\nmarker = 1\n",
            "sample/other.py": "names = globals()\nvalue = eval('2')\n",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.kind == "forbidden_dependency"
    ]
    assert (row.status, row.evaluation_proven) == ("FAIL", True)


def _mutations(tmp_path: Path, namespace: str, **modules: str):
    from archkeel.analyzer.python.imports import _loader_mutations
    from archkeel.analyzer.python.source import parse_sources

    package = tmp_path / namespace
    package.mkdir()
    (package / "__init__.py").write_text(modules.pop("init", ""))
    for name, source in modules.items():
        (package / f"{name}.py").write_text(source)
    parsed = parse_sources(sorted(package.rglob("*.py")), root=tmp_path, namespace=namespace)
    return _loader_mutations(parsed.modules, {})


BOTH = frozenset({"importlib.import_module", "builtins.__import__"})


@pytest.mark.parametrize("owner", ["importlib", "builtins"])
def test_a_scanned_loader_owner_changes_both_loaders_everywhere(tmp_path: Path, owner: str) -> None:
    changed, exposed = _mutations(tmp_path, owner, a="x = 1\n")
    assert (changed, exposed) == (BOTH, {})


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("table = __builtins__\n", set(BOTH)),
        ("import sys\nsys._getframe().f_builtins['x'] = 1\n", set(BOTH)),
        ("import sys\nsys._getframe(1).f_globals['x'] = 1\n", set(BOTH)),
        ("import sys\nsys._getframe(1).f_locals['x'] = 1\n", set(BOTH)),
        ("names = globals()\neval('1')\nexec('x = 1')\n", set()),
        ("import builtins\nbuiltins.exec('x = 1')\ntable = __annotations__\n", set()),
    ],
    ids=["__builtins__", "f_builtins", "f_globals", "f_locals", "own namespace", "qualified"],
)
def test_only_a_reach_into_another_namespace_changes_a_loader_everywhere(
    tmp_path: Path, body: str, expected: set[str]
) -> None:
    changed, _ = _mutations(tmp_path, "sample", a=body)
    assert changed == frozenset(expected)


def test_an_exposing_module_is_listed_by_name_and_changes_nothing_globally(tmp_path: Path) -> None:
    changed, exposed = _mutations(tmp_path, "sample", a="names = globals()\n", b="x = 1\n")
    assert changed == frozenset()
    assert exposed == {"sample.a": BOTH}


def test_an_exposure_that_is_not_listed_as_own_reaches_other_modules(tmp_path: Path) -> None:
    """Fail closed: a trigger nobody classified changes the loaders everywhere."""
    import ast

    from archkeel.analyzer.python.source import exposes_own_namespace_only, parse_sources

    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("mystery_namespace_access\n")
    module = parse_sources([package / "__init__.py"], root=tmp_path, namespace="sample").modules[0]
    name = next(
        node
        for node in module.all_nodes
        if isinstance(node, ast.Name) and node.id == "mystery_namespace_access"
    )
    assert exposes_own_namespace_only(module, name) is False
