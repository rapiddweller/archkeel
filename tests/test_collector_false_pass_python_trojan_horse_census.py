# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1963: the trojan horse census proofs never turn an open import trojan horse into PASS.

Consumer: `archkeel validate`. Each plant runs in Python 3.12 (`python3.12 -I`), which shows the
real effect. A plant that the proof must keep open (`STAY`) really rebinds a name or really imports
`app.lib`, and its rule is UNKNOWN or FAIL, never PASS. A control that the proof clears (`CLEAR`)
does the same harmless thing, and its rule is PASS. S1 (AD-1049): outside code that loads a file
under a foreign module name.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import run
from python_interface_plants import Plant, build

from archkeel.cli import core_only

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

LIBRARY = {
    "src/app/lib/__init__.py": "from app.lib.pub import f\n",
    "src/app/lib/pub.py": "def f(): return 'public'\n",
    "tools/alt.py": "def f(): return 'private'\n",
}
CONSUMER = "from app.lib import f\n"
ENTRY = "import app.consumer\nprint(app.consumer.f())\n"
# The other file under the name of the module of the scan, or under a foreign name.
LOAD = (
    "import importlib.util, sys\n"
    "spec = importlib.util.spec_from_file_location({name}, 'tools/alt.py')\n"
    "mod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\n"
)
PREPARE = "import sys; sys.path[:0] = ['src']; import runpy; runpy.run_path('tools/run.py')"


def _verdict(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    script: str,
    expected: str,
) -> str:
    """The rule `BOUNDARY` for a script outside the scan; asserts what Python 3.12 prints."""
    root = tmp_path / "repo"
    root.mkdir()
    files = {**LIBRARY, "tools/run.py": script + ENTRY}
    build(root, Plant("loader", CONSUMER, ("app.lib.pub",), files))
    truth = subprocess.run(
        ["python3.12", "-I", "-c", PREPARE], cwd=root, capture_output=True, text=True
    )
    assert truth.returncode == 0, truth.stderr
    assert truth.stdout.strip() == expected, truth.stdout
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    return run("validate", "--root", str(root))[1]["frame"]["rules"]["BOUNDARY"][1]


STAY = {
    # AD-1049 (M1 of the counter-example run): a name below, above or computed from a variable
    # can still name a module of the scan, so the foreign-name proof must refuse each of them.
    "the spec name is below a module of the scan": (
        LOAD.format(name="'app.lib.pub'") + "sys.modules['app.lib'] = mod\n",
        "private",
    ),
    "the spec name is a package above a module of the scan": (
        LOAD.format(name="'app'") + "mod.__path__ = []\nsys.modules['app.lib'] = mod\n",
        "private",
    ),
    "the spec name comes from a variable": (
        "NAME = 'app.' + 'lib'\n" + LOAD.format(name="NAME") + "sys.modules[NAME] = mod\n",
        "private",
    ),
    "the spec name is a relative form": (
        LOAD.format(name="'.lib'") + "sys.modules['app.lib'] = mod\n",
        "private",
    ),
    "the spec has the name of a module of the scan": (
        LOAD.format(name="'app.lib'") + "sys.modules['app.lib'] = mod\n",
        "private",
    ),
    "the module of the scan is the target of the loader": (
        "import app.lib\n"
        + LOAD.format(name="'smoke'")
        + "spec.loader.name = 'app.lib'\nspec.loader.exec_module(app.lib)\n",
        "private",
    ),
    "a foreign spec and a store into the module of the scan": (
        LOAD.format(name="'smoke'") + "import app.lib\napp.lib.f = mod.f\n",
        "private",
    ),
    "a foreign spec and the module put in the state of the import system": (
        LOAD.format(name="'smoke'") + "sys.modules['app.lib'] = mod\n",
        "private",
    ),
}


@pytest.mark.parametrize("name", sorted(STAY))
def test_a_loader_that_can_rebind_a_module_of_the_scan_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    script, expected = STAY[name]
    verdict = _verdict(tmp_path, release_core, monkeypatch, script, expected)

    assert verdict in {"FAIL", "UNKNOWN"}, name


