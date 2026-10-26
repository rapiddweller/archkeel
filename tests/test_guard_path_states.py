# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-270: sequential `if` blocks must not multiply guarded-call paths."""

from __future__ import annotations

import ast
import random
import textwrap
import time
from pathlib import Path

import pytest
from test_exact_module_ownership import _observe_tree
from test_guarded_effect_scan_completeness import _contract

from archkeel.ir.guard_paths import GuardedCallPath, guarded_call_paths


def _paths(source: str, name: str = "flag", receiver: str | None = None) -> list[GuardedCallPath]:
    function = ast.parse(textwrap.dedent(source)).body[0]
    assert isinstance(function, ast.FunctionDef)
    return list(guarded_call_paths(function, name, receiver_name=receiver))


def _by_call(paths: list[GuardedCallPath]) -> dict[str, set[tuple[bool | None, str | None]]]:
    found: dict[str, set[tuple[bool | None, str | None]]] = {}
    for path in paths:
        found.setdefault(path.call_name, set()).add((path.condition_value, path.unknown_reason))
    return found


def _sequential(blocks: int, condition: str) -> str:
    body = "".join(f"    if {condition.format(i=i)}:\n        step{i}()\n" for i in range(blocks))
    return f"def f(flag, other):\n{body}    if flag:\n        effect()\n"


@pytest.mark.parametrize(
    "condition",
    ["other{i}", "other", "flag and other{i}", "g(other)", "not other{i}", "flag or other"],
    ids=["unrelated", "same_unrelated", "compound", "call", "negated", "or"],
)
def test_records_grow_linearly_with_sequential_if_blocks(condition: str) -> None:
    sizes = {n: len(_paths(_sequential(n, condition))) for n in (2, 8, 14)}
    # Twelve more blocks add about twelve calls, not thousands of copies (old code: 2^k).
    assert sizes[14] - sizes[8] <= 3 * 6
    assert sizes[14] <= 3 * 14 + 6


def test_a_deep_sequence_finishes_quickly_and_keeps_one_record_per_guarded_call() -> None:
    started = time.perf_counter()
    paths = _paths(_sequential(18, "other{i}"))
    assert time.perf_counter() - started < 2
    guarded = [path for path in paths if path.call_name == "effect"]
    assert [path.condition_value for path in guarded] == [True]


def test_the_distinct_records_of_a_mixed_function_are_exactly_these() -> None:
    paths = _paths(
        """
        def f(flag, a, b):
            if a:
                one()
            if flag:
                two()
            else:
                three()
            if b:
                four()
            if not flag:
                five()
            six()
        """
    )
    assert _by_call(paths) == {
        "one": {(None, None)},
        "two": {(True, None)},
        "three": {(False, None)},
        "four": {(True, None), (False, None)},
        "five": {(False, None)},
        "six": {(True, None), (False, None)},
    }


def test_a_write_to_the_condition_between_blocks_still_marks_later_calls_unknown() -> None:
    paths = _paths(
        """
        def f(flag, a):
            if a:
                one()
            flag = not flag
            if a:
                two()
            if flag:
                three()
        """
    )
    assert _by_call(paths)["three"] == {(None, "condition_mutation")}
    assert all(reason == "condition_mutation" for _, reason in _by_call(paths)["two"])


def test_receiver_attribute_guards_survive_unrelated_blocks() -> None:
    paths = _paths(
        """
        def f(self, a, b):
            if a:
                x = 1
            if b:
                y = 2
            if self.flag:
                effect()
            else:
                other_effect()
            if a:
                z = 3
            after()
        """,
        receiver="self",
    )
    by_call = _by_call(paths)
    assert by_call["effect"] == {(True, None)}
    assert by_call["other_effect"] == {(False, None)}
    # A call on the receiver may change the flag, so the later call is unknown, as before.
    assert by_call["after"] == {(None, "opaque_call_mutation")}


@pytest.mark.parametrize("seed", range(40))
def test_an_unrelated_block_never_changes_the_distinct_records_of_other_calls(seed: int) -> None:
    rng = random.Random(seed)
    conditions = ["flag", "not flag", "a", "b and flag", "obj.ok", "g(flag)"]

    def block(depth: int, counter: list[int]) -> str:
        counter[0] += 1
        call = f"c{counter[0]}()"
        if depth > 2 or rng.random() < 0.4:
            return rng.choice([call, f"return {call}", f"x = {call}"])
        inner = textwrap.indent(block(depth + 1, counter), "    ")
        tail = textwrap.indent(block(depth + 1, counter), "    ")
        orelse = f"else:\n{tail}\n" if rng.random() < 0.5 else ""
        return f"if {rng.choice(conditions)}:\n{inner}\n{orelse}"

    counter = [0]
    blocks = [block(0, counter) for _ in range(rng.randint(2, 6))]
    base = "def f(flag, a, b, obj):\n" + "".join(textwrap.indent(b, "    ") + "\n" for b in blocks)
    cut = rng.randint(0, len(blocks))
    extra = textwrap.indent("if a:\n    unrelated()\n", "    ")
    longer = (
        "def f(flag, a, b, obj):\n"
        + "".join(textwrap.indent(b, "    ") + "\n" for b in blocks[:cut])
        + extra
        + "".join(textwrap.indent(b, "    ") + "\n" for b in blocks[cut:])
    )
    before = _by_call(_paths(base))
    after = _by_call(_paths(longer))
    after.pop("unrelated", None)
    assert after == before


def test_a_guarded_rule_reports_one_violation_for_twelve_sequential_blocks(
    tmp_path: Path,
) -> None:
    blocks = 12
    sequence = "".join(f"    if other{i}:\n        helper{i}()\n" for i in range(blocks))
    parameters = ", ".join(f"other{i}" for i in range(blocks))
    files = {
        "sample/__init__.py": "",
        "sample/safe/__init__.py": "",
        "sample/safe/core.py": (
            "def _effect():\n    return None\n\n"
            f"def generate(seeded: bool, {parameters}):\n{sequence}"
            "    if seeded:\n        _effect()\n"
        ),
    }
    started = time.perf_counter()
    result = _observe_tree(
        tmp_path, files, _contract(mounted=False, source="sample"), roots=("sample",)
    )
    assert time.perf_counter() - started < 30
    assert result.observation is not None
    # The old walker made 2^12 identical copies of this one violation.
    assert len(result.observation.records("violations") or ()) == 1
