# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of the syntax half of `boundary_types` (AD-550).

A plant is a small project: the module `app/api.py` is the public facade of the component `api`,
and the rule `API-TYPES` checks the written types of its public signatures. `truth` is what the
written types mean when Python reads them: `PASS` (no position breaks the rule), `FAIL` (a
position does) or `OPEN` (the answer needs a fact that syntax does not give: a DTO field, an
alias, a type of another package). The core may answer UNKNOWN for any truth. It may answer PASS
only for `PASS` and FAIL only for `FAIL`. A 4.0.1 PASS where the truth is `FAIL` is a false PASS
of the release, and the core never repeats it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Plant:
    api: str
    truth: str
    files: dict[str, str] = field(default_factory=dict)
    allowed: tuple[dict[str, Any], ...] = ()
    public: tuple[str, ...] = ("app.api",)


def allow(name: str, position: str, annotation: str, **more: Any) -> dict[str, Any]:
    entry = {
        "qualified_name": f"app.api.{name}",
        "position": position,
        "field_path": "",
        "annotation": annotation,
    }
    return {**entry, **more}


def facade(body: str, names: str, imports: str = "") -> str:
    return f"{imports}{body}\n\n__all__ = [{names}]\n"


TYPING = "from typing import Annotated, Any, Literal, Optional, Sequence, Union\n"

