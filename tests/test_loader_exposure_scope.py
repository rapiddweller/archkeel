# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-273: a module's namespace exposure withholds loader proof in that module only.

AD-275: a `globals()` that only reads names keeps the module's direct bindings stable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_absent_import_namespace import _namespace_contract
from test_exact_module_ownership import _observe_tree

from archkeel.ir.decisions import rule_assessments

# The module's own namespace: `eval`, `exec` and annotations. The code they run is not proved
# (AD-240), so they withhold proof in their own module and nowhere else.
EXPOSURES = {
    "eval": "value = eval('1 + 1')\n",
    "eval_from_builtins": "from builtins import eval as run\nvalue = run('1')\n",
    "exec": "exec('x = 1')\n",
    "exec_qualified": "import builtins\nbuiltins.exec('x = 1')\n",
    "exec_with_namespace": "scope = {}\nexec('x = 1', scope)\n",
    "annotations": "table = __annotations__\n",
    "type_hints": "from typing import get_type_hints\nhints = get_type_hints(int)\n",
    "extension_type_hints": (
        "from typing_extensions import get_type_hints\nhints = get_type_hints(int)\n"
    ),
    "inspect_annotations": "import inspect\nhints = inspect.get_annotations(int)\n",
    "inside_function": "def helper():\n    return eval('1')\n",
    "inside_class": "class Holder:\n    value = eval('1')\n",
}
# `globals()` that only reads the names of the module reaches no shared object: no exposure.
NAMES_ONLY = {
    "set": "keys = set(globals())\n",
    "sorted_keys": "keys = sorted(globals().keys())\n",
    "membership": "known = 'x' in globals()\n",
    "length": "size = len(globals())\n",
    "iteration": "for name in globals():\n    pass\n",
    "comprehension": "keys = [name for name in globals()]\n",
    "inside_function": "def names():\n    return sorted(set(globals()))\n",
    "not_in": "missing = 'x' not in globals()\n",
    "union": "keys = sorted(set(globals()) | set(['x']))\n",
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
    "inside_function": (
        "from importlib import import_module\n",
        'def load():\n    return import_module("sample.retired.old")\n',
    ),
}
LOAD_FAMILY = {
    "import_module": "importlib",
    "dunder_import": "builtins",
    "from_import_alias": "importlib",
    "inside_function": "importlib",
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
    # The dict of `globals()` holds references to shared objects such as `importlib`.
    "globals_subscript_mutation": (
        "both",
        "import importlib\nglobals()['importlib'].import_module = lambda *a, **k: None\n",
    ),
    "globals_variable": ("both", "names = globals()\n"),
    "globals_get": ("both", "item = globals().get('x')\n"),
    "globals_copy": ("both", "copy = dict(globals())\n"),
    "globals_items": ("both", "pairs = list(globals().items())\n"),
    "globals_alias": ("both", "grab = globals\nnames = grab()\n"),
    "globals_store": ("both", "globals()['x'] = 1\n"),
    "globals_passed_on": ("both", "def use(namespace): ...\nuse(globals())\n"),
    "builtins_globals_qualified": ("both", "import builtins\nnames = builtins.globals()\n"),
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
@pytest.mark.parametrize("names_only", NAMES_ONLY)
def test_reading_the_names_of_globals_in_another_module_exposes_nothing(
    tmp_path: Path, names_only: str, load: str
) -> None:
    errors = NAMES_ONLY[names_only] + "marker = 1\n"
    assert _status(tmp_path, _caller(load), errors) == ("FAIL", True)


@pytest.mark.parametrize("load", LOADS)
@pytest.mark.parametrize("names_only", NAMES_ONLY)
def test_reading_the_names_of_globals_in_the_loading_module_changes_no_loader(
    tmp_path: Path, names_only: str, load: str
) -> None:
    # AD-275: the read also keeps the loader binding of the module stable.
    code = NAMES_ONLY[names_only]
    assert _status(tmp_path, _caller(load, code), "marker = 1\n") == ("FAIL", True)


def test_a_lazy_package_that_lists_its_names_keeps_the_literal_load_proven(
    tmp_path: Path,
) -> None:
    """The shape measured on DATAMIMIC EE (internal): a lazy package `__init__` with `__dir__`."""
    caller = (
        "from importlib import import_module\n"
        "from sample.errors import marker\n"
        "def _load():\n"
        '    return import_module("sample.retired.old")\n'
        "def __getattr__(name):\n"
        "    return getattr(_load(), name)\n"
        "def __dir__():\n"
        "    return sorted(set(globals()) | set(marker.__all__))\n"
    )
    assert _status(tmp_path, caller, "marker = 1\n") == ("FAIL", True)


# A loader binding that is not bound once at module level stays unproven with a names-only read.
UNSTABLE_LOADERS = {
    "try": "try:\n    import importlib\nexcept ImportError:\n    importlib = None\n",
    "if": "if marker:\n    import importlib\n",
    "rebound": "import importlib\nimportlib = importlib\n",
    "deleted": "import importlib\ndel importlib\nimport importlib\n",
    "global_rebind": "import importlib\ndef swap():\n    global importlib\n    importlib = None\n",
}


@pytest.mark.parametrize("binding", UNSTABLE_LOADERS)
def test_reading_the_names_of_globals_does_not_prove_an_unstable_loader_binding(
    tmp_path: Path, binding: str
) -> None:
    caller = (
        "from sample.errors import marker\n"
        + UNSTABLE_LOADERS[binding]
        + "keys = set(globals())\n"
        + 'importlib.import_module("sample.retired.old")\n'
    )
    assert _status(tmp_path, caller, "marker = 1\n") == ("UNKNOWN", False)


# `locals()` and `vars()` at module level are the module's dict: still an exposure (fail closed).
MODULE_NAMESPACE_READS = {
    "vars_of_object": "names = vars(marker)\n",
    "vars": "keys = set(vars())\n",
    "locals": "keys = set(locals())\n",
}


@pytest.mark.parametrize("load", LOADS)
@pytest.mark.parametrize("read", MODULE_NAMESPACE_READS)
def test_locals_and_vars_at_module_level_keep_the_loader_binding_unstable(
    tmp_path: Path, read: str, load: str
) -> None:
    expected = ("FAIL", True) if LOAD_FAMILY[load] == "builtins" else ("UNKNOWN", False)
    code = MODULE_NAMESPACE_READS[read]
    assert _status(tmp_path, _caller(load, code), "marker = 1\n") == expected


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
            "sample/other.py": "keys = set(globals())\nvalue = eval('2')\n",
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
        ("eval('1')\nexec('x = 1')\n", set()),
        ("names = globals()\n", set(BOTH)),
        ("keys = set(globals())\n", set()),
        ("import builtins\nbuiltins.exec('x = 1')\ntable = __annotations__\n", set()),
    ],
    ids=[
        "__builtins__",
        "f_builtins",
        "f_globals",
        "f_locals",
        "eval and exec",
        "globals as a dict",
        "globals names only",
        "qualified",
    ],
)
def test_only_a_reach_into_another_namespace_changes_a_loader_everywhere(
    tmp_path: Path, body: str, expected: set[str]
) -> None:
    changed, _ = _mutations(tmp_path, "sample", a=body)
    assert changed == frozenset(expected)


