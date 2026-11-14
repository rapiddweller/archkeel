# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of the Python `interface_boundary` differential (AD-504, #880).

One consumer module imports from one library component. Each plant sets the public entries of the
library, the files of the library and the import of the consumer. `four` holds the verdict of
release 4.0.1 for the plant: its `report --json` on the same tree, one run for each plant
(recorded once from an installed 4.0.1).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GRAPH = "# Target\n\n<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n    root\n```\n"
LIB = "src/app/lib/__init__.py"
IMPL = "src/app/lib/impl.py"
DEFINES = "def f(): pass\ndef g(): pass\n"
REEXPORTS = "from app.lib.impl import f\n"


@dataclass(frozen=True)
class Plant:
    """One tree: the library files, the public entries and the import of the consumer."""

    name: str
    consumer: str
    public: tuple[str, ...]
    files: dict[str, str] = field(default_factory=dict)
    # The verdict of 4.0.1 and the verdicts that the core may give (the same, or a documented
    # stricter one). A core PASS is allowed only where 4.0.1 gives PASS.
    four: str = "PASS"
    core: tuple[str, ...] = ("PASS",)
    why: str = ""
    # What Python binds at import time, when it is not what 4.0.1 says, and whether the core still
    # gives PASS for it (an open false PASS that the documents name, pinned as such).
    truth: str = ""
    open_pass: bool = False


