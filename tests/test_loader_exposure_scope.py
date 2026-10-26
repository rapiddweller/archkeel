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
    "eval": "value = eval('1 + 1')\n",
    "exec": "exec('x = 1')\n",
    "exec_with_namespace": "scope = {}\nexec('x = 1', scope)\n",
    "builtins_name": "table = __builtins__\n",
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
# Visible mutation of a loader is a real escape: it withholds proof of that loader in every module.
ESCAPES = {
    "assign_importlib": ("importlib", "import importlib\nimportlib.import_module = lambda n: n\n"),
    "pass_importlib": ("importlib", "import importlib\nmutate(importlib)\n"),
    "assign_builtins": ("builtins", "import builtins\nbuiltins.__import__ = lambda n: n\n"),
    "pass_builtins": ("builtins", "import builtins\nmutate(builtins)\n"),
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
    expected = ("UNKNOWN", False) if family == LOAD_FAMILY[load] else ("FAIL", True)
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


def test_an_exposing_module_is_listed_by_name_and_changes_nothing_globally(tmp_path: Path) -> None:
    changed, exposed = _mutations(tmp_path, "sample", a="names = globals()\n", b="x = 1\n")
    assert changed == frozenset()
    assert exposed == {"sample.a": BOTH}