def test_an_exposing_module_is_listed_by_name_and_changes_nothing_globally(tmp_path: Path) -> None:
    changed, exposed = _mutations(tmp_path, "sample", a="value = eval('1')\n", b="x = 1\n")
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


READS = {
    "set(globals())": True,
    "frozenset(globals())": True,
    "sorted(globals())": True,
    "list(globals())": True,
    "tuple(globals())": True,
    "sorted(set(globals()))": True,
    "list(globals().keys())": True,
    "'x' in globals()": True,
    "'x' not in globals()": True,
    "len(globals())": True,
    "[k for k in globals()]": True,
    "for k in globals(): pass": True,
    "g = globals()": False,
    "globals()['importlib']": False,
    "globals().get('x')": False,
    "dict(globals())": False,
    "list(globals().items())": False,
    "list(globals().values())": False,
    "f(globals())": False,
    "globals().update(x=1)": False,
    "globals()['a'] = 1": False,
    "x == globals()": False,
    "globals() in x": False,
    "f = globals().keys": False,
    "sorted([], key=globals())": False,
    "[k for k in x if globals()]": False,
    "globals()(1)": False,
    "x in globals() == y": False,
    "set(globals().keys())": True,
    "'x' in globals().keys()": True,
    "for k in globals().keys(): pass": True,
    "sorted(globals(), key=len)": True,
    "k = globals().keys()": False,
    "globals().keys().mapping['importlib']": False,
    "globals().keys() & x": False,
    "set(x, globals())": False,
    "def set(ns): pass\nset(globals())": False,
    "set = f\nset(globals())": False,
    "import set\nset(globals())": False,
    "from m import sorted\nsorted(globals())": False,
    "class list: pass\nlist(globals())": False,
    "def f(len): return len(globals())": False,
    "builtins.set(globals())": False,
}


@pytest.mark.parametrize("source", READS)
def test_which_uses_of_globals_only_read_its_names(tmp_path: Path, source: str) -> None:
    import ast

    from archkeel.analyzer.python.source import parse_sources, reads_only_namespace_names

    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text(f"{source}\n")
    module = parse_sources([package / "__init__.py"], root=tmp_path, namespace="sample").modules[0]
    parents = {
        child: parent for parent in ast.walk(module.tree) for child in ast.iter_child_nodes(parent)
    }
    calls = [
        node
        for node in module.all_nodes
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "globals"
    ]
    assert calls
    assert all(reads_only_namespace_names(module, call, parents) for call in calls) is READS[source]


def _module(tmp_path: Path, source: str):
    from archkeel.analyzer.python.source import parse_sources

    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text(source)
    return parse_sources([package / "__init__.py"], root=tmp_path, namespace="sample").modules[0]


@pytest.mark.parametrize("source", READS)
def test_only_a_names_only_globals_keeps_the_direct_bindings_stable(
    tmp_path: Path, source: str
) -> None:
    from archkeel.analyzer.python.source import stable_direct_module_bindings

    module = _module(tmp_path, f"import importlib\n{source}\n")
    assert ("importlib" in stable_direct_module_bindings(module)) is READS[source]


@pytest.mark.parametrize(
    ("read", "stable"),
    [
        ("keys = set(globals())\n", True),
        ("names = globals()\n", False),
        ("names = vars(importlib)\n", False),
        ("keys = set(locals())\n", False),
        ('__import__("json")\n', False),
    ],
)
def test_an_overload_group_stays_static_beside_a_names_only_globals(
    read: str, stable: bool
) -> None:
    from test_analyzer import _parsed_module
    from test_boundary_types_reexport_proofs import _OVERLOAD_GROUP

    from archkeel.analyzer.python.imports import collect_imports
    from archkeel.analyzer.python.source import static_overload_bindings

    module = _parsed_module(f"import importlib\n{_OVERLOAD_GROUP}{read}")
    collect_imports([module], {module.module}, {}, namespace="sample")
    expected = frozenset({"resolve_source_entity"}) if stable else frozenset()
    assert static_overload_bindings(module) == expected
