# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One source collection must reproduce Context evidence under different contracts."""

import ast
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from archkeel.analyzer.python.calls import collect_calls
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.resolve import build_symbol_index
from archkeel.analyzer.python.source import parse_sources
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.ir.facts_codec import freeze_data, parse_record
from archkeel.ir.state_codec import parse_state_data, state_data


def test_state_collection_replays_two_contracts_without_parsing_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from archkeel.analyzer.python.state import collect_state
    from archkeel.check.evaluation.state import evaluate_contexts

    source = tmp_path / "sample.py"
    source.write_text(
        "from dataclasses import dataclass\n"
        "from typing import Final, Protocol\n"
        "@dataclass(frozen=True)\n"
        "class Bag:\n"
        "    entries: Final[list[str]]\n"
        "    def __init__(self):\n"
        "        self.counter: int = 0\n"
        "    @property\n"
        "    def total(self):\n"
        "        return self.counter\n"
        "    @total.setter\n"
        "    def total(self, value):\n"
        "        self.counter = value\n"
        "    def change(self):\n"
        "        self.entries.append('x')\n"
        "class Unselected:\n"
        "    hidden: int\n"
        "class StatusState(Protocol):\n"
        "    state: str\n"
        "def use(value: Bag, state: StatusState):\n"
        "    alias = value\n"
        "    alias.entries.append('a')\n"
        "    print(later.counter)\n"
        "    if True:\n"
        "        if True:\n"
        "            later = Bag()\n"
        "    typed: Bag = state\n"
        "    both: StatusState = Bag()\n"
        "    typed.counter = 1\n"
        "    both.counter = 2\n"
        "    consume(alias, state, again=alias)\n"
        "    def inner(value: Bag):\n"
        "        return value.counter\n"
        "    return inner(value)\n"
    )
    parsed = parse_sources([source], root=tmp_path, namespace="sample").modules
    initial = {}
    symbols, nodes, owners = collect_symbols(parsed, initial)
    imports = collect_imports(
        parsed, {module.module for module in parsed}, initial, namespace="sample"
    )
    calls = collect_calls(parsed, build_symbol_index(symbols), initial)
    roots = (("sample.Bag", "missing.Root"), ("sample.Unselected", "other.Bag"))
    expected = json.loads(
        (Path(__file__).parent / "fixtures/state-facts/contracts.json").read_text()
    )

    facts, candidates = collect_state(
        parsed, tuple(parse_record(item) for item in symbols), nodes, owners
    )
    assert parse_state_data(state_data(facts)) == facts
    facts = parse_state_data(state_data(facts))
    before = asdict(facts)
    assert {item.qualified_name for item in facts.classes} == {
        "sample.Bag",
        "sample.Unselected",
        "sample.StatusState",
    }

    def forbidden_walk(*args: object, **kwargs: object) -> None:
        raise AssertionError("Core context replay must not inspect AST")

    monkeypatch.setattr(ast, "walk", forbidden_walk)
    for declared, expected_case in zip(roots, expected, strict=True):
        contexts, details, used = evaluate_contexts(
            facts, symbols, imports, calls, declared, candidates
        )
        assert contexts == expected_case["contexts"]
        assert details == expected_case["context_evidence"]
        assert [asdict(item) for item in used if item.id not in initial] == [
            item for item in expected_case["evidence"] if item["id"] not in initial
        ]
    assert asdict(facts) == before


def test_duplicate_simple_names_and_nested_class_owners_keep_original_resolution(
    tmp_path: Path,
) -> None:
    from archkeel.analyzer.python.state import collect_state
    from archkeel.check.evaluation.state import evaluate_contexts

    paths = []
    for filename, source in {
        "a.py": "class Same:\n    a: int\n",
        "z.py": "class Same:\n    z: int\n",
        "use.py": (
            "class Outer:\n"
            "    class Same:\n"
            "        def mutate(this, /, ordinary):\n"
            "            this.field = 1\n"
            "            ordinary.field = 2\n"
            "def outer(ctx: Same):\n"
            "    alias = ctx\n"
            "    def inner(ctx: Same):\n"
            "        del ctx.value\n"
            "        consume(ctx, again=ctx)\n"
            "    return alias.value\n"
        ),
    }.items():
        path = tmp_path / "sample" / filename
        path.parent.mkdir(exist_ok=True)
        path.write_text(source)
        paths.append(path)
    parsed = parse_sources(paths, root=tmp_path, namespace="sample").modules
    initial = {}
    symbols, nodes, owners = collect_symbols(parsed, initial)
    facts, candidates = collect_state(
        parsed, tuple(parse_record(item) for item in symbols), nodes, owners
    )
    class_names = sorted(
        item.qualified_name for item in facts.classes if item.qualified_name.endswith(".Same")
    )
    expected = json.loads(
        (Path(__file__).parent / "fixtures/state-facts/duplicate-names.json").read_text()
    )
    for roots, case in (
        (tuple(class_names), 0),
        (tuple(reversed(class_names)), 0),
        ((class_names[0],), 1),
    ):
        contexts, details, used = evaluate_contexts(facts, symbols, [], [], roots, candidates)
        assert contexts == expected[case]["contexts"]
        assert details == expected[case]["context_evidence"]
        assert [asdict(item) for item in used if item.id not in initial] == [
            item for item in expected[case]["evidence"] if item["id"] not in initial
        ]


