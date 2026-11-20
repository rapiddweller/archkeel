# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The survey reports `any_annotation` only for a proven `typing.Any` that nothing replaces (#1833).

CPython is the truth: a FAIL is allowed only where the annotation of `x` is the object that the
interpreter ships as `typing.Any`. A true `typing.Any` that the survey cannot prove stays UNKNOWN
(a named gap), never PASS. Each plant runs in CPython first, then against the release core.
"""

import json
import subprocess
import sys
import typing
from pathlib import Path
from typing import NamedTuple

import pytest
from core_support import ROOT
from test_cli_native_python_imports import rows, verdict
from test_cli_python_profile_limits import CONSTRUCT, Plant, scanned

from tools.fixture_tree import fixture_tree

PAGE = "src/app/client/page.py"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
PROBE = "p.__annotations__['x']"


class Case(NamedTuple):
    files: dict[str, str]
    expected: str
    # True when CPython says the annotation of `x` is the `typing.Any` of the standard library.
    is_typing_any: bool
    # Code of the repository that runs before the page is imported.
    before: str = ""
    probe: str = PROBE


def page(source: str, **others: str) -> dict[str, str]:
    return {
        PAGE: source,
        **{f"src/{name.replace('__', '/')}.py": text for name, text in others.items()},
    }


CASES = {
    # A proven typing.Any stays FAIL.
    "from-typing": Case(page("from typing import Any\nx: Any = None\n"), FAIL, True),
    "typing-attribute": Case(page("import typing\nx: typing.Any = None\n"), FAIL, True),
    "typing-alias": Case(page("import typing as t\nx: t.Any = None\n"), FAIL, True),
    "star-from-typing": Case(page("from typing import *\nx: Any = None\n"), FAIL, True),
    "star-and-import": Case(
        page("from typing import *\nfrom typing import Any\nx: Any = None\n"), FAIL, True
    ),
    "typing-import-under-if": Case(
        page("if True:\n    import typing\nx: typing.Any = None\n"), FAIL, True
    ),
    # Another object under the name or the attribute.
    "nested-class-attribute": Case(
        page("class Outer:\n    class Any: pass\nx: Outer.Any = None\n"), UNKNOWN, False
    ),
    "other-module-attribute": Case(
        page("import other\nx: other.Any = None\n", other="class Any: pass\n"), UNKNOWN, False
    ),
    "other-star": Case(
        page("from other import *\nx: Any = None\n", other="class Any: pass\n"), UNKNOWN, False
    ),
    "star-then-local-class": Case(
        page("from typing import *\nclass Any: pass\nx: Any = None\n"), UNKNOWN, False
    ),
    "typing-rebound": Case(
        page("import typing\nclass typing:\n    Any = 1\nx: typing.Any = None\n"), UNKNOWN, False
    ),
    "class-scope-shadow": Case(
        page("from typing import Any\nclass C:\n    Any = int\n    x: Any = None\n"),
        UNKNOWN,
        False,
        probe="p.C.__annotations__['x']",
    ),
    "relative-typing-module": Case(
        page("from . import typing as t\nx: t.Any = None\n", app__client__typing="Any = int\n"),
        UNKNOWN,
        False,
    ),
    # The four counter-probes of the review: a replaced typing module.
    "scanned-module-typing": Case(
        page("import typing as t\nx: t.Any = None\n", typing="Any = int\n"), UNKNOWN, False
    ),
    "scanned-module-typing-extensions": Case(
        page("import typing_extensions as te\nx: te.Any = None\n", typing_extensions="Any = int\n"),
        UNKNOWN,
        False,
    ),
    "write-through-alias": Case(
        page("import typing as t\nt.Any = int\nx: t.Any = None\n"), UNKNOWN, False
    ),
    "write-in-another-scanned-module": Case(
        page(
            "import app.client.patch\nimport typing\nx: typing.Any = None\n",
            app__client__patch="import typing\ntyping.Any = int\n",
        ),
        UNKNOWN,
        False,
    ),
    "sys-modules-module-type": Case(
        page(
            "import sys\nimport types\nfake = types.ModuleType('typing')\nfake.Any = int\n"
            "sys.modules['typing'] = fake\nimport typing as t\nx: t.Any = None\n"
        ),
        UNKNOWN,
        False,
    ),
    "sys-modules-namespace": Case(
        page(
            "import sys\nimport types\nsys.modules['typing'] = types.SimpleNamespace(Any=int)\n"
            "import typing as t\nx: t.Any = None\n"
        ),
        UNKNOWN,
        False,
    ),
    "write-outside-the-scan": Case(
        {
            **page("import typing\nx: typing.Any = None\n"),
            "scripts/patch.py": ("import typing\ntyping.Any = int\n"),
        },
        UNKNOWN,
        False,
        before="import scripts.patch; ",
    ),
    "write-with-a-computed-name": Case(
        page(
            "import typing\nname = 'A' + 'ny'\nsetattr(typing, name, int)\nx: typing.Any = None\n"
        ),
        UNKNOWN,
        False,
    ),
    # The second review: the scan itself can change what `import typing` gives (#1835).
    "sys-modules-through-an-alias": Case(
        page(
            "import sys as s\nfrom types import SimpleNamespace\n"
            "s.modules['typing'] = SimpleNamespace(Any=int)\nimport typing as t\nx: t.Any = None\n"
        ),
        UNKNOWN,
        False,
    ),
    "sys-modules-in-a-function": Case(
        page(
            "from types import SimpleNamespace\ndef patch():\n"
            "    from sys import modules as cache\n"
            "    cache['typing'] = SimpleNamespace(Any=int)\npatch()\n"
            "import typing as t\nx: t.Any = None\n"
        ),
        UNKNOWN,
        False,
    ),
    "sys-path-before-a-local-typing": Case(
        {
            **page(
                "import sys\nsys.path.insert(0, 'hidden')\nimport typing as t\nx: t.Any = None\n"
            ),
            "hidden/typing.py": "Any = int\n",
        },
        UNKNOWN,
        False,
    ),
    # Safe controls: no site of the scan touches the import system.
    "unrelated-sys-use": Case(
        page("import sys\nARGS = sys.argv\nfrom typing import Any\nx: Any = None\n"), FAIL, True
    ),
    "path-append-of-a-clean-directory": Case(
        page(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.append(str(Path(__file__).resolve().parents[1]))\n"
            "from typing import Any\nx: Any = None\n"
        ),
        FAIL,
        True,
    ),
    # Named gaps: CPython says typing.Any, the survey has no sound basis and stays UNKNOWN.
    "local-class-then-star": Case(
        page("class Any: pass\nfrom typing import *\nx: Any = None\n"), UNKNOWN, True
    ),
    "aliased-any-in-container": Case(
        page("from typing import Any as Opaque\nx: list[Opaque]\n"),
        UNKNOWN,
        True,
        probe=f"{PROBE}.__args__[0]",
    ),
    "quoted-any-in-container": Case(
        page("from typing import Any\nx: list['Any']\n"),
        UNKNOWN,
        True,
        before="import typing; ",
        probe="typing.get_type_hints(p)['x'].__args__[0]",
    ),
    "typing-extensions-import": Case(
        page("from typing_extensions import Any\nx: Any = None\n"), UNKNOWN, True
    ),
    "typing-extensions-attribute": Case(
        page("import typing_extensions as te\nx: te.Any = None\n"), UNKNOWN, True
    ),
}


def cpython_says_typing_any(root: Path, case: Case) -> bool:
    for rel, text in case.files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    code = (
        f"import sys; sys.path[:0] = ['src', '.']; {case.before}"
        f"import app.client.page as p; print(repr({case.probe}))"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", code], cwd=root, capture_output=True, text=True, check=True
    )
    return done.stdout.strip() == repr(typing.Any)


@pytest.mark.parametrize("name", CASES)
def test_cpython_truth_of_each_plant(tmp_path: Path, name: str) -> None:
    case = CASES[name]
    assert cpython_says_typing_any(tmp_path, case) is case.is_typing_any


@pytest.mark.parametrize("name", CASES)
def test_any_annotation_needs_the_proof(release_core: Path, tmp_path: Path, name: str) -> None:
    case = CASES[name]
    rule = {**CONSTRUCT, "id": "NO-ANY", "constructs": ["any_annotation"]}
    result = scanned(release_core, tmp_path, Plant(case.files, [rule], [], {}, {}))
    status = rows(result)["NO-ANY"]
    assert status == case.expected, result["frame"]["explained"]
    assert status != FAIL or case.is_typing_any
    premise = result["frame"]["premise"]
    assert ("typing.Any unchanged" in premise) is (status == FAIL), premise


def test_a_name_without_a_binder_is_unknown(release_core: Path, tmp_path: Path) -> None:
    rule = {**CONSTRUCT, "id": "NO-ANY", "constructs": ["any_annotation"]}
    source = "from __future__ import annotations\nx: Any = None\n"
    result = scanned(release_core, tmp_path, Plant({PAGE: source}, [rule], [], {}, {}))
    assert rows(result)["NO-ANY"] == UNKNOWN, result["frame"]["explained"]


SHOP = ROOT / "fixtures/F-architecture"
SHOP_RULE = "CONSTRUCT-NO-ANY"


@pytest.mark.parametrize("premise", [True, False])
def test_shop_any_annotation_inventory_is_complete(release_core: Path, premise: bool) -> None:
    with fixture_tree(SHOP) as root:
        if not premise:
            path = root / "architecture-contract.json"
            contract = json.loads(path.read_text())
            del contract["declarations"]["premises"]
            path.write_text(json.dumps(contract))
        frame = verdict(release_core, root, "report")["frame"]
    status = "PASS" if premise else "UNKNOWN"
    assert frame["rules"][SHOP_RULE] == ["forbidden_construct", status]
    if premise:
        assert frame["premises"][SHOP_RULE][0]["kind"] == "standard_library_unchanged"


@pytest.mark.parametrize(
    "source",
    [
        "from typing import Any as Opaque\nx: list[Opaque]\n",
        "from typing import Any\nx: list['Any']\n",
        "from typing import Any\nAlias = Any\nx: Alias\n",
        "x: choose_a_type()\n",
        "x = None  # type: Missing\n",
        "from lib import Opaque\nx: Opaque\n",
        "class X(metaclass=meta): pass\nx: X\n",
        "import pathlib\npathlib.Path = str\n",
        "from dataclasses import dataclass\nimport typing as t\n"
        "def replace(**options): return lambda cls: getattr(t, 'Any')\n"
        "dataclass.__code__ = replace.__code__\n"
        "@dataclass(frozen=True, slots=True)\nclass Impostor: pass\nx: Impostor\n",
        "int = choose_a_type()\n",
        "class list: pass\n",
    ],
)
def test_shop_keeps_an_unresolved_annotation_unknown(release_core: Path, source: str) -> None:
    with fixture_tree(SHOP) as root:
        path = root / "shop/cli/main.py"
        path.write_text(path.read_text() + "\n" + source)
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"][SHOP_RULE] == ["forbidden_construct", "UNKNOWN"]


@pytest.mark.parametrize(
    "source",
    [
        'import typing\nclass __doc__: pass\nclass C:\n    "typing.Any"\n    x: __doc__\n',
        "import typing\nclass _C__x: pass\nclass C:\n    __x = 'typing.Any'\n    x: _C__x\n",
    ],
    ids=["implicit-docstring", "private-name-mangling"],
)
def test_implicit_class_binding_cannot_borrow_a_module_type(
    release_core: Path, tmp_path: Path, source: str
) -> None:
    probe = Case(
        page(source),
        UNKNOWN,
        True,
        before="import typing; ",
        probe="typing.get_type_hints(p.C)['x']",
    )
    assert cpython_says_typing_any(tmp_path, probe)
    with fixture_tree(SHOP) as root:
        (root / "shop/cli/docprobe.py").write_text(source)
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"][SHOP_RULE] == ["forbidden_construct", "UNKNOWN"]
