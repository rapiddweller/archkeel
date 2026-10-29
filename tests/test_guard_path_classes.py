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


def _run(
    walker: type[_GuardPathWalker], function: ast.FunctionDef | ast.AsyncFunctionDef, member: bool
) -> Paths:
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
    "except_type": "try:\n    pass\nexcept E{i}(c{i}()):\n    pass",
    "try_else": "try:\n    pass\nexcept E:\n    pass\nelse:\n    c{i}()",
    "try_finally": "try:\n    pass\nfinally:\n    c{i}()",
    "try_star": "try:\n    pass\nexcept* E:\n    c{i}()",
    "with_item": "with c{i}() as f:\n    pass",
    "with_target": "with ctx as c{i}().x:\n    pass",
    "match_guard": "match other:\n    case 1 if c{i}():\n        pass",
    "match_subject": "match c{i}():\n    case 1:\n        pass",
    "match_nested_try": (
        "match other:\n    case 1:\n        try:\n            pass\n"
        "        except E:\n            c{i}()"
    ),
    "for_else": "for q in qs:\n    pass\nelse:\n    c{i}()",
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
    "try": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow"), ("d", None, "unsupported_control_flow")],
    ),
    "with": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "match": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "except_type": (
        [(None, "unsupported_control_flow")],
        [("E", None, "unsupported_control_flow"), ("c", None, "unsupported_control_flow")],
    ),
    "try_else": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "try_finally": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "try_star": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "with_item": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "with_target": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "match_guard": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "match_subject": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "match_nested_try": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "for_else": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
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
    "try": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow"), ("d", None, "unsupported_control_flow")],
    ),
    "with": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "match": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "except_type": (
        [(None, "unsupported_control_flow")],
        [("E", None, "unsupported_control_flow"), ("c", None, "unsupported_control_flow")],
    ),
    "try_else": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "try_finally": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "try_star": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "with_item": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "with_target": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "match_guard": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "match_subject": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "match_nested_try": (
        [(None, "unsupported_control_flow")],
        [("c", None, "unsupported_control_flow")],
    ),
    "for_else": ([(None, "unsupported_control_flow")], [("c", None, "unsupported_control_flow")]),
    "ifexp_guard": (
        [(None, "opaque_call_mutation")],
        [("a", None, "opaque_call_mutation"), ("b", None, "opaque_call_mutation")],
    ),
    "ifexp_other": (
        [(None, "opaque_call_mutation")],
        [("a", None, "opaque_call_mutation"), ("b", None, "opaque_call_mutation")],
    ),
    "nested_def": ([(None, None)], [("c", None, None)]),
    # The class body calls c(): that call can change the member before the code after the class.
    "nested_class": (
        [(None, "opaque_call_mutation")],
        [("Base", None, None), ("c", None, None)],
    ),
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


def _function(
    menu: dict[str, str],
    kinds: Iterable[str],
    wrap: str,
    member: bool,
    asynchronous: bool = False,
):
    body = "\n".join(menu[kind].format(i=i) for i, kind in enumerate(kinds)) + "\nprobe()"
    if wrap != "top":
        body = WRAPS[wrap].format(s=textwrap.indent(body, "    "))
        if member:
            body = body.replace("flag", "self.flag")
    keyword = "async def" if asynchronous else "def"
    head = (
        f"{keyword} f(self, other, qs, ctx):" if member else f"{keyword} f(flag, other, qs, ctx):"
    )
    function = ast.parse(head + "\n" + textwrap.indent(body, "    ") + "\n").body[0]
    assert isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
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


def _calls_in_body(function: ast.FunctionDef) -> set[tuple[int, int]]:
    """Call sites of the function body, without the bodies of nested functions."""
    sites: set[tuple[int, int]] = set()

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                for decorated in child.decorator_list:
                    visit_expression(decorated)
                continue
            if isinstance(child, ast.Call):
                sites.add((child.lineno, child.col_offset))
            visit(child)

    def visit_expression(node: ast.expr) -> None:
        if isinstance(node, ast.Call):
            sites.add((node.lineno, node.col_offset))
        visit(node)

    visit(function)
    return sites


