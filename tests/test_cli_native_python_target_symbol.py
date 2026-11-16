# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-668: a star import may take the item that a `target_symbol` rule forbids, so it never passes.

`pkg.base.vocab` defines `Profile`; the rule forbids `pkg.app` to name it. python3.12 runs each
plant and shows that `pkg.app` holds the member. A direct import and a re-export under another
name give FAIL; a star import gives UNKNOWN, because the scan does not list the names it takes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import run
from corpus_support import commit_tree

from archkeel.cli import core_only

pytestmark = pytest.mark.skipif(
    shutil.which("python3.12") is None, reason="python3.12 is the oracle"
)

VOCAB = "import enum\n\n\nclass Profile(enum.Enum):\n    DART = 1\n\n\ndef other():\n    return 1\n"
PLANTS = [
    ("direct", "from pkg.base.vocab import Profile\n\nX = Profile.DART\n", "FAIL"),
    ("re-export under another name", "from pkg.base import Lang\n\nX = Lang.DART\n", "FAIL"),
    ("star import", "from pkg.base.vocab import *\n\nX = Profile.DART\n", "UNKNOWN"),
    ("no use of the item", "from pkg.base.vocab import other\n\nX = other()\n", "PASS"),
]


def _component(label: str) -> dict[str, object]:
    return {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [f"pkg.{label}"],
        "responsibilities": ["Own this package."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
    }


def _write(root: Path, app: str) -> None:
    files = {
        "pkg/__init__.py": "",
        "pkg/base/__init__.py": "from .vocab import Profile as Lang\n",
        "pkg/base/vocab.py": VOCAB,
        "pkg/app/__init__.py": app,
        "docs/target.md": "# Target\n",
        "archkeel.toml": '[scan]\nlanguage = "python"\nroots = ["pkg"]\nnamespace = "pkg"\n'
        'python = "3.12"\ncontract = "architecture-contract.json"\n',
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    rule = {
        "id": "NO-PROFILE",
        "kind": "forbidden_dependency",
        "source": "pkg.app",
        "target": "pkg.base",
        "target_symbol": "Profile",
        "include_type_checking": True,
        "rationale": "The fixture states this rule.",
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
    }
    contract = {
        "schema_version": "3.14.0",
        "components": [_component("base"), _component("app")],
        "rules": [rule],
    }
    (root / "architecture-contract.json").write_text(json.dumps(contract, indent=2))
    commit_tree(root)


@pytest.mark.parametrize(("name", "app", "status"), PLANTS, ids=[p[0] for p in PLANTS])
def test_a_star_import_never_passes_a_symbol_rule(
    core_binary: Path, tmp_path: Path, name: str, app: str, status: str
) -> None:
    _write(tmp_path, app)
    truth = subprocess.run(
        [
            "python3.12",
            "-I",
            "-c",
            "import sys; sys.path.insert(0, '.'); import pkg.app as a; print(a.X)",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert truth.stdout.strip() in {"Profile.DART", "1"}, truth
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: core_binary)
        _, result = run("validate", "--root", str(tmp_path))
    rules = result["frame"]["rules"]
    assert rules["NO-PROFILE"][1] == status, (name, result["frame"].get("details"))