def test_a_loader_under_a_foreign_name_that_writes_nothing_clears(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = "PACKAGE = 'app'\n" + LOAD.format(name="'smoke_selection'") + "mod.f()\n"
    verdict = _verdict(tmp_path, release_core, monkeypatch, script, "public")

    assert verdict == "PASS"


# S2 (AD-1050): names and strings that a trojan horse list matches but that run no import.
FORBIDDEN = {
    "id": "NO-IMPORT",
    "kind": "forbidden_dependency",
    "rationale": "The consumer must not depend on the library.",
    "provenance": ["docs/target.md"],
    "decided_by": "architect",
    "source": "app.consumer",
    "target": "app.lib",
    "include_type_checking": True,
}
LIB = {"src/app/lib/__init__.py": "value = 1\n"}
TRUTH = (
    "import sys; sys.path[:0] = ['src']; import app.consumer; "
    "getattr(app.consumer, 'run', lambda: None)(); print('app.lib' in sys.modules)"
)


def _dependency(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    consumer: str,
    imports: bool,
) -> tuple[str, set[tuple[str, int]]]:
    """The rule NO-IMPORT and the gaps (detail, line) of the consumer; asserts the real import."""
    root = tmp_path / "repo"
    root.mkdir()
    build(root, Plant("census", consumer, ("app.lib",), LIB))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["rules"] = [FORBIDDEN]
    path.write_text(json.dumps(contract))
    truth = subprocess.run(
        ["python3.12", "-W", "ignore", "-I", "-c", TRUTH], cwd=root, capture_output=True, text=True
    )
    assert truth.returncode == 0, truth.stderr
    assert truth.stdout.strip() == str(imports), truth.stdout
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    frame = run("validate", "--root", str(root))[1]["frame"]
    lines = {key: found["line"] for key, found in frame["locations"].items()}
    gaps = {
        (gap["reason"].split(": ", 1)[-1], lines[key])
        for gap in frame["collection_gaps"]
        if gap["reason"].startswith(("dynamic_import", "import_system_change"))
        for key in gap["evidence"]
    }
    return frame["rules"]["NO-IMPORT"][1], gaps


def _code_args() -> str:
    """The arguments of `CodeType` for the code of `import app.lib` (Python 3.12 oracle)."""
    script = (
        "c = compile('import app.lib', '<p>', 'exec')\n"
        "print((c.co_argcount, c.co_posonlyargcount, c.co_kwonlyargcount, c.co_nlocals,"
        " c.co_stacksize, c.co_flags, c.co_code, c.co_consts, c.co_names, c.co_varnames,"
        " c.co_filename, c.co_name, c.co_qualname, c.co_firstlineno, c.co_linetable,"
        " c.co_exceptiontable))"
    )
    done = subprocess.run(["python3.12", "-I", "-c", script], capture_output=True, text=True)
    return done.stdout.strip()


S2_STAY = {
    "a code type attribute in an annotation and a constructor call": lambda: (
        "import types\ndef f(c: types.CodeType) -> None: ...\n"
        "ok = isinstance(f, types.FunctionType)\n"
        f"def run():\n    types.FunctionType(types.CodeType(*{_code_args()}), {{}})()\n"
    ),
    "a code type in an annotation and a constructor call": lambda: (
        "from types import CodeType, FunctionType\n"
        "def f(c: CodeType) -> None: ...\n"
        f"def run():\n    FunctionType(CodeType(*{_code_args()}), {{}})()\n"
    ),
    "a literal test of sys.modules and a read of sys.modules": lambda: (
        "import sys\nok = 'numpy' in sys.modules\n"
        "def run():\n    sys.modules['builtins'].__import__('app.lib')\n"
    ),
    "a literal test of sys.modules and an alias of the state": lambda: (
        "import sys\nok = 'numpy' in sys.modules\nstate = sys.modules\n"
        "def run():\n    state['builtins'].__import__('app.lib')\n"
    ),
    "the key view of globals and a read of globals": lambda: (
        "names = sorted(set(globals().keys()))\n"
        "def run():\n    globals()['__builtins__']['__import__']('app.lib')\n"
    ),
    "the key view of globals and an alias of globals": lambda: (
        "names = sorted(set(globals().keys()))\nhold = globals\n"
        "def run():\n    hold()['__builtins__']['__import__']('app.lib')\n"
    ),
    "a spec that is tested and a spec that gives its loader": lambda: (
        "def run(m=__import__('app')):\n    s = m.__spec__\n"
        "    if s is None or s.submodule_search_locations is None:\n        return\n"
        "    s.loader.name = 'app.lib'\n    s.loader.path = 'src/app/lib/__init__.py'\n"
        "    s.loader.load_module()\n"
    ),
    "a pickler of a function whose module name was written": lambda: (
        "import pickle\ndef f(): ...\n"
        "def run():\n    f.__module__ = 'app.lib'\n"
        "    try:\n        pickle.dumps(f)\n    except Exception:\n        pass\n"
    ),
    # The string rules S1 to S4 of the census are not built: a class with `__ne__` collects the
    # strings that the compare sees (AD-1050). The plants keep the verdict open.
    "a class that collects the strings of a compare": lambda: (
        "class K:\n    seen = []\n    def __ne__(self, other):\n        K.seen.append(other)\n"
        "        if len(K.seen) == 2:\n"
        "            getattr(getattr(len, K.seen[0]), K.seen[1])('app.lib')\n"
        "        return True\n"
        "k = K()\nk != '__self__'\nk != '__import__'\n"
    ),
    "a trojan horse string in a set that a loop passes on": lambda: (
        "NAMES = {'__self__', '__import__'}\n"
        "def run():\n    a, b = sorted(NAMES, reverse=True)\n"
        "    getattr(getattr(len, a), b)('app.lib')\n"
    ),
    "a trojan horse string in a variable that reaches getattr": lambda: (
        "def run():\n    a = '__self__'\n    b = '__import__'\n"
        "    if a != 'x':\n        getattr(getattr(len, a), b)('app.lib')\n"
    ),
}


@pytest.mark.parametrize("name", sorted(S2_STAY))
def test_a_name_that_still_reaches_an_import_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    verdict, _ = _dependency(tmp_path, release_core, monkeypatch, S2_STAY[name](), True)

    assert verdict in {"FAIL", "UNKNOWN"}, name


# Each control does the same harmless thing, imports nothing and loses the gap of its form.
S2_CLEAR = {
    "sys.modules": (
        "import sys\nok = 'numpy' in sys.modules\nmissing = 'pandas' not in sys.modules\n"
    ),
    "globals": "def names():\n    return sorted(set(globals().keys()))\n",
    "__spec__": (
        "import pkgutil\n"
        "def run(package=pkgutil):\n    s = package.__spec__\n"
        "    if s is None or s.submodule_search_locations is None:\n        return []\n"
        "    return [n for _, n, _ in pkgutil.walk_packages(\n"
        "        s.submodule_search_locations, s.name + '.')]\n"
    ),
    "types.CodeType": (
        "from types import CodeType\n"
        "def f(c):\n    x: CodeType | None = None\n    y: list[CodeType] = []\n    return x, y\n"
    ),
    "types.CodeType attribute": (
        "import types\n"
        "def f(c):\n    z: list[types.FunctionType] = []\n"
        "    return [x for x in [c] if isinstance(x, types.CodeType)], z\n"
    ),
}


@pytest.mark.parametrize("detail", sorted(S2_CLEAR))
def test_a_proven_inert_form_loses_its_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, detail: str
) -> None:
    verdict, gaps = _dependency(tmp_path, release_core, monkeypatch, S2_CLEAR[detail], False)
    first = S2_CLEAR[detail].splitlines()
    detail = detail.split(" ")[0]

    # `from types import CodeType` and `import pkgutil` keep their own gap (AD-574).
    assert not {line for found, line in gaps if found == detail and first[line - 1][:4] != "from"}
    if detail in {"sys.modules", "globals", "types.CodeType"} and "import types" in first[0]:
        assert verdict == "PASS", gaps
    if detail in {"sys.modules", "globals"}:
        assert verdict == "PASS", gaps