@CASES
def test_every_call_of_every_statement_class_gets_a_path_record(menu, member) -> None:
    # Pruning drops calls on purpose: inside a fixed guard, and after a `return` under the
    # guard, where the walker knows the flag is false. Those two cases stay out.
    for kinds in itertools.chain(((kind,) for kind in menu), itertools.product(menu, repeat=2)):
        if kinds[0] == "return_in_guard" and len(kinds) > 1:
            continue
        for wrap in ("top", "in_other", "in_else"):
            function = _function(menu, kinds, wrap, member)
            recorded = {(p.line, p.column) for p in _run(_GuardPathWalker, function, member)}
            missing = _calls_in_body(function) - recorded
            assert not missing, (kinds, wrap, sorted(missing))


@pytest.mark.parametrize(
    "wrapper",
    [
        "try:\n    pass\nexcept Error:\n{body}",
        "match other:\n    case 1:\n{body}",
        "with ctx as handle:\n{body}",
    ],
    ids=["except_handler", "match_case", "with_body"],
)
def test_a_guard_inside_an_unsupported_block_keeps_its_statement_and_test_as_path(
    wrapper: str,
) -> None:
    body = textwrap.indent("if flag:\n    c0()\nelse:\n    d0()", "        ")
    source = (
        "def f(flag, other, ctx):\n" + textwrap.indent(wrapper.format(body=body), "    ") + "\n"
    )
    function = ast.parse(source).body[0]
    assert isinstance(function, ast.FunctionDef)
    paths = {p.call_name: p for p in _run(_GuardPathWalker, function, False)}
    for name in ("c0", "d0"):
        # The unsupported statement and the guard test stay on the path, so the evidence is exact.
        kinds = [type(node).__name__ for node in paths[name].path_nodes]
        assert kinds[0] in {"Try", "Match", "With"}, kinds
        assert "Name" in kinds, kinds
        assert paths[name].condition_value is None
        assert paths[name].unknown_reason == "unsupported_control_flow"


# Every way the guarded value can be read: the call in the `if` body and in the `else` body.
PARAM_CONDITIONS = {
    "flag": ([(True, None)], [(False, None)]),
    "(flag)": ([(True, None)], [(False, None)]),
    "not flag": ([(False, None)], [(True, None)]),
    "not (flag)": ([(False, None)], [(True, None)]),
    "not not flag": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "flag is True": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "flag == True": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "bool(flag)": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "flag and other": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "other and flag": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "flag or other": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "other": ([(None, None)], [(None, None)]),
    "not other": ([(None, None)], [(None, None)]),
    "True": ([(None, None)], [(None, None)]),
    "flag if other else other": (
        [(None, "unsupported_condition")],
        [(None, "unsupported_condition")],
    ),
    "[flag]": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "flag[0]": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "-flag": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "(flag := other)": ([(None, "condition_mutation")], [(None, "condition_mutation")]),
    "g(flag)": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "g()": ([(None, None)], [(None, None)]),
    "other.flag": ([(None, None)], [(None, None)]),
    "other == flag": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
}
MEMBER_CONDITIONS = {
    "flag": ([(True, None)], [(False, None)]),
    "(flag)": ([(True, None)], [(False, None)]),
    "not flag": ([(False, None)], [(True, None)]),
    "not (flag)": ([(False, None)], [(True, None)]),
    "not not flag": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "flag is True": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "flag == True": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "bool(flag)": ([(None, "opaque_call_mutation")], [(None, "opaque_call_mutation")]),
    "flag and other": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "other and flag": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "flag or other": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "other": ([(None, None)], [(None, None)]),
    "not other": ([(None, None)], [(None, None)]),
    "True": ([(None, None)], [(None, None)]),
    "flag if other else other": (
        [(None, "unsupported_condition")],
        [(None, "unsupported_condition")],
    ),
    "[flag]": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "flag[0]": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "-flag": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
    "g(flag)": ([(None, "opaque_call_mutation")], [(None, "opaque_call_mutation")]),
    "g()": ([(None, "opaque_call_mutation")], [(None, "opaque_call_mutation")]),
    "other == flag": ([(None, "unsupported_condition")], [(None, "unsupported_condition")]),
}

