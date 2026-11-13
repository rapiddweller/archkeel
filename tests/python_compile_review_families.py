# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""CPython rules and source families for the H1–H5 review of PR #1104."""

from __future__ import annotations

from textwrap import indent

RULES = {
    "H1": (
        "Python/compile.c:compiler_annassign/check_ann_subscr; "
        "3.14 Python/codegen.c:codegen_annassign/check_ann_subscr. "
        "Without a value, tuple subscript elements are checked individually, "
        "not as an unpacking tuple."
    ),
    "H2": (
        "Python/symtable.c:symtable_visit_stmt/symtable_raise_if_annotation_block/"
        "symtable_extend_namedexpr_scope. A walrus cannot bind in a type-parameter scope, "
        "including through comprehensions. Bounds, defaults, generic annotations and class bases "
        "use that scope; decorators, function defaults and bodies do not. Lambda bodies reset it."
    ),
    "H3": (
        "3.12 Python/symtable.c:symtable_visit_expr (Lambda_kind)/symtable_handle_comprehension. "
        "ste_can_see_class_scope rejects lambdas and comprehensions in a class-visible annotation "
        "scope. New function/class bodies reset that flag. "
        "Future-annotation blocks do not inherit it."
    ),
    "H4": (
        "3.13/3.14 Parser/pegen.c:_PyPegen_new_identifier rejects NFKC True/False/None in every "
        "identifier position. Strings and keyword constants are not identifier fields. "
        "__debug__: Python/compile.c:forbidden_name; 3.14 Python/symtable.c:check_name. "
        "An unaliased dotted import binds its first component; an alias replaces that binding."
    ),
    "H5": (
        "3.11/3.12 Python/future.c:future_parse and Python/compile.c:compiler_from_import; "
        "3.13/3.14 Python/symtable.c:check_import_from. A future import must lead the module. "
        "3.11/3.12 test the module name regardless of relative level; 3.13/3.14 require level zero."
    ),
}


def wrap(header: str, source: str) -> str:
    if not header:
        return source
    last = header.split("\n")[-1]
    padding = len(last) - len(last.lstrip()) + 1
    return header + "\n" + indent(source, " " * padding)


def scopes() -> dict[str, str]:
    return {
        "module": "",
        "function": "def outer():",
        "class": "class Outer:",
        "method": "class Outer:\n def method(self):",
        "class-if": "class Outer:\n if flag:",
    }


def annotated_targets() -> dict[str, str]:
    bodies = scopes() | {
        "async-function": "async def outer():",
        "if": "if flag:",
        "for": "for item in values:",
        "while": "while flag:",
        "with": "with manager:",
        "try": "try:",
        "generic-function": "def outer[T]():",
        "generic-class": "class Outer[T]:",
        "try-handler": "try:\n pass\nexcept E:",
        "try-else": "try:\n pass\nexcept E:\n pass\nelse:",
        "try-finally": "try:\n pass\nfinally:",
        "match-case": "match subject:\n case _:",
        "loop-else": "for item in values:\n pass\nelse:",
        "async-with": "async def outer():\n async with manager:",
    }
    targets = [
        "a[*b]",
        "a.b[*c]",
        "a[*b, c]",
        "(a[*b])",
        "a[(*b,)]",
        "a[0, (*b,)]",
        "a[*b, 1:2]",
        "a[1:*b]",
        "a[:: *b]",
        "a[[*b]]",
        "a[tuple((*b,))]",
        "a[(lambda: (*b,))()]",
        "a[[i for i in b]]",
        "a[*b][c]",
        "a[*b].field",
        "a",
        "a.field",
        "a[0]",
        "(a, b)",
    ]
    found = {}
    for scope, header in bodies.items():
        for index, target in enumerate(targets):
            for value in ("", " = 1"):
                for future in (False, True):
                    source = wrap(header, f"{target}: int{value}")
                    if scope == "try":
                        source += "\nfinally: pass"
                    prefix = "from __future__ import annotations\n" if future else ""
                    found[f"H1-{scope}-{index}-{bool(value)}-{future}"] = prefix + source
    return found