PLANTS: dict[str, Plant] = {
    # Accepted forms.
    "primitives": Plant(
        facade("def f(a: int, b: str, c: bytes, d: bool, e: float) -> None:\n    pass\n", "'f'"),
        "PASS",
    ),
    "optional-and-union": Plant(
        facade(
            "def f(a: int | None, b: Optional[str], c: Union[int, str]) -> int | None:\n    pass\n",
            "'f'",
            TYPING,
        ),
        "PASS",
    ),
    "collections": Plant(
        facade(
            "def f(a: list[int], b: tuple[str, ...], c: Sequence[str], d: set[int]) -> list[str]:\n"
            "    return []\n",
            "'f'",
            TYPING,
        ),
        "PASS",
    ),
    "literal-and-annotated": Plant(
        facade(
            "def f(a: Literal['x', 'y'], b: Annotated[int, 'meta']) -> Literal[1]:\n    return 1\n",
            "'f'",
            TYPING,
        ),
        "PASS",
    ),
    "enum-parameter": Plant(
        facade(
            "class Color(Enum):\n    RED = 1\n\n\ndef f(a: Color) -> Color:\n    return a\n",
            "'f', 'Color'",
            "from enum import Enum\n",
        ),
        "PASS",
    ),
    "quoted-builtin": Plant(facade("def f(a: 'str') -> 'int':\n    return 1\n", "'f'"), "PASS"),
    "method-receiver-is-no-position": Plant(
        facade(
            "class Box:\n    def put(self, a: int) -> None:\n        pass\n\n"
            "    @classmethod\n    def make(cls, a: int) -> int:\n        return a\n\n"
            "    @staticmethod\n    def util(a: int) -> int:\n        return a\n",
            "'Box'",
        ),
        "PASS",
    ),
    "init-has-no-return-position": Plant(
        facade("class Box:\n    def __init__(self, a: int):\n        self.a = a\n", "'Box'"),
        "PASS",
    ),
    "private-names-are-not-the-surface": Plant(
        facade("def f(a: int) -> int:\n    return a\n\n\ndef _g(a):\n    return a\n", "'f'"),
        "PASS",
    ),
    # Failed forms.
    "bare-dict": Plant(facade("def f(a: dict) -> int:\n    return 1\n", "'f'"), "FAIL"),
    "dict-with-arguments": Plant(
        facade("def f(a: dict[str, int]) -> int:\n    return 1\n", "'f'"), "FAIL"
    ),
    "bare-object": Plant(facade("def f(a: object) -> int:\n    return 1\n", "'f'"), "FAIL"),
    "dict-in-a-list": Plant(
        facade("def f(a: list[dict[str, int]]) -> int:\n    return 1\n", "'f'"), "FAIL"
    ),
    "dict-in-a-union": Plant(facade("def f(a: int | dict) -> int:\n    return 1\n", "'f'"), "FAIL"),
    "dict-in-optional": Plant(
        facade("def f(a: Optional[dict]) -> int:\n    return 1\n", "'f'", TYPING), "FAIL"
    ),
    "undeclared-class": Plant(
        facade("def f(a: Hidden) -> int:\n    return 1\n", "'f'", "from app.inner import Hidden\n"),
        "FAIL",
        {"inner.py": "class Hidden:\n    pass\n"},
    ),
    "dict-method": Plant(
        facade("class Box:\n    def put(self, a: dict) -> None:\n        pass\n", "'Box'"), "FAIL"
    ),
    "dict-return": Plant(facade("def f() -> dict:\n    return {}\n", "'f'"), "FAIL"),
    "a-builtin-name-is-not-hidden-by-a-parameter": Plant(
        facade("def f(dict: int, a: dict) -> int:\n    return 1\n", "'f'"), "FAIL"
    ),
    # Named gaps: a verdict needs a fact that syntax does not give.
    "missing-annotation": Plant(facade("def f(a):\n    return a\n", "'f'"), "OPEN"),
    "variadics-without-annotations": Plant(
        facade("def f(*args, **kwargs) -> int:\n    return 1\n", "'f'"), "OPEN"
    ),
    "variadics-with-annotations": Plant(
        facade("def f(*args: int, **kwargs: str) -> int:\n    return 1\n", "'f'"), "PASS"
    ),
    "forward-reference": Plant(
        facade("def f(a: 'Later') -> int:\n    return 1\n\n\nclass Later:\n    pass\n", "'f'"),
        "OPEN",
    ),
    "user-generic": Plant(
        facade(
            "T = TypeVar('T')\n\n\nclass Box(Generic[T]):\n    pass\n\n\n"
            "def f(a: Box[int]) -> int:\n    return 1\n",
            "'f'",
            "from typing import Generic, TypeVar\n",
        ),
        "OPEN",
    ),
    "alias": Plant(
        facade("Alias = int\n\n\ndef f(a: Alias) -> int:\n    return 1\n", "'f'"), "OPEN"
    ),
    "alias-of-a-dict": Plant(
        facade("Alias = dict\n\n\ndef f(a: Alias) -> int:\n    return 1\n", "'f'"), "FAIL"
    ),
    "rebound-builtin": Plant(
        facade("int = dict\n\n\ndef f(a: int) -> int:\n    return 1\n", "'f'"), "FAIL"
    ),
    "external-type": Plant(
        facade("def f(a: Decimal) -> int:\n    return 1\n", "'f'", "from decimal import Decimal\n"),
        "OPEN",
    ),
    "dotted-name": Plant(
        facade("def f(a: decimal.Decimal) -> int:\n    return 1\n", "'f'", "import decimal\n"),
        "OPEN",
    ),
    "star-import-in-scope": Plant(
        facade("def f(a: Thing) -> int:\n    return 1\n", "'f'", "from app.other import *\n"),
        "OPEN",
        {"other.py": "class Thing:\n    pass\n"},
    ),
    "type-checking-import": Plant(
        facade(
            "def f(a: Thing) -> int:\n    return 1\n",
            "'f'",
            "from typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n    from app.other import Thing\n",
        ),
        "FAIL",
        {"other.py": "class Thing:\n    pass\n"},
    ),
    "declared-dto": Plant(
        facade("class Dto:\n    x: dict\n\n\ndef f(a: Dto) -> int:\n    return 1\n", "'f', 'Dto'"),
        "FAIL",
    ),
    "dataclass-dto": Plant(
        facade(
            "@dataclass\nclass Dto:\n    x: dict\n\n\ndef f(a: Dto) -> int:\n    return 1\n",
            "'f', 'Dto'",
            "from dataclasses import dataclass\n",
        ),
        "FAIL",
    ),
    "inherited-surface": Plant(
        facade(
            "class Base:\n    def put(self, a: dict) -> None:\n        pass\n\n\n"
            "class Box(Base):\n    pass\n",
            "'Box'",
        ),
        "FAIL",
    ),
    "decorated-function": Plant(
        facade(
            "@functools.cache\ndef f(a: int) -> int:\n    return a\n", "'f'", "import functools\n"
        ),
        "OPEN",
    ),
    "property-member": Plant(
        facade(
            "class Box:\n    @property\n    def value(self) -> dict:\n        return {}\n", "'Box'"
        ),
        "FAIL",
    ),
    "dynamic-exports": Plant(
        "def f(a: int) -> int:\n    return a\n\n\n__all__ = ['f'] + list(globals())\n", "OPEN"
    ),
    "facade-without-a-literal-all": Plant("def f(a: int) -> int:\n    return a\n", "OPEN"),
    "explicit-entry-needs-no-all": Plant(
        "def f(a: int) -> int:\n    return a\n", "PASS", public=("app.api:f",)
    ),
    "callable-type-with-a-dict": Plant(
        facade(
            "def f(a: Callable[[int], dict]) -> int:\n    return 1\n",
            "'f'",
            "from collections.abc import Callable\n",
        ),
        "OPEN",
    ),
    "any-type": Plant(
        facade("def f(a: Any) -> int:\n    return 1\n", "'f'", "from typing import Any\n"),
        "OPEN",
    ),
    "alias-of-a-literal": Plant(
        facade("NAME = 'x'\n\n\ndef f(a: NAME) -> int:\n    return 1\n", "'f'"), "OPEN"
    ),
    "dotted-chain": Plant(
        facade("def f(a: decimal.sub.Thing) -> int:\n    return 1\n", "'f'", "import decimal\n"),
        "OPEN",
    ),
    "literal-of-a-member": Plant(
        facade(
            "class Color(Enum):\n    RED = 1\n\n\n"
            "def f(a: Literal[Color.RED]) -> int:\n    return 1\n",
            "'f'",
            "from enum import Enum\nfrom typing import Literal\n",
        ),
        "PASS",
    ),
    "module-attribute-written-elsewhere": Plant(
        "from app.inner import f\n\n__all__ = ['f']\n",
        "OPEN",
        {
            "inner.py": "def f(a: dict) -> int:\n    return 1\n",
            "other.py": "import app.api as api\n\napi.f = lambda a: a\n",
        },
    ),
    "all-extended-later": Plant(
        facade(
            "def f(a: int) -> int:\n    return a\n\n\ndef g(a: dict) -> int:\n    return 1\n\n"
            "__all__.append('g')\n",
            "'f'",
        ),
        "FAIL",
    ),
    "facade-with-no-function": Plant(facade("X = 1\n", "'X'"), "OPEN"),
    "allowance-for-a-dict-of-strings": Plant(
        facade("def f(a: dict[str, str]) -> int:\n    return 1\n", "'f'"),
        "PASS",
        allowed=(allow("f", "a", "dict[str, str]"),),
    ),
    "unresolved-facade-entry": Plant(
        facade("def f(a: int) -> int:\n    return a\n", "'f'"),
        "OPEN",
        public=("app.api", "app.api:missing"),
    ),
    "reexport-through-the-facade": Plant(
        "from app.inner import f\n\n__all__ = ['f']\n",
        "FAIL",
        {"inner.py": "def f(a: dict) -> int:\n    return 1\n"},
    ),
    "reexport-of-a-clean-function": Plant(
        "from app.inner import f\n\n__all__ = ['f']\n",
        "PASS",
        {"inner.py": "def f(a: int) -> int:\n    return a\n"},
    ),
    # Allowances: exact exceptions of the contract.
    "allowance-for-a-bare-dict": Plant(
        facade("def f(a: dict) -> int:\n    return 1\n", "'f'"),
        "PASS",
        allowed=(allow("f", "a", "dict", native_mapping=True),),
    ),
    "allowance-exact-for-object": Plant(
        facade("def f(a: object) -> int:\n    return 1\n", "'f'"),
        "PASS",
        allowed=(allow("f", "a", "object"),),
    ),
    "allowance-for-a-nested-object-needs-a-depth": Plant(
        facade("def f(a: dict[str, object]) -> int:\n    return 1\n", "'f'"),
        "FAIL",
        allowed=(allow("f", "a", "dict[str, object]"),),
    ),
    "allowance-with-a-depth": Plant(
        facade("def f(a: dict[str, object]) -> int:\n    return 1\n", "'f'"),
        "PASS",
        allowed=(
            allow("f", "a", "dict[str, object]"),
            allow("f", "a", "dict[str, object]", container_depth=1),
        ),
    ),
    "allowance-with-a-wrong-text": Plant(
        facade("def f(a: object) -> int:\n    return 1\n", "'f'"),
        "FAIL",
        allowed=(allow("f", "a", "object | None"),),
    ),
    "allowance-for-another-position": Plant(
        facade("def f(a: object, b: object) -> int:\n    return 1\n", "'f'"),
        "FAIL",
        allowed=(allow("f", "a", "object"),),
    ),
    "allowance-with-a-field-path": Plant(
        facade("def f(a: int) -> int:\n    return 1\n", "'f'"),
        "PASS",
        allowed=(allow("f", "a", "int", field_path="x"),),
    ),
    "stale-allowance": Plant(
        facade("def f(a: int) -> int:\n    return 1\n", "'f'"),
        "PASS",
        allowed=(allow("f", "a", "object"),),
    ),
}
