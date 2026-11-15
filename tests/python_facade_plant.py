# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A public entry that only a declared signature reaches (AD-580, #880).

The component `lib` publishes `Item` and the function `make`. `make(item: Item)` names `Item`,
and nobody outside `lib` imports `Item`. Release 4.0.1 counts the entry as used because a
declared facade signature names the type. Each variant changes the signature or the declaration;
`four` is the `interface.*` code that an installed 4.0.1 gives (`validate --json`) for the entry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from python_deep_mount_plant import GRAPH, PROJECT, component, rules

ITEM = "pkg.lib.types:Item"
MAKE = "pkg.lib.api:make"
OTHER = "pkg.lib.api:other"
SCAN = '[scan]\nroots = ["pkg"]\nnamespace = "pkg"\ncontract = "architecture-contract.json"\n'


@dataclass(frozen=True)
class Variant:
    name: str
    api: str
    public: tuple[str, ...]
    # The code of the entry `Item` in 4.0.1 (None: clear) and in the core (None: clear).
    four: str | None
    core: str | None


API = "from pkg.lib.types import Item\n\n\ndef make(item: Item) -> int:\n    return 1\n"
HEAD = "from pkg.lib.types import Item\n"


def variants() -> list[Variant]:
    both = (ITEM, MAKE, OTHER)
    return [
        Variant("a public function names the type", API, both, None, None),
        Variant(
            "an optional parameter and a list return",
            HEAD + "\n\ndef make(item: Item | None = None) -> list[Item]:\n    return []\n",
            both,
            None,
            None,
        ),
        Variant(
            "the function is not public",
            API,
            (ITEM, OTHER),
            "interface.unused",
            "interface.usage_unknown",
        ),
        Variant(
            "the type is named only by a private function",
            HEAD
            + "\n\ndef _make(item: Item) -> int:\n    return 1\n"
            + "\n\ndef make() -> int:\n    return 1\n",
            both,
            "interface.unused",
            "interface.usage_unknown",
        ),
        Variant(
            "no import and no signature reaches the entry",
            "def make() -> int:\n    return 1\n",
            both,
            "interface.unused",
            "interface.usage_unknown",
        ),
        Variant(
            "the type is a string annotation",
            HEAD + "\n\ndef make(item: 'Item') -> int:\n    return 1\n",
            both,
            "interface.unused",
            "interface.usage_unknown",
        ),
        Variant(
            "the import is under TYPE_CHECKING",
            "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n"
            + "    from pkg.lib.types import Item\n\n\n"
            + "def make(item: Item) -> int:\n    return 1\n",
            both,
            None,
            "interface.usage_unknown",
        ),
        Variant(
            "a decorator can replace the function",
            HEAD
            + "\n\ndef wrap(f):\n    return f\n\n\n@wrap\n"
            + "def make(item: Item) -> int:\n    return 1\n",
            both,
            None,
            "interface.usage_unknown",
        ),
    ]


def build(root: Path, variant: Variant) -> Path:
    other = "\n\ndef other() -> int:\n    return 1\n"
    contracts = {
        "architecture-contract.json": {
            "schema_version": "2.2.0",
            "rules": rules("pkg"),
            "components": [
                component(
                    "main",
                    [],
                    None,
                    exact_modules=["pkg", "pkg.main"],
                    requires=[
                        {
                            "component": "lib",
                            "through": ["pkg.lib.api:make", "pkg.lib.api:other"],
                            "rationale": "main calls the library.",
                            "decided_by": "agent",
                        }
                    ],
                ),
                component("lib", ["pkg.lib"], list(variant.public), exact_modules=[]),
            ],
        }
    }
    files = {
        "pkg/__init__.py": "",
        "pkg/lib/__init__.py": "",
        "pkg/lib/types.py": "class Item: ...\n",
        "pkg/lib/api.py": variant.api + other,
        "pkg/main/__init__.py": "from pkg.lib.api import make, other\n\nvalue = (make, other)\n",
        "docs/target.md": GRAPH.replace("main --> app", "main --> lib"),
        "pyproject.toml": PROJECT,
        "archkeel.toml": SCAN,
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    for name, contract in contracts.items():
        (root / name).write_text(json.dumps(contract, indent=1))
    return root
