# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Index order must never decide API ownership for an ambiguous binding.

Every class definition keeps its kind. A repeated identical import stays one target;
distinct bindings stay undecidable across imports, classes and functions.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from test_analyzer import _component, _observe

from archkeel.analyzer.python.source import ParsedModule
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.check.evaluation.rules import boundary_type_indexes
from archkeel.ir.facts_codec import RawRecord
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


def test_builtin_named_functions_are_undecidable_through_observe(tmp_path: Path) -> None:
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:snapshot"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "def dict() -> None:\n"
        "    return None\n\n\n"
        "def object() -> None:\n"
        "    return None\n\n\n"
        "def snapshot(mapping: dict, value: object) -> str:\n"
        "    return str(mapping) + str(value)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    limit = next(
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    )
    assert (limit.data.get("positions"), limit.data.get("decided")) == (3, 1)
    assert limit.data.get("ambiguous_binding") == 2


def test_two_same_named_top_level_classes_each_keep_their_class_kind() -> None:
    """Definition-site identities prevent one classification from overwriting another."""
    source = "class Order:\n    pass\n\n\nclass Order:\n    pass\n"
    symbols, _nodes, _owners = collect_symbols([_parsed_module(source)], {})
    order_records = [item for item in symbols if item["data"]["name"] == "Order"]
    assert len(order_records) == 2
    assert all(item["data"].get("class_kind") == "class" for item in order_records)


def test_redefined_top_level_classes_keep_the_scan_and_binding_uncertainty(
    tmp_path: Path,
) -> None:
    """A classifier fix must not turn an ambiguous binding into a proven API type."""
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
    assert result.exit_code == 0
    assert result.diagnostics == ()
    assert result.observation is not None
    assert any(
        item.kind == "boundary_type_limit" and item.data.get("ambiguous_binding") == 1
        for item in result.observation.records("unknowns") or ()
    )


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


def test_import_and_local_class_with_one_name_is_undecidable_through_observe(
    tmp_path: Path,
) -> None:
    contract = _boundary_types_contract(
        _component("core", public=["sample.core.types:Thing"]),
        _component("app", public=["sample.app.facade:snapshot"]),
    )
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/core/__init__.py").write_text("")
    (tmp_path / "sample/core/types.py").write_text("class Thing:\n    pass\n")
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "from sample.core.types import Thing\n\n\n"
        "class Thing:\n"
        "    pass\n\n\n"
        "def snapshot(thing: Thing) -> str:\n"
        "    return str(thing)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    limit = next(
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    )
    assert (limit.data.get("positions"), limit.data.get("decided")) == (2, 1)
    assert limit.data.get("ambiguous_binding") == 1


def test_class_and_function_with_one_name_is_undecidable_through_observe(
    tmp_path: Path,
) -> None:
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:snapshot"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "class Order:\n"
        "    pass\n\n\n"
        "def Order() -> None:\n"
        "    return None\n\n\n"
        "def snapshot(order: Order) -> str:\n"
        "    return str(order)\n"
    )

    result = _observe(tmp_path)

    assert result.exit_code == 0
    assert result.diagnostics == ()
    assert result.observation is not None
    limit = next(
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    )
    assert (limit.data.get("positions"), limit.data.get("decided")) == (2, 1)
    assert limit.data.get("ambiguous_binding") == 1


def test_import_and_local_function_with_one_name_is_undecidable_through_observe(
    tmp_path: Path,
) -> None:
    contract = _boundary_types_contract(
        _component("core", public=["sample.core.types:Thing"]),
        _component("app", public=["sample.app.facade:snapshot"]),
    )
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/core/__init__.py").write_text("")
    (tmp_path / "sample/core/types.py").write_text("class Thing:\n    pass\n")
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "from sample.core.types import Thing\n\n\n"
        "def Thing() -> None:\n"
        "    return None\n\n\n"
        "def snapshot(thing: Thing) -> str:\n"
        "    return str(thing)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    limit = next(
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    )
    assert (limit.data.get("positions"), limit.data.get("decided")) == (2, 1)
    assert limit.data.get("ambiguous_binding") == 1


def test_ambiguous_reexport_chain_is_undecidable_through_observe(tmp_path: Path) -> None:
    contract = _boundary_types_contract(
        _component("core", public=["sample.core.declared:Thing"]),
        _component("app", public=["sample.app.facade:snapshot"]),
    )
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/core/declared.py").write_text("class Thing:\n    pass\n")
    (tmp_path / "sample/core/undeclared.py").write_text("class Thing:\n    pass\n")
    (tmp_path / "sample/core/__init__.py").write_text(
        "from sample.core.declared import Thing\n\n\n\nfrom sample.core.undeclared import Thing\n"
    )
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "from sample.core import Thing\n\n\n"
        "def snapshot(thing: Thing) -> str:\n"
        "    return str(thing)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    limit = next(
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    )
    assert (limit.data.get("positions"), limit.data.get("decided")) == (2, 1)
    assert limit.data.get("ambiguous_binding") == 1


def test_direct_import_and_ambiguous_reexport_are_distinct_bindings(tmp_path: Path) -> None:
    contract = _boundary_types_contract(
        _component("core", public=["sample.core.declared:Thing"]),
        _component("app", public=["sample.app.facade:snapshot"]),
    )
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/core/declared.py").write_text("class Thing:\n    pass\n")
    (tmp_path / "sample/core/undeclared.py").write_text("class Thing:\n    pass\n")
    (tmp_path / "sample/core/__init__.py").write_text(
        "from sample.core.declared import Thing\n\n\n\nfrom sample.core.undeclared import Thing\n"
    )
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "from sample.core.declared import Thing\n"
        "from sample.core import Thing\n\n\n"
        "def snapshot(thing: Thing) -> str:\n"
        "    return str(thing)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    limit = next(
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    )
    assert (limit.data.get("positions"), limit.data.get("decided")) == (2, 1)
    assert limit.data.get("ambiguous_binding") == 1


def test_repeated_identical_module_and_function_imports_are_not_ambiguous(
    tmp_path: Path,
) -> None:
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:snapshot"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "from pathlib import Path\n\n\n"
        "def helper() -> Path:\n"
        "    from pathlib import Path\n"
        "    return Path('.')\n\n\n"
        "def snapshot(path: Path) -> str:\n"
        "    return str(path)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    limit = next(
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    )
    assert (limit.data.get("positions"), limit.data.get("decided")) == (2, 1)
    assert limit.data.get("external_type") == 1
    assert limit.data.get("ambiguous_binding") == 0


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
            "target_module": f"other.{marker}",
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
