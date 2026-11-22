# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-782 (#1538): standard decorators and standard library types under the premise
`standard_library_unchanged`, through the release core.

Each plant runs with and without the premise. Without it, every plant is UNKNOWN and the cause
names the premise or the unread form. With it, a modeled form is read: a plain form passes, a
form that shows a class of the repository that no component declares fails, and a form that the
survey does not model stays UNKNOWN with its reason. `truth` plants check the modeled signature
against CPython.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from boundary_types_plants import Plant, facade
from boundary_types_sources import RULE, project
from test_cli_boundary_types import use_standard_library_premise
from test_cli_core_only_scan import command

SECRET = {"model.py": "class Secret:\n    pass\n"}

# name: (api source, extra files, row with the premise, a text that the frame must hold or "")
PLANTS: dict[str, tuple[str, dict[str, str], str, str]] = {
    "contextmanager-generator": (
        facade(
            "@contextmanager\ndef f(a: int) -> Generator[int, None, None]:\n    yield a\n",
            "'f'",
            "from contextlib import contextmanager\nfrom typing import Generator\n",
        ),
        {},
        "PASS",
        "",
    ),
    "asynccontextmanager": (
        facade(
            "@asynccontextmanager\nasync def f(a: int) -> AsyncIterator[str]:\n    yield ''\n",
            "'f'",
            "from contextlib import asynccontextmanager\n"
            "from collections.abc import AsyncIterator\n",
        ),
        {},
        "PASS",
        "",
    ),
    "cache": (
        facade(
            "@cache\ndef f(a: int) -> str:\n    return ''\n",
            "'f'",
            "from functools import cache\n",
        ),
        {},
        "PASS",
        "",
    ),
    "lru-cache-call": (
        facade(
            "@functools.lru_cache(maxsize=32)\ndef f(a: int) -> str:\n    return ''\n",
            "'f'",
            "import functools\n",
        ),
        {},
        "PASS",
        "",
    ),
    "property-and-cached-property": (
        facade(
            "class C:\n"
            "    @property\n    def size(self) -> int:\n        return 1\n"
            "    @cached_property\n    def name(self) -> str:\n        return ''\n"
            "    @staticmethod\n    @cache\n    def make(a: int) -> int:\n        return a\n",
            "'C'",
            "from functools import cache, cached_property\n",
        ),
        {},
        "PASS",
        "",
    ),
    "dataclass": (
        facade(
            "@dataclass\nclass P:\n    x: int\n    y: str = ''\n"
            "    z: int = field(default=0, kw_only=True)\n    hidden: Secret = field(init=False)\n"
            "    _: KW_ONLY\n    w: bool = False\n",
            "'P'",
            "from dataclasses import KW_ONLY, dataclass, field\nfrom app.model import Secret\n",
        ),
        SECRET,
        "PASS",
        "",
    ),
    "dataclass-init-false": (
        facade(
            "@dataclass(init=False, frozen=True)\nclass P:\n    secret: Secret\n"
            "    def size(self) -> int:\n        return 1\n",
            "'P'",
            "from dataclasses import dataclass\nfrom app.model import Secret\n",
        ),
        SECRET,
        "PASS",
        "",
    ),
    "wraps-equal": (
        facade(
            "def original(a: int) -> int:\n    return a\n"
            "@wraps(original)\ndef f(a: int) -> int:\n    return a\n",
            "'f'",
            "from functools import wraps\n",
        ),
        {},
        "PASS",
        "",
    ),
    # A modeled form shows a class of the repository that no component declares.
    "contextmanager-secret": (
        facade(
            "@contextmanager\ndef f() -> Iterator[Secret]:\n    yield Secret()\n",
            "'f'",
            "from contextlib import contextmanager\nfrom collections.abc import Iterator\n"
            "from app.model import Secret\n",
        ),
        SECRET,
        "FAIL",
        "",
    ),
    "dataclass-secret-field": (
        facade(
            "@dataclass\nclass P:\n    secret: Secret\n",
            "'P'",
            "from dataclasses import dataclass\nfrom app.model import Secret\n",
        ),
        SECRET,
        "FAIL",
        "",
    ),
    # Forms that the survey does not model stay UNKNOWN, with the reason.
    "own-decorator": (
        facade(
            "def register(f):\n    return f\n@register\ndef f(a: int) -> int:\n    return a\n",
            "'f'",
        ),
        {},
        "UNKNOWN",
        "is no standard decorator that ArchKeel models",
    ),
    "contextmanager-iterable": (
        facade(
            "@contextmanager\ndef f(a: int) -> Iterable[int]:\n    yield a\n",
            "'f'",
            "from contextlib import contextmanager\nfrom collections.abc import Iterable\n",
        ),
        {},
        "UNKNOWN",
        "names no iterator or generator of a yield type",
    ),
    # Another module of the scan replaces the decorator.
    "changed-decorator": (
        facade(
            "@contextlib.contextmanager\ndef f(a: int) -> Iterator[int]:\n    yield a\n",
            "'f'",
            "import contextlib\nfrom collections.abc import Iterator\n",
        ),
        {"patch.py": "import contextlib\ncontextlib.contextmanager = lambda function: function\n"},
        "UNKNOWN",
        "may change the standard decorator contextlib.contextmanager",
    ),
    "dataclass-with-base": (
        facade(
            "class Base:\n    pass\n@dataclass\nclass P(Base):\n    x: int\n",
            "'P'",
            "from dataclasses import dataclass\n",
        ),
        {},
        "UNKNOWN",
        "a base or a metaclass can add fields",
    ),
    "broad-standard-type": (
        facade(
            "def f(a: Counter) -> int:\n    return 1\n",
            "'f'",
            "from collections import Counter\n",
        ),
        {},
        "UNKNOWN",
        "external_type",
    ),
    "sys-modules-from-import": (
        facade(
            "def f(a: Path) -> int:\n    return 1\n",
            "'f'",
            "from sys import modules\nfrom pathlib import Path\nmodules['pathlib'] = None\n",
        ),
        {},
        "UNKNOWN",
        "import_system_change: sys.modules",
    ),
    "vars-store": (
        facade(
            "def f(a: Path) -> int:\n    return 1\n",
            "'f'",
            "from pathlib import Path\n",
        ),
        {"patch.py": "import pathlib\nvars(pathlib)['Path'] = dict\n"},
        "UNKNOWN",
        "a store through vars",
    ),
    "exec-text": (
        facade(
            "def f(a: Path) -> int:\n    return 1\n",
            "'f'",
            "from pathlib import Path\nexec('import pathlib')\n",
        ),
        {},
        "UNKNOWN",
        "dynamic_import: exec",
    ),
}


