# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of the Python interface lifecycle differential (AD-514, #880).

The tree and the contract come from `python_interface_plants.build`. `codes` is the set of
`interface.*` diagnostics that release 4.0.1 gives for the plant, one `validate --json` of an
installed 4.0.1 for each plant. The core gives a hygiene row for a finding; it gives
`interface.usage_unknown` where 4.0.1 gives `interface.unused` or `interface.missing`, because
the core reads no declared facade signature.
"""

from __future__ import annotations

from dataclasses import dataclass

from python_interface_plants import DEFINES, IMPL, LIB, Plant

REEXPORT = "from app.lib.impl import f\n"
API = "src/app/lib/api.py"
MODELS = "src/app/lib/models.py"
FACADE = "from app.lib.models import Model\n\n\ndef make() -> Model:\n    return Model()\n"


@dataclass(frozen=True)
class Lifecycle:
    plant: Plant
    # The `interface.*` codes of 4.0.1, the codes that the core may give (each of them a row),
    # and why the core differs.
    four: frozenset[str]
    core: frozenset[str]
    why: str = ""


def _plant(name: str, consumer: str, public, files: dict[str, str], planned=()) -> Plant:  # noqa: ANN001
    return Plant(name, consumer, public, files, planned=tuple(planned))


def lifecycles() -> list[Lifecycle]:
    both = {LIB: "", IMPL: DEFINES}
    clear: frozenset[str] = frozenset()
    return [
        Lifecycle(
            _plant("module entry used", "from app.lib import f\n", ("app.lib",), {LIB: DEFINES}),
            clear,
            clear,
        ),
        Lifecycle(
            _plant("symbol entry used", "from app.lib.impl import f\n", ("app.lib.impl:f",), both),
            clear,
            clear,
        ),
        Lifecycle(
            _plant(
                "entry used through a re-export",
                "from app.lib import f\n",
                ("app.lib.impl:f",),
                {LIB: REEXPORT, IMPL: DEFINES},
            ),
            clear,
            clear,
        ),
        Lifecycle(
            _plant("module object used", "import app.lib\n", ("app.lib",), {LIB: DEFINES}),
            clear,
            clear,
        ),
        Lifecycle(
            _plant(
                "symbol entry unused",
                "from app.lib.impl import f\n",
                ("app.lib.impl:f", "app.lib.impl:g"),
                both,
            ),
            frozenset({"interface.unused"}),
            frozenset({"interface.usage_unknown"}),
            "the core cannot exclude a facade signature that reaches the entry",
        ),
        Lifecycle(
            _plant(
                "entry of a module that is not scanned",
                "from app.lib.impl import f\n",
                ("app.lib.impl:f", "app.lib.ghost:x"),
                both,
            ),
            frozenset({"interface.missing"}),
            frozenset({"interface.usage_unknown"}),
            "the core cannot exclude a facade signature that reaches the entry",
        ),
        Lifecycle(
            _plant(
                "no public entry, imports received", "from app.lib import f\n", None, {LIB: DEFINES}
            ),
            frozenset({"interface.undeclared"}),
            frozenset({"interface.undeclared"}),
        ),
        Lifecycle(
            _plant(
                "planned entry reached",
                "from app.lib.impl import f\n",
                ("app.lib.impl:f",),
                both,
                ("app.lib.impl:g",),
            ),
            clear,
            frozenset({"interface.usage_unknown"}),
            "the core cannot exclude a facade signature that reaches the planned entry",
        ),
        Lifecycle(
            _plant(
                "planned entry built and used",
                "from app.lib.impl import f\n",
                ("app.lib",),
                both,
                ("app.lib.impl:f",),
            ),
            frozenset({"interface.planned_built", "interface.unused"}),
            frozenset({"interface.planned_built", "interface.usage_unknown"}),
            "the public module entry is unused in 4.0.1; the core cannot exclude a signature",
        ),
        Lifecycle(
            _plant(
                "planned entry not scanned",
                "from app.lib.impl import f\n",
                ("app.lib.impl:f",),
                both,
                ("app.lib.future:x",),
            ),
            clear,
            clear,
        ),
        Lifecycle(
            _plant(
                "star import of the entry module",
                "from app.lib.impl import *\n",
                ("app.lib.impl:f",),
                both,
            ),
            frozenset({"interface.unused"}),
            frozenset({"interface.usage_unknown"}),
            "a star import names no symbol, so it reaches no module:name entry",
        ),
        Lifecycle(
            _plant(
                "entry reached only by a dynamic import",
                "import importlib\nm = importlib.import_module('app.lib.impl')\n",
                ("app.lib.impl",),
                both,
            ),
            frozenset({"interface.unused"}),
            frozenset({"interface.usage_unknown"}),
            "a call-form import binds no name and may not run, so it proves no use",
        ),
        Lifecycle(
            _plant(
                "entry reached by a facade signature",
                "from app.lib.api import make\n",
                ("app.lib.api:make", "app.lib.models:Model"),
                {
                    LIB: "",
                    API: FACADE,
                    MODELS: "class Model:\n    pass\n",
                },
            ),
            clear,
            frozenset({"interface.usage_unknown"}),
            "4.0.1 reads the type of a declared signature; the core does not",
        ),
    ]
