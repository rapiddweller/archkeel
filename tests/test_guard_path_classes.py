# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-270: equivalence classes of statements, checked against the walker without merging."""

from __future__ import annotations

import ast
import itertools
import re
import textwrap
from collections.abc import Iterable

import pytest

from archkeel.ir.guard_paths import GuardedCallPath, _GuardPathWalker

Paths = list[GuardedCallPath]


class _UnmergedWalker(_GuardPathWalker):
    """The walker as it was before AD-270: every branch state stays, equal or not."""

    def block(  # type: ignore[override]
        self,
        statements: list[ast.stmt],
        value: bool | None,
        path_nodes: tuple[ast.AST, ...],
        unknown_reason: str | None = None,
    ):
        active = [(value, unknown_reason, path_nodes)]
        for statement in statements:
            next_active = []
            for current, current_reason, current_nodes in active:
                next_active.extend(
                    self._statement_paths(statement, current, current_reason, current_nodes)
                )
            active = next_active
            if not active:
                break
        return active


def _run(walker: type[_GuardPathWalker], function: ast.FunctionDef, member: bool) -> Paths:
    instance = walker(function, "flag", "self" if member else None)
    instance.block(function.body, None, ())
    return instance.calls


# Equivalence classes of one statement; {i} makes the call names unique.
PARAM = {
    "plain": "v{i} = 1",
    "call": "c{i}()",
    "guard_if": "if flag:\n    c{i}()",
    "guard_if_else": "if flag:\n    c{i}()\nelse:\n    d{i}()",
    "negated_if": "if not flag:\n    c{i}()",
    "unrelated_if": "if other:\n    c{i}()",
    "unrelated_if_else": "if other:\n    c{i}()\nelse:\n    d{i}()",
    "elif_chain": "if other:\n    c{i}()\nelif flag:\n    d{i}()\nelse:\n    e{i}()",
    "compound_read": "if flag and other:\n    c{i}()",
    "or_read": "if flag or other:\n    c{i}()",
    "compare_read": "if flag == other:\n    c{i}()",
    "call_in_test": "if g(other):\n    c{i}()",
    "walrus_write": "if (flag := other):\n    c{i}()",
    "assign_write": "flag = other",
    "augassign_write": "flag |= other",
    "reflective_write": "exec('flag = 1')",
    "return_in_guard": "if flag:\n    return c{i}()",
    "return_in_other": "if other:\n    return c{i}()",
    "raise_ctor": "if other:\n    raise E{i}()",
    "raise_bare": "if other:\n    raise",
    "loop": "for q in qs:\n    c{i}()",
    "while": "while other:\n    c{i}()",
    "try": "try:\n    c{i}()\nexcept E:\n    d{i}()",
    "with": "with ctx:\n    c{i}()",
    "match": "match other:\n    case 1:\n        c{i}()",
    "ifexp_guard": "x{i} = a{i}() if flag else b{i}()",
    "ifexp_other": "x{i} = a{i}() if other else b{i}()",
    "nested_def": "def inner{i}(p=c{i}()):\n    return 1",
    "nested_class": "class K{i}(Base{i}()):\n    attr = c{i}()",
    "empty_branch": "if other:\n    pass",
}
MEMBER = {k: v.replace("flag", "self.flag") for k, v in PARAM.items()}
MEMBER.pop("walrus_write")
MEMBER["setattr_write"] = "setattr(self, 'flag', 1)"
MEMBER["dict_write"] = "self.__dict__.update(x=1)"
MEMBER["method_call"] = "self.run{i}()"

WRAPS = {
    "top": "{s}",
    "in_other": "if other:\n{s}",
    "in_else": "if other:\n    pass\nelse:\n{s}",
    "in_guard": "if flag:\n{s}",
    "in_notguard": "if not flag:\n{s}",
}


def build(menu, kinds, wrap, member):
    parts = []
    for i, kind in enumerate(kinds):
        parts.append(menu[kind].format(i=i))
    body = "\n".join(parts) + "\nprobe()"
    w = WRAPS[wrap]
    if wrap != "top":
        body = (
            w.format(s=textwrap.indent(body, "    ")).replace("flag", "self.flag")
            if member
            else w.format(s=textwrap.indent(body, "    "))
        )
    head = "def f(self, other, qs, ctx):" if member else "def f(flag, other, qs, ctx):"
    src = head + "\n" + textwrap.indent(body, "    ") + "\n"
    return ast.parse(src).body[0]