@pytest.mark.parametrize(
    ("case", "source"),
    enumerate(
        [
            "from typing import Any as T\ndef f(ctx: T):\n    return ctx.root._value\n",
            "from typing import Any as T\nT = object\ndef f(ctx: T):\n    return ctx._value\n",
            (
                "class C:\n    def f(self, unknown):\n        def nested(unknown):\n"
                "            return unknown._value\n        return unknown._secret\n"
            ),
        ]
    ),
)
def test_private_attribute_collection_matches_original(
    tmp_path: Path, case: int, source: str
) -> None:
    from archkeel.analyzer.python.private_attributes import collect_private_attributes

    path = tmp_path / "sample.py"
    path.write_text(source)
    parsed = parse_sources([path], root=tmp_path, namespace="sample").modules
    expected = json.loads(
        (Path(__file__).parent / "fixtures/state-facts/private-attributes.json").read_text()
    )[case]
    records, used = collect_private_attributes(parsed)
    assert records == tuple(parse_record(item) for item in expected["records"])
    assert [asdict(item) for item in used] == expected["evidence"]


def test_state_wire_roundtrip_rejects_unknown_event_shapes() -> None:
    from archkeel.ir.state_facts import Assignment, FunctionStateTrace, StateFacts

    facts = StateFacts(
        (),
        (
            FunctionStateTrace(
                "sample.f", "sample", None, None, (), (Assignment(("ctx",), "Bag", None, None),)
            ),
        ),
    )
    assert parse_state_data(state_data(facts)) == facts
    invalid = freeze_data(
        {
            "classes": [],
            "functions": [
                {
                    "scope": "sample.f",
                    "module": "sample",
                    "class_owner": None,
                    "receiver": None,
                    "parameters": [],
                    "events": [{"kind": "unknown"}],
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="event"):
        parse_state_data(invalid)


@pytest.mark.parametrize(
    "event",
    [
        {
            "kind": "assignment",
            "targets": "ctx",
            "constructor": None,
            "annotation": None,
            "alias": None,
        },
        {"kind": "pass", "binding": "ctx", "target": "f", "evidence_id": "e", "rule": "forbidden"},
        {"kind": "attribute", "binding": "ctx", "path": [], "access": "read", "evidence_id": "e"},
        {
            "kind": "attribute",
            "binding": "ctx",
            "path": ["append"],
            "access": "mutation",
            "evidence_id": "e",
        },
        {
            "kind": "attribute",
            "binding": "ctx",
            "path": ["value"],
            "access": "unknown",
            "evidence_id": "e",
        },
        {"kind": "pass", "binding": "ctx", "target": "f", "evidence_id": ""},
    ],
)
def test_state_wire_rejects_malformed_events(event: dict[str, object]) -> None:
    raw = freeze_data(
        {
            "classes": [],
            "functions": [
                {
                    "scope": "sample.f",
                    "module": "sample",
                    "class_owner": None,
                    "receiver": None,
                    "parameters": [],
                    "events": [event],
                }
            ],
        }
    )
    with pytest.raises(ValueError):
        parse_state_data(raw)


@pytest.mark.parametrize("frozen", [0, 1, "true", None])
def test_state_wire_requires_boolean_class_flags(frozen: object) -> None:
    raw = freeze_data(
        {
            "classes": [
                {
                    "qualified_name": "sample.Bag",
                    "module": "sample",
                    "frozen": frozen,
                    "protocol": False,
                    "fields": [],
                    "methods": [],
                    "evidence_ids": [],
                }
            ],
            "functions": [],
        }
    )
    with pytest.raises(ValueError, match="boolean"):
        parse_state_data(raw)