TYPE_POSITIONS = {
    "function-bound": "def f[T: EXPR](): pass",
    "class-bound": "class C[T: EXPR]: pass",
    "alias-bound": "type X[T: EXPR] = int",
    "constraints": "def f[T: (EXPR, int)](): pass",
    "function-type-default": "def f[T = EXPR](): pass",
    "class-type-default": "class C[T = EXPR]: pass",
    "alias-type-default": "type X[T = EXPR] = int",
    "tuple-type-default": "def f[*Ts = EXPR](): pass",
    "paramspec-default": "def f[**P = EXPR](): pass",
    "parameter-annotation": "def f[T](x: EXPR): pass",
    "keyword-annotation": "def f[T](*, x: EXPR): pass",
    "positional-only-annotation": "def f[T](x: EXPR, /): pass",
    "vararg-annotation": "def f[T](*args: EXPR): pass",
    "kwarg-annotation": "def f[T](**kwargs: EXPR): pass",
    "unpacked-vararg-annotation": "def f[T](*args: *tuple[EXPR]): pass",
    "return-annotation": "def f[T]() -> EXPR: pass",
    "positional-default": "def f[T](x=EXPR): pass",
    "keyword-default": "def f[T](*, x=EXPR): pass",
    "base": "class C[T](EXPR): pass",
    "metaclass": "class C[T](metaclass=EXPR): pass",
    "class-keyword": "class C[T](Base, k=EXPR): pass",
    "class-star-base": "class C[T](*(EXPR)): pass",
    "class-star-keyword": "class C[T](**(EXPR)): pass",
    "alias-value": "type X = EXPR",
    "generic-alias-value": "type X[T] = EXPR",
    "function-body": "def f[T]():\n x = EXPR",
    "class-body": "class C[T]:\n x = EXPR",
    "function-decorator": "@(EXPR)\ndef f[T](): pass",
    "class-decorator": "@(EXPR)\nclass C[T]: pass",
    "unpacked-tuple-default": "def f[*Ts = *tuple[EXPR]](): pass",
    "class-paramspec-default": "class C[**P = EXPR]: pass",
    "alias-tuple-default": "type X[*Ts = *tuple[EXPR]] = int",
    "ordinary-annotation": "x: EXPR = 1",
    "ordinary-parameter": "def f(x: EXPR): pass",
    "ordinary-return": "def f() -> EXPR: pass",
}


def type_scopes() -> dict[str, str]:
    expressions = [
        "(x := 1)",
        "[(x := i) for i in values]",
        "{(x := i) for i in values}",
        "{i: (x := i) for i in values}",
        "((x := i) for i in values)",
        "(lambda: (x := 1))",
        "(lambda x=(y := 1): x)",
    ]
    found = {}
    for scope, header in scopes().items():
        for position, template in TYPE_POSITIONS.items():
            for index, expression in enumerate(expressions):
                for future in (False, True):
                    prefix = "from __future__ import annotations\n" if future else ""
                    found[f"H2-{scope}-{position}-{index}-{future}"] = prefix + wrap(
                        header, template.replace("EXPR", expression)
                    )
    return found


def class_annotation_scopes() -> dict[str, str]:
    # The review publishes six examples and a 20-refused/5-valid count, not its source file.
    # Keep a 25-source seed with those examples, then cross the rule's scope positions.
    seeds = [
        "class C:\n type X = lambda: 1",
        "class C:\n type X = [i for i in z]",
        "class C:\n type X = {i for i in z}",
        "class C:\n type X = {i:i for i in z}",
        "class C:\n type X = (i for i in z)",
        "class C:\n type X[T] = lambda: 1",
        "class C:\n type X[T] = [i for i in z]",
        "class C:\n type X[T] = (i for i in z)",
        "class C:\n def f[T: (lambda: 1)](self): pass",
        "class C:\n def f[T: [i for i in z]](self): pass",
        "class C:\n def f[T: ((lambda: 1), int)](self): pass",
        "class C:\n def f[T](self, x: (lambda: 1)): pass",
        "class C:\n def f[T](self, x: [i for i in z]): pass",
        "class C:\n def f[T](self) -> (lambda: 1): pass",
        "class C:\n def f[T](self) -> [i for i in z]: pass",
        "class C:\n class D[T]((lambda: 1)): pass",
        "class C:\n class D[T](list[[i for i in z]]): pass",
        "class C:\n class D[T](metaclass=(lambda: 1)): pass",
        "class C:\n class D[T](k=[i for i in z]): pass",
        "class C:\n type X[T: (lambda: 1)] = int",
        "type X = lambda: 1",
        "def f():\n type X = [i for i in z]",
        "class C:\n def f[T](self, x=(lambda: 1)): pass",
        "class C:\n def f(self, x: (lambda: 1)): pass",
        "class C:\n x: (lambda: 1)",
    ]
    found = {f"H3-review-{index}": source for index, source in enumerate(seeds)}
    expressions = [
        "(lambda: 1)",
        "[i for i in z]",
        "{i for i in z}",
        "{i:i for i in z}",
        "(i for i in z)",
    ]
    positions = list(TYPE_POSITIONS)
    for scope, header in scopes().items():
        for position in positions:
            for index, expression in enumerate(expressions):
                for future in (False, True):
                    prefix = "from __future__ import annotations\n" if future else ""
                    found[f"H3-{scope}-{position}-{index}-{future}"] = prefix + wrap(
                        header, TYPE_POSITIONS[position].replace("EXPR", expression)
                    )
    return found


