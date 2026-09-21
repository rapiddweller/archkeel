# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""`boundary_type_indexes` (`archkeel/analyzer/embedded/violations.py`) builds
`imports_by_binding` and `classes_by_location` as last-write-wins dict comprehensions over
`imports`/`symbols` in the order the scan hands them over -- sorted by content-hash id, not
source order. A module that binds one name twice (two top-level classes of the same name, or
two imports bound to the same local name) makes that order decide which of the two candidate
records the index keeps, and Python's own binding rule (whichever one is textually last) is
not what decides it.

Two consequences, pinned below:

  1. A crash that destroys the whole scan. `symbols.py::_resolve_class_kinds` keys its
     fixpoint by qualified name, so of two same-named top-level classes only the record
     `symbol_by_name` happens to keep gets a `class_kind` at all; the other keeps none.
     `_boundary_type_verdict` then does `origin_symbol["class_kind"]` -- a bare subscript --
     and raises `KeyError` if the index happens to keep the record missing it.

  2. A wrong PASS or a wrong VIOLATION. Two imports bound to the same local name, one
     declared by its component and one not: whichever the index keeps decides the verdict,
     with no relation to which import is actually live in the module.

The intended fix: a name bound twice in one module is something the analyzer cannot resolve
from what it records, so the honest answer is unresolvable (undecidable), not a coin flip --
never a crash, never a guessed PASS or VIOLATION.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from test_analyzer import _component, _observe

from archkeel.analyzer.embedded.records import RawRecord
from archkeel.analyzer.embedded.source import ParsedModule
from archkeel.analyzer.embedded.symbols import collect_symbols
from archkeel.analyzer.embedded.violations import boundary_type_indexes
from archkeel.ir.trace import trace_valid_violations


