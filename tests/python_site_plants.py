# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of the Python symbol sites (AD-520): the hard forms of scope and of writes.

Each plant plans one relationship (or closes a kind). The truth is whether Python makes it hold
when the module runs: `PASS` or `DIFF`. The rows of release 4.0.1 and of the core are pinned in
`python_site_rows.json`.
"""

from __future__ import annotations

from python_symbol_sources import Plant, Want

HELPER = "def helper():\n    pass\n\n\n"
UNIT = "class U:\n    pass\n\n\n"
F = Want("function", "helper")
RUN = Want("function", "run")
CLS = Want("class", "U")
BUILD = Want("function", "build")
ITEM = Want("binding", "build.item", {"initializer": "U()"})


def calls(source: str, truth: str, **more: object) -> Plant:
    wants = (F, RUN)
    return Plant(HELPER + source, wants, truth, edges=(("calls", "run", "helper"),), **more)


def made(source: str, truth: str, edge: tuple[str, str, str], wants: tuple[Want, ...]) -> Plant:
    return Plant(UNIT + source, wants, truth, edges=(edge,))


INSTANCE = ("instance_of", "build.item", "U")
CREATES = ("creates", "build", "U")
WANT_ITEM = (CLS, BUILD, ITEM)

HIDDEN = {
    "call-plain": calls("def run():\n    helper()\n", "PASS"),
    "call-param": calls("def run(helper):\n    helper()\n", "DIFF"),
    "call-local": calls("def run():\n    helper = lambda: 1\n    helper()\n", "DIFF"),
    "call-for": calls("def run():\n    for helper in [len]:\n        helper()\n", "DIFF"),
    "call-with": calls(
        "from contextlib import nullcontext\n\n\ndef run():\n"
        "    with nullcontext(len) as helper:\n        helper()\n",
        "DIFF",
    ),
    "call-walrus": calls("def run():\n    (helper := len)([])\n", "DIFF"),
    "call-comprehension": calls("def run():\n    return [helper() for helper in [len]]\n", "DIFF"),
    "call-lambda": calls("def run():\n    return (lambda helper: helper([]))(len)\n", "DIFF"),
    "call-nested-def": calls("def run():\n    def helper():\n        pass\n    helper()\n", "DIFF"),
    "call-except": calls(
        "def run():\n    try:\n        pass\n    except ValueError as helper:\n        helper()\n",
        "DIFF",
    ),
    "call-match": calls(
        "def run():\n    match len:\n        case helper:\n            helper()\n", "DIFF"
    ),
    "call-local-import": calls(
        "def run():\n    from os import getcwd as helper\n    helper()\n", "DIFF"
    ),
    "call-global": calls(
        "def run():\n    global helper\n    helper = len\n    helper([])\n", "DIFF"
    ),
    "call-deleted": calls("def run():\n    helper()\n    del helper\n", "DIFF"),
    "call-redefined": calls("def helper(a):\n    pass\n\n\ndef run():\n    helper(1)\n", "PASS"),
    "call-alias": calls("alias = helper\n\n\ndef run():\n    alias()\n", "PASS"),
    "call-of-call": calls("def run():\n    helper()()\n", "PASS"),
    "call-getattr": calls("def run():\n    getattr(len, 'x', helper)()\n", "DIFF"),
    "call-method": Plant(
        "class A:\n    def m(self):\n        pass\n\n    def n(self):\n        self.m()\n",
        (Want("class", "A"), Want("method", "A.m"), Want("method", "A.n")),
        "PASS",
        edges=(("calls", "A.n", "A.m"),),
    ),
    "call-in-method": Plant(
        HELPER + "class A:\n    def m(self):\n        helper()\n",
        (F, Want("class", "A"), Want("method", "A.m")),
        "PASS",
        edges=(("calls", "A.m", "helper"),),
    ),
    "call-class-attribute-hides-nothing": Plant(
        HELPER + "class A:\n    helper = 1\n\n    def m(self):\n        helper()\n",
        (F, Want("class", "A"), Want("method", "A.m")),
        "PASS",
        edges=(("calls", "A.m", "helper"),),
    ),
    "call-decorated-target": calls(
        "def deco(fn):\n    return len\n\n\n@deco\ndef helper():\n    pass\n\n\n"
        "def run():\n    helper()\n",
        "DIFF",
    ),
    "closed-calls-extra": Plant(
        HELPER + "def run():\n    helper()\n", (F, RUN), "DIFF", closed=("calls",)
    ),
    "closed-calls-param": Plant(
        HELPER + "def run(helper):\n    helper()\n", (F, RUN), "PASS", closed=("calls",)
    ),
}

CONSTRUCTION = {
    "creates": made("def build():\n    return U()\n", "PASS", CREATES, (CLS, BUILD)),
    "creates-hidden": made("def build(U):\n    return U()\n", "DIFF", CREATES, (CLS, BUILD)),
    "instance-of": made(
        "def build():\n    item = U()\n    return item\n", "PASS", INSTANCE, WANT_ITEM
    ),
    "instance-twice": made(
        "class V:\n    pass\n\n\ndef build():\n    item = U()\n    item = V()\n    return item\n",
        "DIFF",
        INSTANCE,
        WANT_ITEM,
    ),
    "instance-tuple": made(
        "def build():\n    item, other = U(), U()\n    return item\n", "PASS", INSTANCE, WANT_ITEM
    ),
    "instance-with": made(
        "def build():\n    with U() as item:\n        pass\n    return item\n",
        "DIFF",
        INSTANCE,
        WANT_ITEM,
    ),
    "instance-walrus": made(
        "def build():\n    return (item := U())\n", "PASS", INSTANCE, WANT_ITEM
    ),
    "instance-global": made(
        "def build():\n    global item\n    item = U()\n    return item\n",
        "PASS",
        INSTANCE,
        WANT_ITEM,
    ),
    "instance-parameter": made(
        "def build(item):\n    item = U()\n    return item\n", "PASS", INSTANCE, WANT_ITEM
    ),
    "instance-conditional-value": made(
        "def build(flag):\n    item = U() if flag else None\n    return item\n",
        "DIFF",
        INSTANCE,
        WANT_ITEM,
    ),
    "instance-with-arguments": made(
        "class W:\n    def __init__(self, a):\n        pass\n\n\n"
        "def build():\n    item = W(1)\n    return item\n",
        "PASS",
        ("instance_of", "build.item", "W"),
        (Want("class", "W"), BUILD, Want("binding", "build.item", {"initializer": "W(1)"})),
    ),
    "new-returns-other": made(
        "class N:\n    def __new__(cls):\n        return 5\n\n\n"
        "def build():\n    item = N()\n    return item\n",
        "DIFF",
        ("instance_of", "build.item", "N"),
        (Want("class", "N"), BUILD, Want("binding", "build.item", {"initializer": "N()"})),
    ),
}

BASES = {
    "inherits": Plant(
        UNIT + "class B(U):\n    pass\n",
        (CLS, Want("class", "B")),
        "PASS",
        edges=(("inherits", "B", "U"),),
    ),
    "inherits-missing": Plant(
        UNIT + "class C:\n    pass\n\n\nclass B(U):\n    pass\n",
        (CLS, Want("class", "C"), Want("class", "B")),
        "DIFF",
        edges=(("inherits", "B", "C"),),
    ),
    "inherits-alias": Plant(
        UNIT + "Alias = U\n\n\nclass B(Alias):\n    pass\n",
        (CLS, Want("class", "B")),
        "PASS",
        edges=(("inherits", "B", "U"),),
    ),
    "inherits-conditional": Plant(
        UNIT + "class V:\n    pass\n\n\nclass B(U if __name__ else V):\n    pass\n",
        (CLS, Want("class", "B")),
        "PASS",
        edges=(("inherits", "B", "U"),),
    ),
    "realizes": Plant(
        "from typing import Protocol\n\n\nclass P(Protocol):\n    pass\n\n\n"
        "class B(P):\n    pass\n",
        (Want("interface", "P"), Want("class", "B")),
        "PASS",
        edges=(("realizes", "B", "P"),),
    ),
    "references-annotation": made(
        "def build() -> U:\n    pass\n", "PASS", ("references", "build", "U"), (CLS, BUILD)
    ),
    "references-hidden-by-class": Plant(
        UNIT + "class C:\n    U = int\n\n    def m(self) -> U:\n        pass\n",
        (CLS, Want("class", "C"), Want("method", "C.m")),
        "DIFF",
        edges=(("references", "C.m", "U"),),
    ),
    "references-value": Plant(
        HELPER + "def run():\n    return helper\n",
        (F, RUN),
        "PASS",
        edges=(("references", "run", "helper"),),
    ),
}

REVIEW = {
    "ctl-absent": calls("def run():\n    pass\n", "DIFF"),
    "mangled-call": Plant(
        "def __helper(*a, **k):\n    return None\n\n\n"
        "class A:\n    def m(self):\n        __helper()\n",
        (Want("function", "__helper"), Want("class", "A"), Want("method", "A.m")),
        "DIFF",
        edges=(("calls", "A.m", "__helper"),),
    ),
    "new-class-attr-written": made(
        "class N:\n    pass\n\n\nN.__new__ = lambda cls: 5\n\n\n"
        "def build():\n    item = N()\n    return item\n",
        "DIFF",
        ("instance_of", "build.item", "N"),
        (Want("class", "N"), BUILD, Want("binding", "build.item", {"initializer": "N()"})),
    ),
    "new-setattr-written": made(
        "class N:\n    pass\n\n\nsetattr(N, '__new__', lambda cls: 5)\n\n\n"
        "def build():\n    item = N()\n    return item\n",
        "DIFF",
        ("instance_of", "build.item", "N"),
        (Want("class", "N"), BUILD, Want("binding", "build.item", {"initializer": "N()"})),
    ),
    "dead-if-false": calls("def run():\n    if False:\n        helper()\n", "DIFF"),
    "dead-if-zero": calls("def run():\n    if 0:\n        helper()\n", "DIFF"),
    "dead-while-false": calls("def run():\n    while False:\n        helper()\n", "DIFF"),
    "dead-after-return": calls("def run():\n    return None\n    helper()\n", "DIFF"),
    "dead-after-raise": calls("def run():\n    raise ValueError\n    helper()\n", "DIFF"),
    "dead-after-break": calls(
        "def run():\n    for _ in [1]:\n        break\n        helper()\n", "DIFF"
    ),
    "dead-type-checking": calls(
        "from typing import TYPE_CHECKING\n\n\n"
        "def run():\n    if TYPE_CHECKING:\n        helper()\n",
        "DIFF",
    ),
    "dead-else-branch-lives": calls(
        "def run():\n    if False:\n        pass\n    else:\n        helper()\n", "PASS"
    ),
    "dead-return-in-branch-lives": calls(
        "def run(a):\n    if a:\n        return None\n    helper()\n", "PASS"
    ),
    "closed-dead-if-false": Plant(
        HELPER + "def run():\n    if False:\n        helper()\n",
        (F, RUN),
        "PASS",
        closed=("calls",),
    ),
}

PLANTS: dict[str, Plant] = {**HIDDEN, **CONSTRUCTION, **BASES, **REVIEW}
