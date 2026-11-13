# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Generated families for public CPython Grammar/python.gram invalid rules.

Keys name the CPython rule, not a diagnostic string. Each seed exercises a rule
alternative. The test expands statements across suites and expression positions.
Type-comment rules are separate: compile without PyCF_TYPE_COMMENTS cannot reach them.
"""

from __future__ import annotations

from textwrap import indent


def seeds() -> dict[str, list[str]]:
    found = {
        "invalid_arguments": [
            "f(**d, *xs)",
            "f(x for x in xs, y)",
            "f(x=1 for x in xs)",
            "f(x=)",
            "f(1, x for x in xs)",
        ],
        "invalid_kwarg": [
            "f(True=1)",
            "f(False=1)",
            "f(None=1)",
            "f(x=1 for x in xs)",
            "f(a.b=1)",
            "f(**d=1)",
        ],
        "invalid_legacy_expression": ["print x", "exec x"],
        "invalid_expression": [
            "['a' x 'b']",
            "[a b]",
            "a if b",
            "a if b else pass",
            "pass if b else a",
            "f'{lambda:1}'",
            "t'{lambda:1}'",
        ],
        "invalid_named_expression": ["(a.b := 1)", "if a = 1:\n pass", "if a.b = 1:\n pass"],
        "invalid_assignment": [
            "[a,b]: int",
            "(a,b): int",
            "a,b: int",
            "f(): int",
            "a = f() = 1",
            "yield x = 1",
            "f() += 1",
        ],
        "invalid_del_stmt": ["del f()", "del [a, f()]", "del (a, *b)"],
        "invalid_block": ["if x:\npass"],
        "invalid_comprehension": [
            "[*x for x in xs]",
            "(*x for x in xs)",
            "{*x for x in xs}",
            "[x,y for x in xs]",
            "{x,y for x in xs}",
            "[x, for x in xs]",
        ],
        "invalid_dict_comprehension": ["{**x for x in xs}"],
        "invalid_default": ["def f(x=): pass", "def f(x=, y=1): pass"],
        "invalid_with_item": ["with x as f(): pass", "with (x as f(),): pass"],
        "invalid_for_target": ["for f() in xs: pass", "[x for f() in xs]"],
        "invalid_for_if_clause": ["[x for x xs]", "[x async for x xs]"],
        "invalid_group": ["(*x)", "(**x)"],
        "invalid_import": ["import a from b", "import\n"],
        "invalid_dotted_as_name": ["import a as b.c", "import a as 1"],
        "invalid_import_from_as_name": ["from a import b as c.d", "from a import b as 1"],
        "invalid_import_from_targets": ["from a import b,\n", "from a import\n"],
        "invalid_with_stmt": ["with x\n pass", "with (x,y)\n pass", "async with x\n pass"],
        "invalid_with_stmt_indent": ["with x:\npass", "with (x,y):\npass", "async with x:\npass"],
        "invalid_try_stmt": [
            "try:\npass",
            "try:\n pass\nx=1",
            "try:\n pass\nexcept E:\n pass\nexcept* F:\n pass",
            "try:\n pass\nexcept* E:\n pass\nexcept F:\n pass",
        ],
        "invalid_except_stmt": [
            "try:\n pass\nexcept E,F as e:\n pass",
            "try:\n pass\nexcept E\n pass",
            "try:\n pass\nexcept\n pass",
            "try:\n pass\nexcept E as a.b:\n pass",
            "try:\n pass\nexcept*:\n pass",
        ],
        "invalid_except_star_stmt": [
            "try:\n pass\nexcept* E,F as e:\n pass",
            "try:\n pass\nexcept* E\n pass",
            "try:\n pass\nexcept*:\n pass",
            "try:\n pass\nexcept*\n pass",
            "try:\n pass\nexcept* E as a.b:\n pass",
        ],
        "invalid_finally_stmt": ["try:\n pass\nfinally:\npass"],
        "invalid_except_stmt_indent": [
            "try:\n pass\nexcept E:\npass",
            "try:\n pass\nexcept:\npass",
        ],
        "invalid_except_star_stmt_indent": ["try:\n pass\nexcept* E:\npass"],
        "invalid_match_stmt": ["match x\n pass", "match x:\npass"],
        "invalid_case_block": ["match x:\n case _\n  pass", "match x:\n case _:\n pass"],
        "invalid_as_pattern": [
            "match x:\n case 1 as _: pass",
            "match x:\n case 1 as a.b: pass",
            "match x:\n case 1 as 2: pass",
        ],
        "invalid_class_pattern": ["match x:\n case C(a=x, y): pass"],
        "invalid_if_stmt": ["if x\n pass", "if x:\npass"],
        "invalid_elif_stmt": ["if x:\n pass\nelif y\n pass", "if x:\n pass\nelif y:\npass"],
        "invalid_else_stmt": [
            "if x:\n pass\nelse:\npass",
            "if x:\n pass\nelse:\n pass\nelif y:\n pass",
        ],
        "invalid_while_stmt": ["while x\n pass", "while x:\npass"],
        "invalid_for_stmt": [
            "for x in xs\n pass",
            "for x in xs:\npass",
            "async for x in xs:\npass",
        ],
        "invalid_def_raw": ["def f():\npass", "async def f():\npass", "def f()\n pass"],
        "invalid_class_def_raw": ["class C\n pass", "class C:\npass", "class C(B)\n pass"],
        "invalid_double_starred_kvpairs": ["{x: *y}", "{x:}", "{x:, y:1}"],
        "invalid_kvpair": ["{a:1, b}", "{a:1, b:*c}", "{a:1, b:}"],
        "invalid_starred_expression_unpacking": ["f(*x=1)"],
        "invalid_starred_expression": ["[*]", "{*}", "f(*)"],
        "invalid_factor": ["-not x", "+not x", "~not x"],
        "invalid_type_params": ["def f[](): pass", "class C[]: pass", "type X[] = int"],
        "invalid_type_param": [
            "def f[*T: int](): pass",
            "def f[*T: (int,str)](): pass",
            "def f[**P: int](): pass",
            "def f[**P: (int,str)](): pass",
        ],
        "type_param_seq": [
            "def f[T=int, U](): pass",
            "class C[T=int, U]: pass",
            "type X[T=int, U] = int",
        ],
        "invalid_string_tstring_concat": ["t'x' 'y'", "'x' t'y'", "t'x' f'y'", "f'x' t'y'"],
    }
    params = ["/,x", "x,/,y,/", "x=1,y", "(x,y)", "*x,y,/", "x,/*y"]
    stars = ["*", "*,", "*,**x", "*x=1", "*x,*y", "*,x,*y"]
    kwds = ["**x=1", "**x,y", "**x,*y", "**x,**y", "**x,/"]
    for suffix, items in (("parameters", params), ("star_etc", stars), ("kwds", kwds)):
        found[f"invalid_{suffix}"] = [f"def f({item}): pass" for item in items]
        found[f"invalid_lambda_{suffix}"] = [f"lambda {item}: 1" for item in items]
    fields = ["{=}", "{!}", "{:}", "{}", "{+}", "{x y}", "{x?}", "{x= y}", "{x!r y}", "{x:!", "{x"]
    for prefix in ("f", "t"):
        found[f"invalid_{prefix}string_replacement_field"] = [
            f"{prefix}'{field}'" for field in fields
        ]
        found[f"invalid_{prefix}string_conversion_character"] = [
            f"{prefix}'{{x!}}'",
            f"{prefix}'{{x!:}}'",
            f"{prefix}'{{x!1}}'",
        ]
    # These rule names change between the pinned minors; their predicates do not.
    found["invalid_replacement_field"] = found["invalid_fstring_replacement_field"]
    found["invalid_conversion_character"] = found["invalid_fstring_conversion_character"]
    found["starred_expression"] = found["invalid_starred_expression"]
    found["invalid_starred_expression"] += found["invalid_starred_expression_unpacking"]
    found["for_if_clause"] = found["invalid_for_if_clause"]
    found["type_param_seq"] += found["invalid_type_param"]
    return found


POSITIONS = {
    "module": "",
    "function": "def outer():",
    "async-function": "async def outer():",
    "class": "class Outer:",
    "method": "class Outer:\n def method(self):",
    "if": "if flag:",
    "while": "while flag:",
    "for": "for item in items:",
    "with": "with manager:",
    "try-finally": "try:\n pass\nfinally:",
    "handler": "try:\n pass\nexcept E:",
    "match": "match value:\n case _:",
    "else": "if flag:\n pass\nelse:",
    "elif": "if flag:\n pass\nelif other:",
    "loop-else": "for item in items:\n pass\nelse:",
    "try": "try:",
    "try-else": "try:\n pass\nexcept E:\n pass\nelse:",
    "async-with": "async def outer():\n async with manager:",
    "async-for": "async def outer():\n async for item in items:",
    "generic-function": "def outer[T]():",
    "generic-class": "class Outer[T]:",
}


def neighbours() -> dict[str, str]:
    return {
        "invalid_arguments": "f(*(x for x in xs), **d)",
        "invalid_kwarg": "f(True == 1, a=1, **d)",
        "invalid_legacy_expression": "print(x); exec(x)",
        "invalid_expression": "['a', x, 'b']; a if b else c",
        "invalid_named_expression": "if (a := 1): pass",
        "invalid_assignment": "a: int; a = b = 1; a += 1",
        "invalid_del_stmt": "del a, b.c, d[0]",
        "invalid_comprehension": "[(x,y) for x in xs]",
        "invalid_dict_comprehension": "{x:y for x in xs}",
        "invalid_parameters": "def f(x,/,y=1,*,z=2): pass",
        "invalid_lambda_parameters": "lambda x,/,y=1,*,z=2: x",
        "invalid_default": "def f(x=1): pass",
        "invalid_star_etc": "def f(*args, x, **kwargs): pass",
        "invalid_lambda_star_etc": "lambda *args,x,**kwargs: x",
        "invalid_kwds": "def f(**kwargs): pass",
        "invalid_lambda_kwds": "lambda **kwargs: 1",
        "invalid_with_item": "with x as a.b: pass",
        "invalid_for_target": "for a.b in xs: pass",
        "invalid_group": "(*x,); {**x}",
        "invalid_import": "from a import b",
        "invalid_dotted_as_name": "import a.b as c",
        "invalid_import_from_as_name": "from a import b as c",
        "invalid_import_from_targets": "from a import (b,)",
        "invalid_with_stmt": "with (x,y): pass",
        "invalid_try_stmt": "try:\n pass\nexcept E:\n pass",
        "invalid_except_stmt": "try:\n pass\nexcept (E,F) as e:\n pass",
        "invalid_except_star_stmt": "try:\n pass\nexcept* (E,F) as e:\n pass",
        "invalid_match_stmt": "match x:\n case _: pass",
        "invalid_case_block": "match x:\n case _: pass",
        "invalid_as_pattern": "match x:\n case 1 as name: pass",
        "invalid_class_pattern": "match x:\n case C(y,a=z): pass",
        "invalid_if_stmt": "if x: pass",
        "invalid_elif_stmt": "if x:\n pass\nelif y:\n pass",
        "invalid_else_stmt": "if x:\n pass\nelse:\n pass",
        "invalid_while_stmt": "while x: pass",
        "invalid_for_stmt": "for x in xs: pass",
        "invalid_def_raw": "def f(): pass",
        "invalid_class_def_raw": "class C(B): pass",
        "invalid_double_starred_kvpairs": "{x:y, **z}",
        "invalid_kvpair": "{a:1, b:2}",
        "invalid_starred_expression_unpacking": "f(*x)",
        "invalid_starred_expression": "[*x]",
        "starred_expression": "[*x]",
        "invalid_factor": "-(not x)",
        "invalid_type_params": "def f[T](): pass",
        "invalid_type_param": "def f[T: int, *Ts, **P](): pass",
        "type_param_seq": "def f[T, U=int](): pass",
        "invalid_string_tstring_concat": "t'x' t'y'",
    }


def family(rule: str) -> dict[str, str]:
    found = {}
    for index, seed in enumerate(seeds()[rule]):
        for position, header in POSITIONS.items():
            padding = len(header.rsplit("\n", 1)[-1]) - len(header.rsplit("\n", 1)[-1].lstrip()) + 1
            source = header + "\n" + indent(seed, " " * padding) if header else seed
            if position == "try":
                source += "\nfinally: pass"
            for prefix in ("", "from __future__ import annotations\n"):
                found[f"{rule}-{index}-{position}-{bool(prefix)}"] = prefix + source
    if rule in neighbours():
        seed = neighbours()[rule]
        for position in ("module", "function", "class", "method", "if"):
            header = POSITIONS[position]
            padding = len(header.rsplit("\n", 1)[-1]) - len(header.rsplit("\n", 1)[-1].lstrip()) + 1
            found[f"{rule}-valid-{position}"] = (
                header + "\n" + indent(seed, " " * padding) if header else seed
            )
    return found
