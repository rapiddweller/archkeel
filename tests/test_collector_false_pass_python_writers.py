# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1522: a writer outside the scan roots that changes a public import binding is never PASS.

Consumer: `archkeel validate`. `app.consumer` imports `f` from the public package `app.lib`, which
re-exports `app.lib.pub.f`. Code of the repository outside `src` replaces `app.lib.f` with the
private `app.lib._priv.secret`, so the consumer gets a private function: BOUNDARY must not PASS
(AD-770). A test file is under the stated premise of the run, so the same write there keeps PASS,
and the frame states the premise.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import run
from python_interface_plants import Plant, build

from archkeel.cli import core_only

PREMISE = (
    "Code outside the scan roots, including test code, hands in no module object of the scan and"
    " writes no binding of a module or class of the scan."
)
LIBRARY = {
    "src/app/lib/__init__.py": "from app.lib.pub import f\n",
    "src/app/lib/pub.py": "def f(): return 'public'\n",
    "src/app/lib/_priv.py": "def secret(): return 'private'\n",
}
WRITER = (
    "from app.lib._priv import secret\nimport app.lib\napp.lib.f = secret\nimport app.consumer\n"
    "assert app.consumer.f() == 'private'\n"
)
# A C extension that replaces the binding when Python imports it (`PyInit_native_patch`).
NATIVE = (
    "#include <Python.h>\n"
    "static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "
    '"native_patch", NULL, -1, NULL};\n'
    "PyMODINIT_FUNC PyInit_native_patch(void) {\n"
    '    PyObject *lib = PyImport_ImportModule("app.lib");\n'
    '    PyObject *priv = PyImport_ImportModule("app.lib._priv");\n'
    "    if (!lib || !priv) return NULL;\n"
    '    PyObject *secret = PyObject_GetAttrString(priv, "secret");\n'
    '    if (!secret || PyObject_SetAttrString(lib, "f", secret) < 0) return NULL;\n'
    "    Py_DECREF(secret); Py_DECREF(priv); Py_DECREF(lib);\n"
    "    return PyModule_Create(&module);\n}\n"
)


def _validate(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, consumer: str, files: dict
) -> dict:
    root = tmp_path / "repo"
    root.mkdir()
    build(root, Plant("writer", consumer, ("app.lib.pub",), {**LIBRARY, **files}))
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    return run("validate", "--root", str(root))[1]


@pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")
def test_an_outside_python_writer_cannot_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _validate(
        tmp_path, release_core, monkeypatch, "from app.lib import f\n", {"outside.py": WRITER}
    )
    truth = subprocess.run(
        [
            "python3.12",
            "-I",
            "-c",
            "import sys; sys.path[:0] = ['src']; import runpy; runpy.run_path('outside.py')",
        ],
        cwd=tmp_path / "repo",
        capture_output=True,
        text=True,
    )
    assert truth.returncode == 0, truth.stderr

    assert result["frame"]["rules"]["BOUNDARY"][1] in {"FAIL", "UNKNOWN"}, result["frame"]


def test_a_native_writer_that_names_the_module_cannot_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer = "import native_patch\nfrom app.lib import f\n"
    result = _validate(
        tmp_path, release_core, monkeypatch, consumer, {"vendor/native_patch.c": NATIVE}
    )

    assert result["frame"]["rules"]["BOUNDARY"][1] in {"FAIL", "UNKNOWN"}, result["frame"]


def test_a_test_file_writer_is_the_stated_premise(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _validate(
        tmp_path,
        release_core,
        monkeypatch,
        "from app.lib import f\n",
        {"tests/test_patch.py": WRITER},
    )

    assert result["frame"]["rules"]["BOUNDARY"][1] == "PASS", result["frame"]
    assert result["frame"]["premise"] == PREMISE