def _boundary_types_contract(*components: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "components": list(components),
        "rules": [
            {
                "id": "APP-TYPES-NOT-DICT",
                "kind": "boundary_types",
                "source": "sample.app",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }


def _parsed_module(source: str) -> ParsedModule:
    return ParsedModule(
        path=Path("sample/app/facade.py"),
        rel_path="sample/app/facade.py",
        module="sample.app.facade",
        package="sample.app",
        source=source,
        source_bytes=source.encode(),
        lines=source.splitlines(),
        tree=ast.parse(source),
    )


def test_two_same_named_top_level_classes_leave_one_symbol_record_without_a_class_kind() -> None:
    """Pins the precondition for the crash directly on `collect_symbols`, independent of
    whatever order `boundary_type_indexes` later receives the records in (AD-30's fixpoint
    keys by qualified name, so of two same-named classes only one -- whichever
    `symbol_by_name` happens to keep -- is ever visited by `_resolve_class_kinds`). This
    holds regardless of the content-hash order `collect_symbols` returns records in, so it
    proves the ingredient for the crash exists without depending on that order's luck.
    """
    source = "class Order:\n    pass\n\n\nclass Order:\n    pass\n"
    symbols, _nodes, _owners = collect_symbols([_parsed_module(source)], {})
    order_records = [item for item in symbols if item["data"]["name"] == "Order"]
    assert len(order_records) == 2
    with_class_kind = [item for item in order_records if "class_kind" in item["data"]]
    without_class_kind = [item for item in order_records if "class_kind" not in item["data"]]
    assert len(with_class_kind) == 1
    assert len(without_class_kind) == 1


def test_two_same_named_top_level_classes_crash_boundary_types_through_observe(
    tmp_path: Path,
) -> None:
    """The real analyzer entry point, run end to end: today this crashes with `KeyError:
    'class_kind'` inside the bundled analyzer subprocess, which `archkeel.analyzer.observe`
    can only report as an opaque `parse_error` -- the whole scan is lost, not just this one
    rule's verdict.

    Made deterministic rather than order-lucky: `stable_id` derives every record's id from a
    sha256 of its own content (`archkeel/ir/model.py::stable_id`), never from `id()` or a
    per-run seed, so for this exact, fixed source text the content-hash order
    `boundary_type_indexes` receives the two `Order` records in is itself fixed and
    reproduces the same outcome on every run and on every machine. This was confirmed by
    actually running the scenario (see the module docstring's own description of the bug)
    rather than assumed from reading the code; it is pinned here as today's actually
    observed behaviour, not as a claim that a `KeyError` is inherent to any such module (a
    module with the unlucky opposite hash order would silently misjudge the position
    instead, which is exactly why the fix must remove the order-dependence itself, not just
    patch around this one crash).
    """
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:snapshot"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "class Order:\n"
        "    pass\n\n\n"
        "class Order:\n"
        "    pass\n\n\n"
        "def snapshot(order: Order) -> str:\n"
        "    return str(order)\n"
    )
    result = _observe(tmp_path)
    # Today: exit_code == 2, one parse_error diagnostic whose claim carries a
    # "KeyError: 'class_kind'" traceback from inside the analyzer subprocess. Fixed: the scan
    # completes and this now-unresolvable position is reported the same way any other
    # unresolved name is, never as a crash that discards the whole observation.
    assert result.exit_code == 0
    assert result.diagnostics == ()


def test_ambiguous_import_binding_reports_the_position_as_undecidable_not_a_guess(
    tmp_path: Path,
) -> None:
    """A module that binds one name to two different imports -- one declared by its owning
    component, one not -- makes `imports_by_binding`'s last-write-wins pick decide the
    `boundary_types` verdict, with no relation to which import is actually live in Python
    (the textually last one, `sample.core.undeclared.Thing` here). Confirmed by running this
    exact fixture: today it decides both of `snapshot`'s two positions (`thing`'s parameter
    and its `str` return) -- a wrong PASS on the ambiguous one, since the index happens to
    keep the *declared* import for this fixed source text, even though the binding actually
    live in the module is the undeclared one. The fix must report that one position as
    undecidable instead, leaving exactly one of the two positions (the plain `str` return)
    decided.
    """
    contract = {
        "schema_version": "2.1.0",
        "components": [
            _component("core", public=["sample.core.declared:Thing"]),
            _component("app", public=["sample.app.facade:snapshot"]),
        ],
        "rules": [
            {
                "id": "APP-TYPES-NOT-DICT",
                "kind": "boundary_types",
                "source": "sample.app",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/core/__init__.py").write_text("")
    (tmp_path / "sample/core/declared.py").write_text("class Thing:\n    pass\n")
    (tmp_path / "sample/core/undeclared.py").write_text("class Thing:\n    pass\n")
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "from sample.core.declared import Thing\n"
        "from sample.core.undeclared import Thing\n\n\n"
        "def snapshot(thing: Thing) -> str:\n"
        "    return str(thing)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    # No wrong VIOLATION either way: this pins the worse of the two defects the bug report
    # names, a wrong PASS, but a wrong VIOLATION would be just as much a guess.
    assert trace_valid_violations(result.observation) == ()
    limits = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    ]
    assert len(limits) == 1
    data = limits[0].data
    # Two positions: `thing`'s ambiguous `Thing` parameter and its plain `str` return.
    # Today the ambiguous binding is silently decided too: (positions, decided) == (2, 2).
    # Fixed: only the `str` return is decided, and the ambiguous `Thing` position is counted
    # as undecided, one of `_UNDECIDABLE_KINDS`.
    assert (data.get("positions"), data.get("decided")) == (2, 1)
    assert data.get("undecided") == 1


def _class_symbol(module: str, name: str, marker: str) -> RawRecord:
    return {
        "id": f"SYM-{marker}",
        "evidence_class": "FACT",
        "area": "repository_topology",
        "kind": "class",
        "title": name,
        "subjects": [],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {"module": module, "name": name, "parent": None, "marker": marker},
    }


def _import_record(module: str, binding: str, marker: str) -> RawRecord:
    return {
        "id": f"IMP-{marker}",
        "evidence_class": "FACT",
        "area": "dependency_violations",
        "kind": "import",
        "title": binding,
        "subjects": [],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {
            "source_module": module,
            "binding": binding,
            "symbol": binding,
            "origin_definition": f"other.{marker}.{binding}",
            "marker": marker,
        },
    }


def test_boundary_type_indexes_does_not_let_input_order_decide_an_ambiguous_class_location() -> (
    None
):
    """Regression guard: nothing about `(module, name)` naming two distinct top-level classes
    tells `boundary_type_indexes` which one is actually live, so the entry it builds for that
    key must not depend on which of the two candidate records happens to come last in the
    sequence it is handed -- that is exactly the "arbitrary last wins" this bug is. Today the
    dict comprehension keeps whichever record is last, so reversing the input reverses the
    answer; a fix that makes ambiguity honestly unresolvable must produce the *same* entry
    (present or absent, but never "whichever came last") no matter the input order.
    """
    first = _class_symbol("sample.app.facade", "Order", "first")
    second = _class_symbol("sample.app.facade", "Order", "second")
    _imports_forward, classes_forward = boundary_type_indexes([first, second], [])
    _imports_backward, classes_backward = boundary_type_indexes([second, first], [])
    key = ("sample.app.facade", "Order")
    assert classes_forward.get(key) == classes_backward.get(key)


def test_boundary_type_indexes_does_not_let_input_order_decide_an_ambiguous_import_binding() -> (
    None
):
    """The same guard for `imports_by_binding`: two imports bound to the same local name in
    one module must resolve to the same answer regardless of which one `imports` happens to
    list last, not to whichever record wins the last-write in a plain dict comprehension.
    """
    first = _import_record("sample.app.facade", "Thing", "first")
    second = _import_record("sample.app.facade", "Thing", "second")
    imports_forward, _classes_forward = boundary_type_indexes([], [first, second])
    imports_backward, _classes_backward = boundary_type_indexes([], [second, first])
    key = ("sample.app.facade", "Thing")
    assert imports_forward.get(key) == imports_backward.get(key)