def run(tmp_path: Path, core: Path, name: str, premise: bool) -> tuple[str, str]:
    api, files, _, _ = PLANTS[name]
    root = project(tmp_path / "p", Plant(api, "OPEN", files=files))
    if premise:
        use_standard_library_premise(root)
    result = json.loads(command(core, root, "--json").stdout)
    assert "refusal" not in result, result
    return result["frame"]["rules"][RULE][1], json.dumps(result)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_without_the_premise_every_plant_is_unknown(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    row, text = run(tmp_path, release_core, name, premise=False)
    assert row == "UNKNOWN", text
    expected = PLANTS[name][3]
    assert "standard_library_unchanged" in text or (expected and expected in text), text


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_with_the_premise_a_modeled_form_is_read(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    row, text = run(tmp_path, release_core, name, premise=True)
    expected, cause = PLANTS[name][2], PLANTS[name][3]
    assert row == expected, text
    assert cause in text, text
    if expected == "PASS":
        assert "the premise that outside code leaves the standard library unchanged" in text, text


TRUTH = """
import dataclasses, inspect, contextlib, functools
from dataclasses import KW_ONLY, dataclass, field

class Secret: pass

@dataclass
class P:
    x: int
    y: str = ''
    z: int = field(default=0, kw_only=True)
    hidden: Secret = field(init=False)
    _: KW_ONLY
    w: bool = False

@contextlib.contextmanager
def f(a: int):
    yield a

@functools.cache
def g(a: int) -> str:
    return ''

params = [(p.name, p.kind.name) for p in inspect.signature(P.__init__).parameters.values()]
print(params)
print(list(inspect.signature(f).parameters), list(inspect.signature(g).parameters))
"""


@pytest.mark.skipif(shutil.which("python3.12") is None, reason="needs python3.12 as the truth")
def test_the_modeled_signatures_are_the_signatures_of_cpython() -> None:
    done = subprocess.run(
        ["python3.12", "-I", "-c", TRUTH], capture_output=True, text=True, check=True
    )
    init, others = done.stdout.splitlines()
    # The dataclass plant: the receiver, the positional fields in order, then the keyword-only
    # fields (`field(kw_only=True)` and those after `KW_ONLY`); `field(init=False)` is no parameter.
    assert init == (
        "[('self', 'POSITIONAL_OR_KEYWORD'), ('x', 'POSITIONAL_OR_KEYWORD'), "
        "('y', 'POSITIONAL_OR_KEYWORD'), ('z', 'KEYWORD_ONLY'), ('w', 'KEYWORD_ONLY')]"
    )
    # contextmanager and cache keep the parameters of the function.
    assert others == "['a'] ['a']"