PARAM_EXPECTED = {
    "plain": ([(None, None)], []),
    "call": ([(None, None)], [("c", None, None)]),
    "guard_if": ([(False, None), (True, None)], [("c", True, None)]),
    "guard_if_else": ([(False, None), (True, None)], [("c", True, None), ("d", False, None)]),
    "negated_if": ([(False, None), (True, None)], [("c", False, None)]),
    "unrelated_if": ([(None, None)], [("c", None, None)]),
    "unrelated_if_else": ([(None, None)], [("c", None, None), ("d", None, None)]),
    "elif_chain": (
        [(False, None), (None, None), (True, None)],
        [("c", None, None), ("d", True, None), ("e", False, None)],
    ),
    "compound_read": ([(None, "unsupported_condition")], [("c", None, "unsupported_condition")]),
    "or_read": ([(None, "unsupported_condition")], [("c", None, "unsupported_condition")]),
    "compare_read": ([(None, "unsupported_condition")], [("c", None, "unsupported_condition")]),
    "call_in_test": ([(None, None)], [("c", None, None), ("g", None, None)]),
    "walrus_write": ([(None, "condition_mutation")], [("c", None, "condition_mutation")]),
    "assign_write": ([(None, "condition_mutation")], []),
    "augassign_write": ([(None, "condition_mutation")], []),
    "reflective_write": ([(None, "condition_mutation")], [("exec", None, "condition_mutation")]),
    "return_in_guard": ([(False, None)], [("c", True, None)]),
    "return_in_other": ([(None, None)], [("c", None, None)]),
    "raise_ctor": ([(None, None)], [("E", None, None)]),
    "raise_bare": ([(None, None)], []),
    "loop": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "while": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "try": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "with": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "match": ([(None, "unsupported_control_flow")], []),
    "ifexp_guard": ([(None, None)], [("a", True, None), ("b", False, None)]),
    "ifexp_other": ([(None, None)], [("a", None, None), ("b", None, None)]),
    "nested_def": ([(None, None)], [("c", None, None)]),
    "nested_class": ([(None, None)], [("Base", None, None), ("c", None, None)]),
    "empty_branch": ([(None, None)], []),
}
MEMBER_EXPECTED = {
    "plain": ([(None, None)], []),
    "call": ([(None, "opaque_call_mutation")], [("c", None, None)]),
    "guard_if": ([(False, None), (None, "opaque_call_mutation")], [("c", True, None)]),
    "guard_if_else": ([(None, "opaque_call_mutation")], [("c", True, None), ("d", False, None)]),
    "negated_if": ([(None, "opaque_call_mutation"), (True, None)], [("c", False, None)]),
    "unrelated_if": ([(None, "opaque_call_mutation"), (None, None)], [("c", None, None)]),
    "unrelated_if_else": ([(None, "opaque_call_mutation")], [("c", None, None), ("d", None, None)]),
    "elif_chain": (
        [(None, "opaque_call_mutation")],
        [("c", None, None), ("d", True, None), ("e", False, None)],
    ),
    "compound_read": (
        [(None, "opaque_call_mutation"), (None, "unsupported_condition")],
        [("c", None, "unsupported_condition")],
    ),
    "or_read": (
        [(None, "opaque_call_mutation"), (None, "unsupported_condition")],
        [("c", None, "unsupported_condition")],
    ),
    "compare_read": (
        [(None, "opaque_call_mutation"), (None, "unsupported_condition")],
        [("c", None, "unsupported_condition")],
    ),
    "call_in_test": (
        [(None, "opaque_call_mutation")],
        [("c", None, "opaque_call_mutation"), ("g", None, "opaque_call_mutation")],
    ),
    "assign_write": ([(None, "condition_mutation")], []),
    "augassign_write": ([(None, "condition_mutation")], []),
    "reflective_write": ([(None, "opaque_call_mutation")], [("exec", None, "condition_mutation")]),
    "return_in_guard": ([(False, None)], [("c", True, None)]),
    "return_in_other": ([(None, None)], [("c", None, None)]),
    "raise_ctor": ([(None, None)], [("E", None, None)]),
    "raise_bare": ([(None, None)], []),
    "loop": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "while": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "try": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "with": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "match": ([(None, "unsupported_control_flow")], []),
    "ifexp_guard": (
        [(None, "opaque_call_mutation")],
        [("a", None, "opaque_call_mutation"), ("b", None, "opaque_call_mutation")],
    ),
    "ifexp_other": (
        [(None, "opaque_call_mutation")],
        [("a", None, "opaque_call_mutation"), ("b", None, "opaque_call_mutation")],
    ),
    "nested_def": ([(None, None)], [("c", None, None)]),
    "nested_class": ([(None, None)], [("Base", None, None), ("c", None, None)]),
    "empty_branch": ([(None, None)], []),
    "setattr_write": ([(None, "opaque_call_mutation")], [("setattr", None, "condition_mutation")]),
    "dict_write": (
        [(None, "opaque_call_mutation")],
        [("self.__dict__.update", None, "condition_mutation")],
    ),
    "method_call": ([(None, "opaque_call_mutation")], [("self.run", None, None)]),
}


