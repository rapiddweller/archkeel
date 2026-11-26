# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2129: a class gets a kind from a base in another module only when each step is proven.

A facade `app.api` exports `Derived` of `app/derived.py`. When the base has a proven kind,
`Derived` has a record, and `boundary_types` names the inherited surface of the base (a gap that
reads no inherited member). When any step is not proven, `Derived` has no record: the gap is
`no_record`. Both answers are UNKNOWN; the cause tells which one the survey took. Each plant runs
under CPython: the output shows what the class really is, so a plant that must keep `no_record`
is a real hazard.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from boundary_types_plants import Plant, facade
from boundary_types_sources import RULE, project
from test_cli_core_only_scan import command

API = facade("from app.derived import Derived\n", "'Derived'")
DERIVED = (
    "from app.base import Base\n\n\nclass Derived(Base):\n"
    "    def m(self, a: int) -> int:\n        return a\n"
)
PLAIN = "class Base:\n    pass\n"
OTHER = "class Other:\n    marker = 1\n"

# name: (extra files, the Python check that prints the truth, the text that it must print)
KIND = "inherited_surface"
OPEN = "no_record"
PLANTS: dict[str, tuple[dict[str, str], str, str, str]] = {
    "plain-base": (
        {"base.py": PLAIN, "derived.py": DERIVED},
        "import app.derived as d",
        "Base type None",
        KIND,
    ),
    "abc-base": (
        {"base.py": "from abc import ABC\n\n\nclass Base(ABC):\n    pass\n", "derived.py": DERIVED},
        "import app.derived as d",
        "Base ABCMeta None",
        KIND,
    ),
    "reexport-chain": (
        {
            "base.py": PLAIN,
            "facade.py": "from app.base import Base\n",
            "derived.py": DERIVED.replace("app.base", "app.facade"),
        },
        "import app.derived as d",
        "Base type None",
        KIND,
    ),
    "diamond": (
        {
            "left.py": "class Left:\n    pass\n",
            "right.py": "class Right:\n    pass\n",
            "base.py": (
                "from app.left import Left\nfrom app.right import Right\n\n\n"
                "class Base(Left, Right):\n    pass\n"
            ),
            "derived.py": DERIVED,
        },
        "import app.derived as d",
        "Base type None",
        KIND,
    ),
    # A step that is not proven: no kind, no record.
    "base-rebound-by-a-write": (
        {
            "base.py": PLAIN,
            "other.py": OTHER,
            "patch.py": "import app.base\nimport app.other\n\napp.base.Base = app.other.Other\n",
            "derived.py": DERIVED,
        },
        "import app.patch, app.derived as d",
        "Other type 1",
        OPEN,
    ),
    "base-rebound-in-the-facade": (
        {
            "base.py": PLAIN,
            "other.py": OTHER,
            "facade.py": "from app.base import Base\n",
            "patch.py": (
                "import app.facade\nimport app.other\n\napp.facade.Base = app.other.Other\n"
            ),
            "derived.py": DERIVED.replace("app.base", "app.facade"),
        },
        "import app.patch, app.derived as d",
        "Other type 1",
        OPEN,
    ),
    "reexport-that-binds-the-name-twice": (
        {
            "base.py": PLAIN,
            "other.py": OTHER,
            "facade.py": "from app.base import Base\nfrom app.other import Other\n\nBase = Other\n",
            "derived.py": DERIVED.replace("app.base", "app.facade"),
        },
        "import app.derived as d",
        "Other type 1",
        OPEN,
    ),
    "metaclass-base": (
        {
            "base.py": "class Meta(type):\n    pass\n\n\nclass Base(metaclass=Meta):\n    pass\n",
            "derived.py": DERIVED,
        },
        "import app.derived as d",
        "Base Meta None",
        OPEN,
    ),
    "base-built-by-a-call": (
        {
            "base.py": "def make():\n    return type('Base', (), {})\n\n\nBase = make()\n",
            "derived.py": DERIVED,
        },
        "import app.derived as d",
        "Base type None",
        OPEN,
    ),
    "conditional-base": (
        {
            "base.py": (
                "import sys\n\nif sys.argv:\n    class Base:\n        pass\n"
                "else:\n    class Base(int):\n        pass\n"
            ),
            "derived.py": DERIVED,
        },
        "import app.derived as d",
        "Base type None",
        OPEN,
    ),
    "decorated-base": (
        {
            "base.py": (
                "def swap(cls):\n    return type('Swapped', (), {})\n\n\n"
                "@swap\nclass Base:\n    pass\n"
            ),
            "derived.py": DERIVED,
        },
        "import app.derived as d",
        "Swapped type None",
        OPEN,
    ),
    "base-from-importlib": (
        {
            "base.py": PLAIN,
            "derived.py": DERIVED.replace(
                "from app.base import Base",
                "import importlib\n\nBase = importlib.import_module('app.base').Base",
            ),
        },
        "import app.derived as d",
        "Base type None",
        OPEN,
    ),
    "two-binders-of-the-base": (
        {
            "base.py": PLAIN,
            "derived.py": DERIVED.replace(
                "from app.base import Base",
                "try:\n    from app.base import Base\nexcept ImportError:\n    Base = object",
            ),
        },
        "import app.derived as d",
        "Base type None",
        OPEN,
    ),
    "base-in-a-module-with-a-hazard": (
        {
            "base.py": "exec('x = 1')\n\n\nclass Base:\n    pass\n",
            "derived.py": DERIVED,
        },
        "import app.derived as d",
        "Base type None",
        OPEN,
    ),
    "relative-import-of-the-base": (
        {"base.py": PLAIN, "derived.py": DERIVED.replace("from app.base", "from .base")},
        "import app.derived as d",
        "Base type None",
        OPEN,
    ),
}


def _run(tmp_path: Path, core: Path, name: str) -> tuple[str, str, str]:
    files, check, _, _ = PLANTS[name]
    root = project(tmp_path / "p", Plant(API, "OPEN", files=files))
    ran = subprocess.run(
        [
            sys.executable,
            "-c",
            f"{check}\nbase = d.Derived.__mro__[1]\n"
            "print(base.__name__, type(d.Derived).__name__, getattr(d.Derived, 'marker', None))",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    result = json.loads(command(core, root, "--json").stdout)
    assert "refusal" not in result, result
    assert ran.returncode == 0, ran.stderr
    return result["frame"]["rules"][RULE][1], json.dumps(result["gaps"]), ran.stdout.strip()


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_survey_gives_a_kind_only_for_a_proven_base_and_python_shows_the_truth(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    status, gaps, mro = _run(tmp_path, release_core, name)
    _, _, truth, cause = PLANTS[name]
    assert mro == truth
    assert status == "UNKNOWN", gaps
    assert f"app.api.Derived: {cause}" in gaps or f"app.api:Derived: {cause}" in gaps, gaps
    other = OPEN if cause == KIND else KIND
    assert f"Derived: {other}" not in gaps, gaps