def plants() -> list[Plant]:
    p = Plant
    return [
        p("module public, name defined", "from app.lib import f\n", ("app.lib",), {LIB: DEFINES}),
        p("module public, no __all__", "from app.lib import g\n", ("app.lib",), {LIB: DEFINES}),
        p(
            "name outside a literal __all__",
            "from app.lib import g\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f']\n"},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "name inside a literal __all__",
            "from app.lib import f\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f']\n"},
        ),
        p(
            "private name",
            "from app.lib import _f\n",
            ("app.lib",),
            {LIB: "def _f(): pass\n"},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "exact symbol entry",
            "from app.lib.impl import f\n",
            ("app.lib.impl:f",),
            {LIB: "", IMPL: DEFINES},
        ),
        p(
            "other symbol than the exact entry",
            "from app.lib.impl import g\n",
            ("app.lib.impl:f",),
            {LIB: "", IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "submodule of a public module",
            "from app.lib.impl import f\n",
            ("app.lib",),
            {LIB: "", IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "reexport covered at the first hop",
            "from app.lib import f\n",
            ("app.lib",),
            {LIB: REEXPORTS + "__all__ = ['f']\n", IMPL: DEFINES},
        ),
        p(
            "reexport covered only at the second hop",
            "from app.lib import f\n",
            ("app.lib.impl",),
            {LIB: REEXPORTS, IMPL: DEFINES},
        ),
        p(
            "reexport not covered at any hop",
            "from app.lib import f\n",
            ("app.lib.impl:g",),
            {LIB: REEXPORTS, IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
        p("module object of a public module", "import app.lib\n", ("app.lib",), {LIB: DEFINES}),
        p(
            "module object of a hidden module",
            "import app.lib.impl\n",
            ("app.lib",),
            {LIB: "", IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "module with __getattr__, no __all__",
            "from app.lib import lazy\n",
            ("app.lib",),
            {LIB: "def __getattr__(name): return name\n"},
        ),
        p(
            "name in a dynamic __all__",
            "from app.lib import f\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f'] + ['g']\n"},
            core=("UNKNOWN",),
            why="4.0.1 reads the literal strings; the core cannot read the rest of __all__",
        ),
        p(
            "name outside a dynamic __all__",
            "from app.lib import g\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f'] + more()\n"},
            core=("UNKNOWN",),
            why="the unread part of __all__ may exclude g; 4.0.1 passes it (false PASS)",
        ),
        p(
            "all of a computed __all__",
            "from app.lib import g\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = compute()\n"},
            core=("UNKNOWN",),
            why="4.0.1 treats an unreadable __all__ as none and passes every name (false PASS)",
        ),
        p(
            "augmented __all__",
            "from app.lib import f\n",
            ("app.lib",),
            {LIB: DEFINES + "__all__ = ['f']\n__all__ += ['g']\n"},
            core=("UNKNOWN",),
            why="the core reads one literal __all__ only",
        ),
        p(
            "binding with two sources",
            "from app.lib import f\n",
            ("app.lib",),
            {
                LIB: "try:\n    from app.lib.impl import f\n"
                "except ImportError:\n    from app.lib.impl import g as f\n",
                IMPL: DEFINES,
            },
            core=("UNKNOWN",),
            why="an alias with two targets is not a proven route",
        ),
        p(
            "alias of a private name",
            "from app.lib import f\n",
            ("app.lib.impl",),
            {LIB: "from app.lib.impl import _g as f\n", IMPL: "def _g(): pass\n"},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "binding redefined after the re-export",
            "from app.lib import f\n",
            ("app.lib.impl",),
            {LIB: REEXPORTS + "def f(): pass\n", IMPL: DEFINES},
            four="UNKNOWN",
            core=("UNKNOWN",),
        ),
        p(
            "type-checking import of a hidden name",
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from app.lib.impl import f\n",
            ("app.lib",),
            {LIB: "", IMPL: DEFINES},
            four="FAIL",
            core=("FAIL",),
        ),
    ] + attacks()


PUB = "src/app/lib/pub.py"
PATCH = "src/app/lib/_patch.py"
GUARD = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
LAZY = "def f(): pass\ndef _lazy():\n    from app.lib.pub import f\n"


def attacks() -> list[Plant]:
    """The forms where a re-export is not what the survey would read (AD-504, review of #1178)."""
    p = Plant
    pub = {PUB: "def f(): pass\ndef g(): pass\n"}
    # B1: Python binds the private `app.lib.f`; the import in a nested scope binds a local name.
    nested = {
        "import in a function": ("lib.f", LAZY),
        "import in a class body": (
            "lib.f",
            "def f(): pass\nclass K:\n    from app.lib.pub import f\n",
        ),
        "aliased import in a function": (
            "lib.f",
            "def f(): pass\ndef _lazy():\n    from app.lib.pub import g as f\n",
        ),
        "relative import in a function": (
            "lib.f",
            "def f(): pass\ndef _lazy():\n    from .pub import f\n",
        ),
        "import in a lazy factory": (
            "lib.f",
            "def make():\n    from app.lib.pub import f\n    return f\nf = make()\n",
        ),
    }
    found = [
        p(
            f"nested re-export: {name}",
            "from app.lib import f\n",
            ("app.lib.pub",),
            {LIB: init, **pub},
            core=("UNKNOWN",),
            why="Python binds the private name of the package; this import is a local one",
            truth="FAIL",
        )
        for name, (_, init) in nested.items()
    ]
    found.append(
        p(
            "nested re-export: exact entry",
            "from app.lib import f\n",
            ("app.lib.pub:f",),
            {LIB: LAZY, **pub},
            core=("UNKNOWN",),
            why="Python binds the private name of the package; this import is a local one",
            truth="FAIL",
        )
    )
    found.append(
        p(
            "nested re-export: in the target module",
            "from app.lib.mod import f\n",
            ("app.lib.pub",),
            {LIB: "", "src/app/lib/mod.py": LAZY, **pub},
            four="FAIL",
            core=("FAIL", "UNKNOWN"),
            truth="FAIL",
        )
    )
    # B2: a package attribute bound by any statement wins over the submodule of the same name.
    bodies = {
        "try and except": "try:\n    from app.lib import _native as speedups\n"
        "except ImportError:\n    from app.lib import _pure as speedups\n",
        "for target": "for speedups in []:\n    pass\n",
        "with target": "with open(__file__) as speedups:\n    pass\n",
        "tuple target": "(speedups, other) = (1, 2)\n",
        "walrus": "(speedups := 1)\n",
        "global in a function": "def _go():\n    global speedups\n    speedups = 1\n",
        "def in an if": "if True:\n    def speedups(): pass\n",
    }
    files = {
        "src/app/lib/speedups.py": "def fast(): pass\n",
        "src/app/lib/_native.py": "",
        "src/app/lib/_pure.py": "",
    }
    found.extend(
        p(
            f"shadowed submodule: {name}",
            "from app.lib import speedups\n",
            ("app.lib.speedups",),
            {LIB: body, **files},
            core=("UNKNOWN",),
            why="the package attribute may or may not be the submodule; the survey cannot say",
            truth="FAIL",
        )
        for name, body in bodies.items()
    )
    # B3: another module writes to the package after its statements ran.
    patched = {
        "attribute write": (
            "from app.lib.pub import f\nimport app.lib._patch\n",
            "lib.f = secret\n",
            "f",
        ),
        "new attribute": ("from app.lib.pub import f\nimport app.lib._patch\n", "lib.f = 1\n", "f"),
        "all removed": (
            "from app.lib.pub import f, g\n__all__ = ['f', 'g']\nimport app.lib._patch\n",
            "lib.__all__.remove('g')\n",
            "g",
        ),
        "all replaced": (
            "from app.lib.pub import f, g\n__all__ = ['f', 'g']\nimport app.lib._patch\n",
            "lib.__all__ = ['f']\n",
            "g",
        ),
    }
    found.extend(
        p(
            f"write from another module: {name}",
            f"from app.lib import {used}\n",
            ("app.lib",),
            {LIB: init, PATCH: "from app import lib\nsecret = 1\n" + write, **pub},
            core=("UNKNOWN",),
            why="another module changes the namespace after the statements of the package ran",
            truth="FAIL",
        )
        for name, (init, write, used) in patched.items()
    )
    # S1: a guarded import that passes a re-export, and a guarded private module.
    found.append(
        p(
            "guarded import through a re-export",
            GUARD + "    from app.lib import f\n",
            ("app.lib.pub",),
            {LIB: "from app.lib.pub import f\n", **pub},
            core=("UNKNOWN",),
            why="a guarded route that passes a re-export is not proven",
        )
    )
    found.append(
        p(
            "guarded import of a private module",
            GUARD + "    import app.lib._priv\n",
            ("app.lib",),
            {LIB: "", "src/app/lib/_priv.py": "def secret(): pass\n"},
            four="FAIL",
            core=("UNKNOWN",),
            why="a guarded module import is a named type-publication gap (UNKNOWN, never PASS)",
        )
    )
    return found + names() + opens()


def names() -> list[Plant]:
    """S3: private and special names, and a port that names a submodule."""
    p = Plant
    return [
        p(
            "private name listed in __all__",
            "from app.lib import _h\n",
            ("app.lib",),
            {LIB: "def _h(): pass\n__all__ = ['_h']\n"},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "exact entry of a private name",
            "from app.lib import _h\n",
            ("app.lib:_h",),
            {LIB: "def _h(): pass\n"},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "dunder name",
            "from app.lib import __version__\n",
            ("app.lib",),
            {LIB: "__version__ = '1'\n"},
            four="FAIL",
            core=("FAIL",),
        ),
        p(
            "port that names a submodule",
            "from app.lib import mod\n",
            ("app.lib:mod",),
            {LIB: "", "src/app/lib/mod.py": "def f(): pass\n"},
            four="FAIL",
            core=("FAIL",),
        ),
    ]


def opens() -> list[Plant]:
    """The open false PASS forms: truth is FAIL, 4.0.1 says PASS, the core still says PASS."""
    p = Plant
    private = {LIB: "from app.lib import _priv\n", "src/app/lib/_priv.py": "def secret(): pass\n"}
    return [
        p(
            "open: private submodule used through the public module object",
            "import app.lib\napp.lib._priv.secret()\n",
            ("app.lib",),
            private,
            truth="FAIL",
            open_pass=True,
            why="the rule judges imports, and a use through a public module object is no import",
        ),
        p(
            "open: write through sys.modules",
            "import sys\nsys.modules['app.lib'].f = 1\n",
            ("app.lib",),
            {LIB: "def f(): pass\n"},
            core=("UNKNOWN",),
            truth="FAIL",
            why="sys.modules is an import-system gap of the survey (AD-450)",
        ),
    ]


def build(root: Path, plant: Plant) -> Path:
    """Write the tree of one plant below `root` and commit it."""
    files = {
        "src/app/__init__.py": "",
        "src/app/consumer.py": plant.consumer,
        "docs/target.md": GRAPH,
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "archkeel.toml": (
            '[scan]\nlanguage = "python"\nroots = ["src"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\n'
        ),
        **plant.files,
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "architecture-contract.json").write_text(json.dumps(contract(plant), indent=1))
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)
    return root


def contract(plant: Plant) -> dict[str, Any]:
    base = {
        "role": "component",
        "responsibilities": ["Own the modules."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
        "requires": [],
    }

    def part(name: str, **owned: Any) -> dict[str, Any]:
        return {**base, "id": name, "label": name, **owned}

    return {
        "schema_version": "2.2.0",
        "components": [
            part("root", packages=[], exact_modules=["app"]),
            part("consumer", packages=[], exact_modules=["app.consumer"]),
            part("lib", packages=["app.lib"], public=list(plant.public)),
        ],
        "rules": [
            {
                "id": "BOUNDARY",
                "kind": "interface_boundary",
                "rationale": "Callers use the declared interface.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
                "include_type_checking": True,
            }
        ],
    }