def _identity(paths: Paths) -> list[tuple[object, ...]]:
    return [
        (
            p.call_name,
            p.line,
            p.column,
            p.condition_value,
            tuple(id(node) for node in p.path_nodes),
            p.unknown_reason,
            p.raised_exception_constructor,
        )
        for p in paths
    ]


def _is_subsequence(small: list[tuple[object, ...]], big: list[tuple[object, ...]]) -> bool:
    remaining = iter(big)
    return all(any(item == other for other in remaining) for item in small)


def _function(menu: dict[str, str], kinds: Iterable[str], wrap: str, member: bool):
    body = "\n".join(menu[kind].format(i=i) for i, kind in enumerate(kinds)) + "\nprobe()"
    if wrap != "top":
        body = WRAPS[wrap].format(s=textwrap.indent(body, "    "))
        if member:
            body = body.replace("flag", "self.flag")
    head = "def f(self, other, qs, ctx):" if member else "def f(flag, other, qs, ctx):"
    function = ast.parse(head + "\n" + textwrap.indent(body, "    ") + "\n").body[0]
    assert isinstance(function, ast.FunctionDef)
    return function


def _compare(menu: dict[str, str], member: bool, kind_lists: Iterable[tuple[str, ...]], wraps):
    """Return (functions checked, functions where merging removed records)."""
    checked = reduced = 0
    for kinds in kind_lists:
        for wrap in wraps:
            function = _function(menu, kinds, wrap, member)
            before = _identity(_run(_UnmergedWalker, function, member))
            after = _identity(_run(_GuardPathWalker, function, member))
            # Same distinct records, in the same order, only fewer copies.
            assert set(after) == set(before), (kinds, wrap)
            assert _is_subsequence(after, before), (kinds, wrap)
            checked += 1
            reduced += len(after) < len(before)
    return checked, reduced


CASES = pytest.mark.parametrize(
    ("menu", "member"), [(PARAM, False), (MEMBER, True)], ids=["parameter", "member"]
)
# The classes that change the walker state: a branch, a value, a reason or a dead end.
CORE = [
    "guard_if_else",
    "negated_if",
    "unrelated_if",
    "compound_read",
    "call_in_test",
    "assign_write",
    "return_in_guard",
    "raise_ctor",
    "loop",
    "plain",
]


@CASES
def test_each_statement_class_alone_and_wrapped_in_each_context(menu, member) -> None:
    checked, _ = _compare(menu, member, ((kind,) for kind in menu), WRAPS)
    assert checked == len(menu) * len(WRAPS)


@CASES
def test_every_ordered_pair_of_statement_classes_in_each_context(menu, member) -> None:
    pairs = itertools.product(menu, repeat=2)
    checked, reduced = _compare(menu, member, pairs, WRAPS)
    assert checked == len(menu) ** 2 * len(WRAPS)
    # The check is not vacuous: merging really removes copies in many of these functions.
    assert reduced > checked // 20


@CASES
def test_every_ordered_triple_of_state_changing_classes(menu, member) -> None:
    triples = itertools.product(CORE, repeat=3)
    checked, reduced = _compare(menu, member, triples, ["top", "in_other"])
    assert checked == len(CORE) ** 3 * 2
    assert reduced > 0


@CASES
def test_four_blocks_of_each_state_changing_class_pair(menu, member) -> None:
    quads = (pair + pair for pair in itertools.product(CORE, repeat=2))
    checked, _ = _compare(menu, member, quads, ["top"])
    assert checked == len(CORE) ** 2


def _probe_and_inner(function: ast.FunctionDef, member: bool):
    paths = _run(_GuardPathWalker, function, member)
    probe = {(p.condition_value, p.unknown_reason) for p in paths if p.call_name == "probe"}
    inner = {
        (re.sub(r"\d+$", "", p.call_name), p.condition_value, p.unknown_reason)
        for p in paths
        if p.call_name != "probe"
    }
    return probe, inner


@pytest.mark.parametrize("kind", PARAM)
def test_expected_result_after_each_parameter_statement_class(kind: str) -> None:
    probe, inner = _probe_and_inner(_function(PARAM, [kind], "top", False), False)
    expected_probe, expected_inner = PARAM_EXPECTED[kind]
    assert probe == {tuple(item) for item in expected_probe}
    assert inner == {tuple(item) for item in expected_inner}


@pytest.mark.parametrize("kind", MEMBER)
def test_expected_result_after_each_member_statement_class(kind: str) -> None:
    probe, inner = _probe_and_inner(_function(MEMBER, [kind], "top", True), True)
    expected_probe, expected_inner = MEMBER_EXPECTED[kind]
    assert probe == {tuple(item) for item in expected_probe}
    assert inner == {tuple(item) for item in expected_inner}
