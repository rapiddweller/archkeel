# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1048, #1965: a code object that a function hands out is an import door.

Consumer: `archkeel validate` through the release core. `app.consumer` rewrites the names of a
code object, so its `import json` imports `app.lib`. CPython 3.12 runs each plant and shows that
`app.lib` is in `sys.modules`; the rule that forbids `app.consumer -> app.lib` is never PASS.
A read of a scalar field of a code object, or of `__name__`, hands out no code object and keeps
PASS; CPython shows that `app.lib` stays unloaded.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from test_cli_native_python_imports import RULE, component, project, rows, verdict
from test_cli_vacuous_pass import amend

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="CPython is the oracle")

REWRITE = "tuple('app.lib' if n == 'json' else n for n in {code}.co_names)"
PLANTS = {
    "code-assignment": (
        "def f():\n    import json\n    return json\n\n"
        "f.__code__ = f.__code__.replace(co_names=" + REWRITE.format(code="f.__code__") + ")\n"
        "f()\n"
    ),
    "function-type-from-code": (
        "def f():\n    import json\n    return json\n\n"
        "g = type(f)(f.__code__.replace(co_names=" + REWRITE.format(code="f.__code__") + "), {})\n"
        "g()\n"
    ),
    "generator-code": (
        "def g():\n    yield 1\n    import json\n    yield json\n\n"
        "code = g().gi_code.replace(co_names=" + REWRITE.format(code="g().gi_code") + ")\n"
        "list(type(g)(code, {})())\n"
    ),
    "string-name": (
        "def f():\n    import json\n    return json\n\n"
        "code = getattr(f, '__code__')\n"
        "setattr(f, '__code__', code.replace(co_names=" + REWRITE.format(code="code") + "))\n"
        "f()\n"
    ),
    "frame-code": (
        "import sys\n\n"
        "def f():\n    import json\n    return json\n\n"
        "def run():\n    return sys._getframe().f_code\n\n"
        "code = f.__code__.replace(co_names=" + REWRITE.format(code="f.__code__") + ")\n"
        "type(f)(code, {})()\nrun()\n"
    ),
}
# #1967 (AD-1053): a computed name on an unproved receiver is a trojan horse. Each plant imports
# `app.lib` under CPython 3.12, so the rule must not give PASS.
EDIT = "tuple('app.lib' if n == 'json' else n for n in code.co_names)"
HEAD = "def f():\n    import json\n    return json\n\nname = {name}\n"
TAIL = "code = {read}\nsetattr(f, name, code.replace(co_names=" + EDIT + "))\nf()\n"
COMPUTED = {
    "joined-getattr": ("'__co' + 'de__'", "getattr(f, name)"),
    "getattribute": ("''.join(['__c', 'ode__'])", "f.__getattribute__(name)"),
    "variable-name": ("''.join(['__c', 'ode__'])", "getattr(f, name)"),
    "reversed-name": ("'__edoc__'[::-1]", "getattr(f, name)"),
    "dir-filter": (
        "[n for n in dir(f) if n.startswith('__co')][0]",
        "getattr(f, name)",
    ),
}
CONTROLS = {
    "scalar-field": "def f():\n    import json\n    return json\n\nNAME = f.__code__.co_name\n",
    "function-name": "def f():\n    import json\n    return json\n\nNAME = f.__name__\nf()\n",
    "defaults-read": "def f(a=1):\n    return a\n\nDEFAULTS = f.__defaults__\n",
}
FILES = {
    "src/app/__init__.py": "",
    "src/app/lib/__init__.py": "value = 1\n",
}
RULES = [
    {
        **RULE,
        "id": "NO-LIB",
        "kind": "forbidden_dependency",
        "source": "app.consumer",
        "target": "app.lib",
        "include_type_checking": True,
    }
]


def loads_lib(root: Path) -> bool:
    """Run the consumer under CPython 3.12 and say whether `app.lib` was imported."""
    code = (
        "import sys; sys.path[:0] = ['src']; import app.consumer; print('app.lib' in sys.modules)"
    )
    done = subprocess.run(
        ["python3.12", "-I", "-c", code], cwd=root, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip() == "True"


def build(root: Path, source: str) -> Path:
    files = {**FILES, "src/app/consumer.py": source}

    def own(contract: dict) -> None:
        contract["components"] = [
            component("root", ["app"], exact=True),
            component("consumer", ["app.consumer"], exact=True),
            component("lib", ["app.lib"]),
        ]

    return amend(project(root, files, contract_rules=RULES), own)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_rewritten_code_object_is_never_pass(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    root = build(tmp_path, PLANTS[name])
    assert loads_lib(root), "CPython must import app.lib: the plant is real"
    result = verdict(release_core, root)
    assert rows(result)["NO-LIB"] in {"FAIL", "UNKNOWN"}, result["frame"]


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_plain_read_of_a_function_keeps_pass(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    root = build(tmp_path, CONTROLS[name])
    assert not loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    result = verdict(release_core, root)
    assert rows(result)["NO-LIB"] == "PASS", result["frame"]


@pytest.mark.parametrize("name", sorted(COMPUTED))
def test_a_computed_name_that_reaches_a_code_object_is_never_pass(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    value, read = COMPUTED[name]
    source = HEAD.format(name=value) + TAIL.format(read=read)
    root = build(tmp_path, source)
    assert loads_lib(root), "CPython must import app.lib: the plant is real"
    result = verdict(release_core, root)
    assert rows(result)["NO-LIB"] in {"FAIL", "UNKNOWN"}, result["frame"]
