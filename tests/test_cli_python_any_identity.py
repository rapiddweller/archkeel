# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The survey reports `any_annotation` only when the module proves that `Any` is typing.Any (#1833).

CPython is the truth: a FAIL is allowed only where the annotation is `typing.Any`. A true
`typing.Any` that the survey cannot prove stays UNKNOWN (a named gap), never PASS.
"""

import sys
import types
import typing
from pathlib import Path

import pytest
from test_cli_native_python_imports import rows
from test_cli_python_profile_limits import CONSTRUCT, Plant, scanned

# (source, expected status, true when CPython says the annotation of `x` is typing.Any)
REAL = "FAIL"
CASES = {
    "from-typing": ("from typing import Any\nx: Any = None\n", REAL, True),
    "from-typing-extensions": ("from typing_extensions import Any\nx: Any = None\n", REAL, True),
    "typing-attribute": ("import typing\nx: typing.Any = None\n", REAL, True),
    "typing-alias": ("import typing as t\nx: t.Any = None\n", REAL, True),
    "typing-extensions-alias": ("import typing_extensions as te\nx: te.Any = None\n", REAL, True),
    "typing-extensions-attribute": (
        "import typing_extensions\nx: typing_extensions.Any = None\n",
        REAL,
        True,
    ),
    "star-from-typing": ("from typing import *\nx: Any = None\n", REAL, True),
    "star-and-import": (
        "from typing import *\nfrom typing import Any\nx: Any = None\n",
        REAL,
        True,
    ),
    "typing-import-under-if": ("if True:\n    import typing\nx: typing.Any = None\n", REAL, True),
    "nested-class-attribute": (
        "class Outer:\n    class Any: pass\nx: Outer.Any = None\n",
        "UNKNOWN",
        False,
    ),
    "other-module-attribute": ("import mylib\nx: mylib.Any = None\n", "UNKNOWN", False),
    "star-then-local-class": (
        "from typing import *\nclass Any: pass\nx: Any = None\n",
        "UNKNOWN",
        False,
    ),
    "other-star": ("from other import *\nx: Any = None\n", "UNKNOWN", False),
    "typing-rebound": (
        "import typing\nclass typing:\n    Any = 1\nx: typing.Any = None\n",
        "UNKNOWN",
        False,
    ),
    # Named gaps: CPython says typing.Any, the source order decides, the survey stays UNKNOWN.
    "local-class-then-star": (
        "class Any: pass\nfrom typing import *\nx: Any = None\n",
        "UNKNOWN",
        True,
    ),
}


def run_in_cpython(source: str) -> object:
    other = types.ModuleType("other")
    other.Any = type("Any", (), {})  # type: ignore[attr-defined]
    mylib = types.ModuleType("mylib")
    mylib.Any = type("Any", (), {})  # type: ignore[attr-defined]
    modules = {"other": other, "mylib": mylib}
    with pytest.MonkeyPatch.context() as patch:
        for name, module in modules.items():
            patch.setitem(sys.modules, name, module)
        namespace: dict[str, object] = {"__name__": "plant"}
        exec(compile(source, "plant.py", "exec"), namespace)
    return namespace["__annotations__"]["x"]  # type: ignore[index]


@pytest.mark.parametrize("name", CASES)
def test_cpython_truth_of_each_plant(name: str) -> None:
    source, _, is_typing_any = CASES[name]
    assert (run_in_cpython(source) is typing.Any) is is_typing_any


@pytest.mark.parametrize("name", CASES)
def test_any_annotation_needs_the_proof(release_core: Path, tmp_path: Path, name: str) -> None:
    source, expected, is_typing_any = CASES[name]
    rule = {**CONSTRUCT, "id": "NO-ANY", "constructs": ["any_annotation"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    status = rows(result)["NO-ANY"]
    assert status == expected, result["frame"]["explained"]
    assert status != "FAIL" or is_typing_any


def test_a_name_without_a_binder_is_unknown(release_core: Path, tmp_path: Path) -> None:
    rule = {**CONSTRUCT, "id": "NO-ANY", "constructs": ["any_annotation"]}
    source = "from __future__ import annotations\nx: Any = None\n"
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-ANY"] == "UNKNOWN", result["frame"]["explained"]
