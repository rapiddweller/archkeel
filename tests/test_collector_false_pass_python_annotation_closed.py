# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2156, #2157, AD-1175: the closed-binding rule for a module that evaluates annotations.

Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. `app/lib` appends a line
to a counter file when CPython loads it. Each plant makes CPython 3.12 load it (the counter is 1),
so the rule `NO-LIB` must be UNKNOWN or FAIL, never PASS. Each control makes CPython leave the
counter at 0 and the rule is PASS. A plant may bring more files of the project.
"""

from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path

import pytest
from python_interface_plants import Plant, build
from rust_repository import rule
from test_collector_false_pass_python_annotation_routes import _counter
from test_collector_false_pass_python_trojan_attribute import _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")

IMPORT = "__import__('app.lib')"
HEAD = "import types\nimport typing\n\n\n"
HINTS = "\n\ntry:\n    typing.get_type_hints(K)\nexcept Exception:\n    pass\n"
USE = "\n\nclass K:\n    x: {ref}\n"


def consumer(body: str, ref: str, head: str = HEAD) -> str:
    return head + body + USE.format(ref=ref) + HINTS


CFG = {"src/app/cfg.py": f's = "{IMPORT}"\n'}
PLANTS = {
    "receiver taint behind an unrelated held attribute": (
        consumer(
            f"class C:\n    s = 'int'\n\n\nbox = types.SimpleNamespace(s=str(\"{IMPORT}\"))\n",
            "box.s",
        ),
        {},
    ),
    "TypeVar bound is a string": (
        consumer(f"T = typing.TypeVar('T', bound=\"{IMPORT}\")\n", "T.__bound__"),
        {},
    ),
    "class attribute rebound by a store": (
        consumer(f"class C:\n    s = 'int'\n\n\nC.s = str(\"{IMPORT}\")\n", "C.s"),
        {},
    ),
    "class attribute set by a computed setattr": (
        consumer(
            f"class C:\n    s = 'int'\n\n\nname = 's'.strip()\nsetattr(C, name, \"{IMPORT}\")\n",
            "C.s",
        ),
        {},
    ),
    "name written through globals()": (
        consumer(f"globals()['s'] = \"{IMPORT}\"\n", "s"),
        {},
    ),
    "parameter used as annotation": (
        HEAD
        + "def make(s):\n    class K:\n        x: s\n\n    return K\n\n\n"
        + f'K = make("{IMPORT}")\n'
        + HINTS,
        {},
    ),
    "string of another module by from-import": (consumer("from app.cfg import s\n", "s"), CFG),
    "string of another module by module attribute": (
        consumer("import app.cfg as cfg\n", "cfg.s"),
        CFG,
    ),
    "string of another module by a relative import": (
        consumer("from .cfg import s\n", "s"),
        CFG,
    ),
    "string of another module through a re-export": (
        consumer("from app.mid import s\n", "s"),
        {**CFG, "src/app/mid.py": "from app.cfg import s\n"},
    ),
    "standard attribute written by another module": (
        consumer("import app.patch\nimport inspect\n", "inspect.Signature"),
        {"src/app/patch.py": f'import inspect\n\ninspect.Signature = "{IMPORT}"\n'},
    ),
    "standard name from-imported after a write": (
        consumer("import app.patch\nfrom inspect import Signature\n", "Signature"),
        {"src/app/patch.py": f'import inspect\n\ninspect.Signature = "{IMPORT}"\n'},
    ),
    "standard attribute set by setattr": (
        consumer("import app.patch\nimport inspect\n", "inspect.Signature"),
        {"src/app/patch.py": f'import inspect\n\nsetattr(inspect, "Signature", "{IMPORT}")\n'},
    ),
    "standard attribute set by a computed setattr": (
        consumer("import app.patch\nimport inspect\n", "inspect.Signature"),
        {
            "src/app/patch.py": "import inspect\n\nname = 'Sig' + 'nature'\n"
            f'setattr(inspect, name, "{IMPORT}")\n'
        },
    ),
    "string of another module through an alias": (
        consumer("from app.cfg import s as t\n", "t"),
        CFG,
    ),
}


def source(text: str) -> str:
    """A plant from plain text: `PAYLOAD` stands for the string that imports `app.lib`."""
    return HEAD + textwrap.dedent(text).replace("PAYLOAD", f'"{IMPORT}"') + HINTS


SCOPES = {
    "store in a function with the written value of that scope": source(
        """
        s = str(PAYLOAD)


        class C:
            s = 'int'


        def f():
            C.s = s


        f()


        class K:
            x: C.s
        """
    ),
    "scanned module member written by another module": (
        consumer(
            "import app.cfg as cfg\ncfg.s = str(PAYLOAD)\n".replace("PAYLOAD", f'"{IMPORT}"'),
            "cfg.s",
        ),
        {"src/app/cfg.py": "s = 'int'\n"},
    ),
    "standard module written through an alias": source(
        """
        import contextlib

        alias = contextlib
        alias.AbstractContextManager = str(PAYLOAD)


        class K:
            x: contextlib.AbstractContextManager
        """
    ),
    "standard module written through a parameter": source(
        """
        import inspect


        def patch(module):
            module.Signature = PAYLOAD


        patch(inspect)


        class K:
            x: inspect.Signature
        """
    ),
    "global declaration reads the module": source(
        """
        s = str(PAYLOAD)


        def outer():
            s = 'int'

            def inner():
                global s

                class K:
                    x: s

                return K

            return inner()


        K = outer()
        """
    ),
    "quoted annotation reads the module globals": source(
        """
        s = str(PAYLOAD)


        def make():
            s = 'int'

            def f(x: 's'):
                pass

            return f


        K = make()
        """
    ),
    "deleted override leaves the inherited string": source(
        """
        class B:
            pass


        B.s = str(PAYLOAD)


        class C(B):
            s = 'int'
            del s


        class K:
            x: C.s
        """
    ),
    "item of a standard mapping": source(
        """
        import os

        os.environ["HINT"] = PAYLOAD
        s = os.environ['HINT']


        class K:
            x: s
        """
    ),
    "nonlocal write through a function without the name": source(
        """
        def outer():
            s = 'int'

            def middle():
                def inner():
                    nonlocal s
                    s = PAYLOAD

                inner()

            middle()

            class K:
                x: s

            return K


        K = outer()
        """
    ),
    "global write of a local value": source(
        """
        s = 'int'


        def patch():
            global s
            value = str(PAYLOAD)
            s = value


        patch()


        class K:
            x: s
        """
    ),
    "class of another module written by its consumer": (
        consumer('from app.cfg import C\nC.s = str("' + IMPORT + '")\n', "C.s"),
        {"src/app/cfg.py": "class C:\n    s = 'int'\n"},
    ),
    "class text reads the module first": source(
        """
        s = str(PAYLOAD)


        class K:
            s = 'int'
            x: 's'
        """
    ),
    "postponed annotation reads the module globals": (
        "from __future__ import annotations\n\n"
        + source(
            """
            s = str(PAYLOAD)


            def make():
                s = 'int'

                def f(x: s):
                    pass

                return f


            K = make()
            """
        )
    ),
    "static method writes a module it gets": source(
        """
        import contextlib


        class Patch:
            @staticmethod
            def patch(module):
                module.AbstractContextManager = PAYLOAD


        Patch.patch(contextlib)


        class K:
            x: contextlib.AbstractContextManager
        """
    ),
    "name of the module written through an alias of the module": source(
        """
        import app.consumer as me

        s = 'int'
        me.s = str(PAYLOAD)


        class K:
            x: s
        """
    ),
    "class reads the outer name before its own assignment": source(
        """
        s = str(PAYLOAD)


        class K:
            x: s
            s = 'int'
        """
    ),
    "held text is read where the annotated class is evaluated": source(
        """
        class C:
            s = int
            hint = 's'


        class K:
            s = str(PAYLOAD)
            x: C.hint
        """
    ),
    "method called with a module as its first argument": source(
        """
        import contextlib


        class Patch:
            def patch(self):
                self.AbstractContextManager = PAYLOAD


        Patch.patch(contextlib)


        class K:
            x: contextlib.AbstractContextManager
        """
    ),
    "class replaced by its decorator": source(
        """
        class Evil:
            s = PAYLOAD


        def wrap(cls):
            return Evil


        @wrap
        class C:
            s = 'int'


        class K:
            x: C.s
        """
    ),
    "metaclass property wins over the class binding": source(
        """
        class Meta(type):
            s = property(lambda cls: str(PAYLOAD))


        class C(metaclass=Meta):
            s = 'int'


        class K:
            x: C.s
        """
    ),
    "class replaced by a decorator that a standard call makes": source(
        """
        import functools


        class Evil:
            s = PAYLOAD


        def wrap(cls):
            return Evil


        @functools.partial(wrap)
        class C:
            s = 'int'


        class K:
            x: C.s
        """
    ),
    "name created in the module through an alias of the module": source(
        """
        import app.consumer as me

        me.s = str(PAYLOAD)


        class K:
            x: s
        """
    ),
    "standard attribute written by a comprehension target": source(
        """
        import contextlib

        [None for contextlib.AbstractContextManager in [PAYLOAD]]


        class K:
            x: contextlib.AbstractContextManager
        """
    ),
    "metaclass given by unpacked keywords": source(
        """
        class Meta(type):
            s = property(lambda cls: str(PAYLOAD))


        class C(**{'metaclass': Meta}):
            s = 'int'


        class K:
            x: C.s
        """
    ),
    "class in a function reads the module, not the function local": source(
        """
        s = str(PAYLOAD)


        def make():
            s = 'int'

            class K:
                x: s
                s = 'int'

            return K


        K = make()
        """
    ),
    "module name created through an alias despite a class binding": source(
        """
        import app.consumer as me

        me.s = str(PAYLOAD)


        class K:
            s = 'int'
            x: 's'
        """
    ),
    "annotation without a value makes the name local to the class": source(
        """
        s = str(PAYLOAD)


        def make():
            s = 'int'

            class K:
                x: s
                s: int

            return K


        K = make()
        """
    ),
    "module of a standard alias re-exported by a scanned module": (
        consumer(
            'from app.cfg import alias\nalias.AbstractContextManager = str("' + IMPORT + '")\n',
            "contextlib.AbstractContextManager",
            HEAD + "import contextlib\n",
        ),
        {"src/app/cfg.py": "import contextlib as alias\n"},
    ),
    "inherited string next to an unrelated store": source(
        """
        class B:
            s = str(PAYLOAD)


        class C(B):
            pass


        class D:
            pass


        D.s = 'int'


        class K:
            x: C.s
        """
    ),
    "inherited string behind an annotation-only declaration": source(
        """
        class B:
            s = str(PAYLOAD)


        class C(B):
            s: int


        class K:
            x: C.s
        """
    ),
}

PLANTS.update(SCOPES)
CONTROLS = {
    "nine equal texts": (consumer("s = 'int'\n" * 9, "s"), {}),
    "class of another module": (
        consumer("from app.cfg import T\n", "T"),
        {"src/app/cfg.py": "class T:\n    pass\n"},
    ),
    "clean text of another module": (
        consumer("from app.cfg import s\n", "s"),
        {"src/app/cfg.py": "s = 'int'\n"},
    ),
    "module attribute class of another module": (
        consumer("import app.cfg as cfg\n", "cfg.T"),
        {"src/app/cfg.py": "class T:\n    pass\n"},
    ),
    "standard names without a write": (
        consumer(
            "import inspect\nimport contextlib\n", "inspect.Signature | contextlib.AsyncExitStack"
        ),
        {},
    ),
    "class of the standard decorator": (
        consumer(
            "import dataclasses\n\n\n@dataclasses.dataclass\nclass C:\n    n: int = 0\n\n\n",
            "C",
        ),
        {},
    ),
    "typing alias": (consumer("Alias = typing.Optional[int]\n", "Alias"), {}),
    "name of a parameter elsewhere": (
        HEAD + "def f(list):\n    return list\n\n\nclass K:\n    x: list[int]\n" + HINTS,
        {},
    ),
}


def _plant(entry: str | tuple[str, dict[str, str]]) -> tuple[str, dict[str, str]]:
    return (entry, {}) if isinstance(entry, str) else entry


def _root_with(tmp: Path, source: str, files: dict[str, str]) -> Path:
    root = tmp / "repo"
    root.mkdir(parents=True)
    extra = {"src/app/lib/__init__.py": "value = 1\n", **files}
    build(root, Plant("trojan", source, ("app.lib",), extra))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    forbidden = rule("NO-LIB", "forbidden_dependency", source="app.consumer", target="app.lib")
    forbidden["include_type_checking"] = True
    forbidden["provenance"] = ["docs/target.md"]
    contract["rules"] = [forbidden]
    path.write_text(json.dumps(contract))
    return root


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_binding_the_rule_cannot_close_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    source, files = _plant(PLANTS[name])
    root = _root_with(tmp_path, source, files)
    assert _counter(root) == 1, "CPython must load app.lib once: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_a_closed_binding_stays_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    source, files = CONTROLS[name]
    root = _root_with(tmp_path, source, files)
    assert _counter(root) == 0, "CPython must leave app.lib unloaded: the control is clean"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "PASS", frame


def test_a_third_party_name_is_a_site(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name of a third-party module has no record that proves it a class: UNKNOWN (AD-1175)."""
    source = consumer("from pydantic import BaseModel as D\n", "D")
    root = _root_with(tmp_path, source, {})
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "UNKNOWN", frame


def test_a_store_through_an_unknown_receiver_holds_the_standard_name(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cost of AD-1175: `self.date = 1` may write the attribute `date` of any module."""
    source = (
        HEAD
        + "import datetime\n\n\nclass A:\n    def __init__(self):\n        self.date = 1\n\n\n"
        + "class K:\n    x: datetime.date\n"
        + HINTS
    )
    root = _root_with(tmp_path, source, {})
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "UNKNOWN", frame