# Statements that may change the guarded value, after `if flag:` fixed it to True:
# the value a later call sees. `None` plus a reason means the walker gave up, which is safe.
PARAM_WRITE_SOURCES = {
    "assign": "flag = x",
    "augassign": "flag |= x",
    "annassign": "flag: bool = x",
    "annassign_novalue": "flag: bool",
    "tuple_unpack": "flag, y = x, 1",
    "starred_unpack": "*flag, y = x",
    "walrus_stmt": "(flag := x)",
    "chained_assign": "a = flag = x",
    "for_target": "for flag in xs:\n    pass",
    "with_target": "with ctx as flag:\n    pass",
    "except_as": "try:\n    pass\nexcept E as flag:\n    pass",
    "global": "global flag",
    "match_capture": "match x:\n    case flag:\n        pass",
    "comprehension_var": "y = [flag for flag in xs]",
    "lambda_param": "g = lambda flag: flag",
    "nested_def_param": "def inner(flag):\n    return flag",
    "attr_of_flag": "flag.x = 1",
    "subscript_of_flag": "flag[0] = 1",
    "other_name": "other = 1",
    "del": "del flag",
    "del_parenthesized": "del (flag)",
    "del_tuple": "del (x, flag)",
    "del_list": "del [flag]",
    "del_nested_if": "if x:\n    del flag",
    "del_attr_of_flag": "del flag.x",
    "del_item_of_flag": "del flag[0]",
    "del_other_name": "del x",
    "import": "import flag",
    "import_dotted": "import flag.sub",
    "import_as": "import m as flag",
    "from_import": "from m import flag",
    "from_import_as": "from m import n as flag",
    "import_other_name": "import m",
    "def": "def flag():\n    pass",
    "async_def": "async def flag():\n    pass",
    "class": "class flag:\n    pass",
    "def_other_name": "def g():\n    pass",
    "class_other_name": "class G:\n    pass",
    "walrus_in_default": "def g(a=(flag := x)):\n    pass",
    "walrus_in_decorator": "@(flag := x)\ndef g():\n    pass",
    "walrus_in_class_base": "class G((flag := x)):\n    pass",
    "exec": "exec('flag = 1')",
    "eval": "eval('flag')",
    "globals": "globals()",
    "locals": "locals()",
    "vars": "vars()",
}
PARAM_WRITES = {
    "assign": [(None, "condition_mutation")],
    "augassign": [(None, "condition_mutation")],
    "annassign": [(None, "condition_mutation")],
    "annassign_novalue": [(None, "condition_mutation")],
    "tuple_unpack": [(None, "condition_mutation")],
    "starred_unpack": [(None, "condition_mutation")],
    "walrus_stmt": [(None, "condition_mutation")],
    "chained_assign": [(None, "condition_mutation")],
    "for_target": [(None, "unsupported_control_flow")],
    "with_target": [(None, "unsupported_control_flow")],
    "except_as": [(None, "unsupported_control_flow")],
    "global": [(True, None)],
    "match_capture": [(None, "unsupported_control_flow")],
    "comprehension_var": [(None, "condition_mutation")],
    "lambda_param": [(True, None)],
    "nested_def_param": [(True, None)],
    "attr_of_flag": [(True, None)],
    "subscript_of_flag": [(True, None)],
    "other_name": [(True, None)],
    "del": [(None, "condition_mutation")],
    "del_parenthesized": [(None, "condition_mutation")],
    "del_tuple": [(None, "condition_mutation")],
    "del_list": [(None, "condition_mutation")],
    "del_nested_if": [(None, "condition_mutation"), (True, None)],
    "del_attr_of_flag": [(True, None)],
    "del_item_of_flag": [(True, None)],
    "del_other_name": [(True, None)],
    "import": [(None, "condition_mutation")],
    "import_dotted": [(None, "condition_mutation")],
    "import_as": [(None, "condition_mutation")],
    "from_import": [(None, "condition_mutation")],
    "from_import_as": [(None, "condition_mutation")],
    "import_other_name": [(True, None)],
    "def": [(None, "condition_mutation")],
    "async_def": [(None, "condition_mutation")],
    "class": [(None, "condition_mutation")],
    "def_other_name": [(True, None)],
    "class_other_name": [(True, None)],
    "walrus_in_default": [(None, "condition_mutation")],
    "walrus_in_decorator": [(None, "condition_mutation")],
    "walrus_in_class_base": [(None, "condition_mutation")],
    "exec": [(None, "condition_mutation")],
    "eval": [(None, "condition_mutation")],
    "globals": [(None, "condition_mutation")],
    "locals": [(None, "condition_mutation")],
    "vars": [(None, "condition_mutation")],
}
MEMBER_WRITE_SOURCES = {
    "attr_assign": "self.flag = x",
    "attr_aug": "self.flag |= x",
    "attr_ann": "self.flag: bool = x",
    "attr_tuple": "self.flag, y = x, 1",
    "other_attr": "self.other = 1",
    "other_receiver": "o.flag = 1",
    "attr_del": "del self.flag",
    "attr_del_tuple": "del (self.other, self.flag)",
    "attr_del_other": "del self.other",
    "receiver_assign": "self = x",
    "receiver_del": "del self",
    "receiver_import_as": "import m as self",
    "receiver_def": "def self():\n    pass",
    "setattr_flag": "setattr(self, 'flag', x)",
    "setattr_other_name": "setattr(self, 'other', x)",
    "setattr_dynamic": "setattr(self, n, x)",
    "setattr_other_obj": "setattr(o, 'flag', x)",
    "setattr_one_arg": "setattr(self)",
    "delattr_flag": "delattr(self, 'flag')",
    "delattr_other": "delattr(self, 'other')",
    "object_setattr_flag": "object.__setattr__(self, 'flag', x)",
    "object_setattr_other": "object.__setattr__(self, 'other', x)",
    "object_setattr_other_obj": "object.__setattr__(o, 'flag', x)",
    "self_setattr_flag": "self.__setattr__('flag', x)",
    "self_setattr_other": "self.__setattr__('other', x)",
    "o_setattr_flag": "o.__setattr__('flag', x)",
    "self_delattr_flag": "self.__delattr__('flag')",
    "dict_item": "self.__dict__['flag'] = x",
    "dict_update": "self.__dict__.update(n=1)",
    "vars_self": "vars(self)['flag'] = x",
    "method_call": "self.run()",
    "plain_function_call": "helper()",
    "no_op": "pass",
    "read_only": "y = self.flag",
    "exec": "exec('self.flag = 1')",
}
MEMBER_WRITES = {
    "attr_assign": [(None, "condition_mutation")],
    "attr_aug": [(None, "condition_mutation")],
    "attr_ann": [(None, "condition_mutation")],
    "attr_tuple": [(None, "condition_mutation")],
    "other_attr": [(True, None)],
    "other_receiver": [(True, None)],
    "attr_del": [(None, "condition_mutation")],
    "attr_del_tuple": [(None, "condition_mutation")],
    "attr_del_other": [(True, None)],
    "receiver_assign": [(None, "condition_mutation")],
    "receiver_del": [(None, "condition_mutation")],
    "receiver_import_as": [(None, "condition_mutation")],
    "receiver_def": [(None, "condition_mutation")],
    "setattr_flag": [(None, "opaque_call_mutation")],
    "setattr_other_name": [(None, "opaque_call_mutation")],
    "setattr_dynamic": [(None, "opaque_call_mutation")],
    "setattr_other_obj": [(None, "opaque_call_mutation")],
    "setattr_one_arg": [(None, "opaque_call_mutation")],
    "delattr_flag": [(None, "opaque_call_mutation")],
    "delattr_other": [(None, "opaque_call_mutation")],
    "object_setattr_flag": [(None, "opaque_call_mutation")],
    "object_setattr_other": [(None, "opaque_call_mutation")],
    "object_setattr_other_obj": [(None, "opaque_call_mutation")],
    "self_setattr_flag": [(None, "opaque_call_mutation")],
    "self_setattr_other": [(None, "opaque_call_mutation")],
    "o_setattr_flag": [(None, "opaque_call_mutation")],
    "self_delattr_flag": [(None, "opaque_call_mutation")],
    "dict_item": [(None, "condition_mutation")],
    "dict_update": [(None, "opaque_call_mutation")],
    "vars_self": [(None, "opaque_call_mutation")],
    "method_call": [(None, "opaque_call_mutation")],
    "plain_function_call": [(None, "opaque_call_mutation")],
    "no_op": [(True, None)],
    "read_only": [(True, None)],
    "exec": [(None, "opaque_call_mutation")],
}


