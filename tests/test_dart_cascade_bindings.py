# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A local variable in a closure is one binding, also when a local declaration encloses it."""

from __future__ import annotations

from pathlib import Path

from dart_native_helpers import collect_native_dart, require_native_dart

from archkeel.analyzer.dart.parse import parse
from archkeel.ir.protocol import CollectionRequest, DartSettings, SnapshotInput, SourceScope

_CASCADE_CLOSURE = b"""void f(List<int> values) {
  final sorted = [...values]..sort((a, b) {
    final order = a.compareTo(b);
    return order;
  });
}
"""


def test_closure_in_a_cascade_gives_each_local_variable_one_binding_site() -> None:
    syntax = parse(_CASCADE_CLOSURE)

    names = [site.assigned_name for site in syntax.sites if site.assigned_name]

    assert sorted(names) == ["order", "sorted"]


def test_collector_answers_for_a_closure_in_a_cascade(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text(
        "name: sample\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n", encoding="utf-8"
    )
    source = tmp_path / "lib" / "sorting.dart"
    source.parent.mkdir()
    source.write_bytes(_CASCADE_CLOSURE)
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("lib",), "sample"),
        DartSettings(),
    )

    facts = require_native_dart(collect_native_dart(request))

    bindings = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "binding"
    ]
    assert len(bindings) == 2


def test_closure_assigned_to_a_local_variable_gives_each_variable_one_binding_site() -> None:
    syntax = parse(b"void f() {\n  final g = () {\n    final h = 1;\n    return h;\n  };\n}\n")

    names = [site.assigned_name for site in syntax.sites if site.assigned_name]

    assert sorted(names) == ["g", "h"]
