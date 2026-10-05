# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Same-named modules must not exchange definition-site proof."""

from pathlib import Path

import pytest

from archkeel.analyzer.python.collect import collect
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.source import parse_sources
from archkeel.analyzer.python.state import collect_state
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.ir.facts_codec import parse_record, thaw_data
from archkeel.ir.protocol import (
    CollectionRequest,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)


def _modules(root: Path, texts: dict[str, str], *, reverse: bool = False):
    paths = []
    for name, text in texts.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        paths.append(path)
    return parse_sources(sorted(paths, reverse=reverse), root=root, namespace="sample").modules


@pytest.mark.parametrize("reverse", [False, True])
def test_same_module_classes_keep_their_own_decorator_aliases(tmp_path: Path, reverse: bool):
    modules = _modules(
        tmp_path,
        {
            "sample/m.py": (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True)\nclass C:\n value: int\n"
            ),
            "sample/m/__init__.py": "class C: pass\n",
        },
        reverse=reverse,
    )
    evidence = {}
    collect_imports(modules, {"sample.m"}, evidence, namespace="sample")
    symbols, _, _ = collect_symbols(modules, evidence)
    actual = {
        evidence[item["evidence_ids"][0]]["file"]: (
            item["data"]["class_kind"],
            item["data"]["frozen_object"],
        )
        for item in symbols
        if item["kind"] == "class"
    }
    assert actual == {
        "sample/m.py": ("dataclass", True),
        "sample/m/__init__.py": ("class", False),
    }


def test_class_inventory_does_not_borrow_another_module_global(tmp_path: Path):
    _modules(
        tmp_path,
        {
            "sample/m.py": (
                "class C:\n class Nested:\n  global staticmethod\n"
                "  staticmethod = None\n @staticmethod\n def method(): pass\n"
            ),
            "sample/m/__init__.py": "class C: pass\n",
        },
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    evidence = {item.id: item for item in facts.evidence}
    [empty] = [
        item
        for section in facts.sections
        if section.name == "symbols"
        for item in section.records
        if item.kind == "class" and evidence[item.evidence_ids[0]].file == "sample/m/__init__.py"
    ]
    assert [item["status"] for item in thaw_data(empty.data)["member_inventories"]] == [
        "complete",
        "complete",
    ]


def test_conditional_collision_keeps_state_evidence_at_its_definition(tmp_path: Path):
    modules = _modules(
        tmp_path,
        {
            "sample/m.py": "class C:\n value: int\n",
            "sample/m/__init__.py": "if flag:\n class C:\n  alternative: str\n",
        },
        reverse=True,
    )
    symbols, nodes, owners = collect_symbols(modules, {})
    facts, evidence = collect_state(
        modules, tuple(parse_record(item) for item in symbols), nodes, owners
    )
    assert len(facts.classes) == 1
    assert {item.file for item in evidence} == {"sample/m.py"}