def names() -> dict[str, str]:
    positions = [
        "NAME",
        "NAME = 1",
        "NAME: int",
        "del NAME",
        "(NAME := 1)",
        "def NAME(): pass",
        "async def NAME(): pass",
        "class NAME: pass",
        "import NAME",
        "import NAME.a",
        "import a.NAME",
        "import a as NAME",
        "from NAME import a",
        "from a.NAME import b",
        "from a import NAME",
        "from a import b as NAME",
        "def f(NAME): pass",
        "def f(*NAME): pass",
        "def f(**NAME): pass",
        "def f(*, NAME): pass",
        "lambda NAME: 1",
        "lambda *NAME: 1",
        "value.NAME",
        "value.NAME = 1",
        "value.NAME += 1",
        "del value.NAME",
        "f(NAME=1)",
        "class C(NAME=1): pass",
        "global NAME",
        "nonlocal NAME",
        "for NAME in values: pass",
        "with manager as NAME: pass",
        "try: pass\nexcept E as NAME: pass",
        "[NAME for NAME in values]",
        "match value:\n case NAME: pass",
        "match value:\n case [*NAME]: pass",
        "match value:\n case {**NAME}: pass",
        "match value:\n case 1 as NAME: pass",
        "match value:\n case C(NAME=x): pass",
        "def f[NAME](): pass",
        "def f[*NAME](): pass",
        "def f[**NAME](): pass",
        "class C[NAME]: pass",
        "type NAME = int",
        "type X[NAME] = int",
        "def f(x: NAME) -> NAME: pass",
        "type X = NAME",
        "def f[T: NAME](): pass",
        "'NAME'",
        "f'{value.NAME}'",
        "match value:\n case {NAME: x}: pass",
        "match value:\n case value.NAME: pass",
        "try: pass\nexcept* E as NAME: pass",
        "async for NAME in values: pass",
        "async with manager as NAME: pass",
        "with manager as value.NAME: pass",
        "[(x, NAME) for x, NAME in values]",
        "@NAME\ndef f(): pass",
        "def f[T = NAME](): pass",
        "x: NAME = 1",
    ]
    spellings = [
        "Ｔrue",
        "Ｆalse",
        "Ｎone",
        "__dｅbug__",
        "𝕋rue",
        "True",
        "False",
        "None",
        "__debug__",
    ]
    found = {}
    for scope, header in (scopes() | {"async-function": "async def outer():"}).items():
        for index, template in enumerate(positions):
            for spelling, name in enumerate(spellings):
                found[f"H4-{scope}-{index}-{spelling}"] = wrap(
                    header, template.replace("NAME", name)
                )
    return found


def futures() -> dict[str, str]:
    wrappers = scopes() | {
        "if": "if flag:",
        "try": "try:",
        "with": "with manager:",
        "for": "for item in values:",
        "while": "while flag:",
        "async-function": "async def outer():",
        "nested-function": "def outer():\n def inner():",
        "try-handler": "try:\n pass\nexcept E:",
        "try-else": "try:\n pass\nexcept E:\n pass\nelse:",
        "try-finally": "try:\n pass\nfinally:",
        "match-case": "match subject:\n case _:",
        "loop-else": "for item in values:\n pass\nelse:",
    }
    modules = [
        "__future__",
        ".__future__",
        "..__future__",
        "...__future__",
        ". __future__",
        "a.__future__",
        ".a.__future__",
        "__future__.a",
    ]
    features = ["x", "annotations", "division", "braces", "*", "annotations as named"]
    found = {}
    for scope, header in wrappers.items():
        for index, module in enumerate(modules):
            for feature, name in enumerate(features):
                source = wrap(header, f"from {module} import {name}")
                if scope == "try":
                    source += "\nfinally: pass"
                found[f"H5-{scope}-{index}-{feature}"] = source
    return found


def families() -> dict[str, dict[str, str]]:
    return {
        "H1": {"H1-review": "a[*b]: int"} | annotated_targets(),
        "H2": {"H2-review": "class C[T](x := 1): pass"} | type_scopes(),
        "H3": class_annotation_scopes(),
        "H4": {"H4-review": "def Ｔrue(): pass"} | names(),
        "H5": {"H5-review": "def f():\n from . __future__ import x"} | futures(),
    }


def outcome(source: str) -> list[str] | None:
    try:
        compile(source, "p.py", "exec", dont_inherit=True)
    except (
        SyntaxError,
        ValueError,
        OverflowError,
        RecursionError,
        MemoryError,
        UnicodeError,
    ) as error:
        return [type(error).__name__, getattr(error, "msg", str(error))]
    return None
