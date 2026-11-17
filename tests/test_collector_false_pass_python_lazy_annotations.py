# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1523: a lazy method annotation on Python 3.14 never passes an unproved `object` allowance.

Consumer: `archkeel validate`, rule `API-TYPES` (`boundary_types`). `Box.f(self, x: object)` has an
allowance for the builtin `object`. On Python 3.14 the annotation is evaluated when it is read, in
the namespace of `Box` (PEP 649): a slot `object` gives a member descriptor, and a store
`app.api.Box.object = app.api.Hidden` in a script gives `Hidden`. The project allows 3.14
(`requires-python = ">=3.11"`), so the rule must not PASS (AD-802). A range that ends below 3.14,
and `from __future__ import annotations`, keep the allowance.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from boundary_types_plants import Plant
from boundary_types_sources import project
from core_support import run

from archkeel.cli import core_only
from archkeel.cli.core_words import plain

ALLOWED = (
    {"qualified_name": "app.api.Box.f", "position": "x", "field_path": "", "annotation": "object"},
)
SLOTS = "    __slots__ = ('object',)\n"
WRITER = "import app.api\napp.api.Box.object = app.api.Hidden\n"
REMEDY = "narrow the version range of the project"


def _api(head: str = "", future: bool = False) -> str:
    body = "class Hidden:\n    pass\nclass Box:\n" + head
    body += "    def f(self, x: object) -> int: return 1\n__all__ = ['Box']\n"
    return ("from __future__ import annotations\n" if future else "") + body


def _validate(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    api: str,
    files: dict[str, str] | None = None,
    requires: str = ">=3.11",
) -> dict:
    root = project(tmp_path / "repo", Plant(api, "FAIL", allowed=ALLOWED))
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "p"\nversion = "0"\nrequires-python = "{requires}"\n'
    )
    for name, text in (files or {}).items():
        (root / name).write_text(text)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "--allow-empty",
            "-qm",
            "c",
        ],
        check=True,
    )
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    return run("validate", "--root", str(root))[1]


def _truth(root: Path, script: str) -> str:
    """What Python 3.14 reads for `x`, or `""` when no Python 3.14 is installed."""
    python = shutil.which("python3.14")
    if python is None:
        return ""
    code = (
        f"import sys; sys.path.insert(0, '.'); {script}import annotationlib, app.api; "
        "print(annotationlib.get_annotations(app.api.Box.f)['x'])"
    )
    done = subprocess.run([python, "-I", "-c", code], cwd=root, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.mark.parametrize(
    ("head", "files", "truth"),
    [
        pytest.param(SLOTS, {}, "<member 'object' of 'Box' objects>", id="slots"),
        pytest.param("", {"outside.py": WRITER}, "<class 'app.api.Hidden'>", id="outside-write"),
    ],
)
def test_a_lazy_method_annotation_cannot_pass_an_unproved_allowance(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    head: str,
    files: dict[str, str],
    truth: str,
) -> None:
    result = _validate(tmp_path, release_core, monkeypatch, _api(head), files)
    found = _truth(
        tmp_path / "repo", "import runpy; runpy.run_path('outside.py'); " if files else ""
    )
    assert found in {"", truth}, found

    assert result["frame"]["rules"]["API-TYPES"][1] in {"FAIL", "UNKNOWN"}, result["frame"]
    assert REMEDY in str(result["frame"]), result["frame"]


@pytest.mark.parametrize(
    ("future", "requires"),
    [
        pytest.param(False, ">=3.11,<3.14", id="range-below-3.14"),
        pytest.param(True, ">=3.11", id="future-annotations"),
    ],
)
def test_eager_or_string_annotations_keep_the_allowance(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    future: bool,
    requires: str,
) -> None:
    result = _validate(tmp_path, release_core, monkeypatch, _api(SLOTS, future), requires=requires)

    assert result["frame"]["rules"]["API-TYPES"][1] == "PASS", result["frame"]


def test_the_text_output_names_the_remedies_of_a_python_project() -> None:
    """The core names no language; the shell says the remedy for a Python project (AD-802)."""
    # AD-802 (#1523): the remedy of a late class annotation, in the words of a Python project.
    late = (
        "app.api.Box.f:x (lazy_class_namespace: object (the class namespace can hold the name when"
        " the annotation is evaluated: narrow the version range of the project, make the"
        " annotations strings, or remove the namespace write))"
    )
    assert plain(late) == (
        "app.api.Box.f:x (lazy class annotation: object (the class namespace can hold the name"
        " when the annotation is evaluated: narrow requires-python below 3.14, add"
        " `from __future__ import annotations`, or remove the namespace write))"
    )