def _guarded(function_source: str, member: bool) -> Paths:
    function = ast.parse(function_source).body[0]
    assert isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
    return _run(_GuardPathWalker, function, member)


def _values(paths: Paths, call: str) -> set[tuple[bool | None, str | None]]:
    return {(p.condition_value, p.unknown_reason) for p in paths if p.call_name == call}


@pytest.mark.parametrize("condition", PARAM_CONDITIONS)
def test_each_parameter_condition_form_is_classified_as_expected(condition: str) -> None:
    source = (
        f"def f(flag, other, o, x):\n    if {condition}:\n        body()\n"
        "    else:\n        orelse()\n"
    )
    paths = _guarded(source, False)
    body, orelse = PARAM_CONDITIONS[condition]
    assert _values(paths, "body") == {tuple(item) for item in body}
    assert _values(paths, "orelse") == {tuple(item) for item in orelse}


@pytest.mark.parametrize("condition", MEMBER_CONDITIONS)
def test_each_member_condition_form_is_classified_as_expected(condition: str) -> None:
    source = (
        f"def f(self, other, o, x):\n    if {condition.replace('flag', 'self.flag')}:\n"
        "        body()\n    else:\n        orelse()\n"
    )
    paths = _guarded(source, True)
    body, orelse = MEMBER_CONDITIONS[condition]
    assert _values(paths, "body") == {tuple(item) for item in body}
    assert _values(paths, "orelse") == {tuple(item) for item in orelse}


def _after_write(statement: str, member: bool) -> set[tuple[bool | None, str | None]]:
    guard = "self.flag" if member else "flag"
    head = "def f(self, o, n, x, xs, ctx):" if member else "def f(flag, x, xs, ctx):"
    body = textwrap.indent(statement + "\nprobe()", "    ")
    source = head + "\n" + textwrap.indent(f"if {guard}:\n" + body, "    ") + "\n"
    return _values(_guarded(source, member), "probe")


@pytest.mark.parametrize("name", PARAM_WRITE_SOURCES)
def test_each_parameter_write_form_changes_or_keeps_the_value_as_expected(name: str) -> None:
    assert _after_write(PARAM_WRITE_SOURCES[name], False) == {
        tuple(item) for item in PARAM_WRITES[name]
    }


@pytest.mark.parametrize("name", MEMBER_WRITE_SOURCES)
def test_each_member_write_form_changes_or_keeps_the_value_as_expected(name: str) -> None:
    assert _after_write(MEMBER_WRITE_SOURCES[name], True) == {
        tuple(item) for item in MEMBER_WRITES[name]
    }


@pytest.mark.parametrize(
    "header,expected",
    [
        ("class G(base):", {(True, None)}),
        ("class G((flag := base)):", {(None, "condition_mutation")}),
        ("class G(metaclass=(flag := base)):", {(None, "condition_mutation")}),
        ("@(flag := deco)\n        class G:", {(None, "condition_mutation")}),
        ("class flag:", {(None, "condition_mutation")}),
    ],
)
def test_a_class_body_runs_after_the_rebinding_in_its_header(header: str, expected: set) -> None:
    source = f"def f(flag):\n    if flag:\n        {header}\n            inner()\n"
    assert _values(_guarded(source, False), "inner") == expected


ASYNC_ONLY = {
    "async_for": "async for q in qs:\n    c{i}()",
    "async_with": "async with ctx:\n    c{i}()",
    "async_with_item": "async with c{i}() as f:\n    pass",
    "await_in_test": "if await c{i}():\n    d{i}()",
    "await_call": "x{i} = await c{i}()",
}


@pytest.mark.parametrize(
    ("menu", "member"), [(PARAM, False), (MEMBER, True)], ids=["parameter", "member"]
)
def test_the_same_checks_hold_in_an_async_function(menu, member) -> None:
    both = {**menu, **ASYNC_ONLY}
    checked = 0
    for kinds in itertools.chain(((k,) for k in both), itertools.product(both, repeat=2)):
        for wrap in ("top", "in_other", "in_else"):
            function = _function(both, kinds, wrap, member, asynchronous=True)
            assert isinstance(function, ast.AsyncFunctionDef)
            before = _identity(_run(_UnmergedWalker, function, member))
            after = _identity(_run(_GuardPathWalker, function, member))
            assert set(after) == set(before), (kinds, wrap)
            assert _is_subsequence(after, before), (kinds, wrap)
            if kinds[0] != "return_in_guard" or len(kinds) == 1:
                recorded = {(p.line, p.column) for p in _run(_GuardPathWalker, function, member)}
                assert not _calls_in_body(function) - recorded, (kinds, wrap)
            checked += 1
    assert checked == (len(both) + len(both) ** 2) * 3
