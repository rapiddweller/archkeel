# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native Dart collector publishes declarations from complete source units."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from dart_native_helpers import collect_native_dart, require_native_dart

from archkeel.ir.facts_validation import validate_source_facts
from archkeel.ir.protocol import CollectionRequest, DartSettings, SnapshotInput, SourceScope

_REPO = Path(__file__).parents[1]


def test_native_process_collects_dart_declarations_and_member_coverage(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text(
        "name: commerce\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n", encoding="utf-8"
    )
    source = tmp_path / "lib/orders.dart"
    source.parent.mkdir()
    source.write_text(
        """typedef OrderId = String;
const currency = 'USD';

enum OrderStatus { draft, paid }

class Order {
  static const taxRate = 0.1;
  final OrderId id;
  final List<String> _items;
  Order(this.id, {List<String> items = const []}) : _items = items;
  String summary([String prefix = 'order']) => '$prefix:$id';
  static bool isEmpty(Order value) => value._items.isEmpty;
}

String describe(Order order, {required bool verbose}) =>
    verbose ? order.summary('verbose') : order.id;
""",
        encoding="utf-8",
    )
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("lib",), "commerce"),
        DartSettings(),
    )
    facts = require_native_dart(collect_native_dart(request))
    assert facts.profile == "archkeel-dart-analyzer"
    assert facts.runtime.name == "python"
    assert facts.adapter.name == "archkeel-dart-analyzer"
    assert len(facts.adapter.code_digest) == 64
    assert facts.source.source_digest
    inputs = {item.path: item for item in facts.inputs}
    assert set(inputs) == {"lib/orders.dart", "pubspec.yaml"}
    assert inputs["lib/orders.dart"].role == "selected"
    assert inputs["pubspec.yaml"].role == "resolution"
    assert (
        inputs["pubspec.yaml"].digest
        == hashlib.sha256((tmp_path / "pubspec.yaml").read_bytes()).hexdigest()
    )
    symbols = [
        record
        for section in facts.sections
        for record in section.records
        if section.name == "symbols"
    ]
    by_name = {record.data.get("name"): record for record in symbols if record.kind != "method"}
    assert {"Order", "OrderStatus", "OrderId", "currency", "describe"} <= set(by_name)
    order = by_name["Order"]
    data = order.data
    inventories = data.get("member_inventories")
    assert inventories[0].get("status") == "complete"
    assert inventories[1].get("status") == "complete"
    attributes = {item.get("name"): item for item in data.get("attribute_declarations")}
    assert set(attributes) == {"taxRate", "id", "_items"}
    assert {
        item.data.get("name")
        for item in symbols
        if item.data.get("parent") == "commerce.orders.Order"
    } >= {
        "Order",
        "summary",
        "isEmpty",
    }, [(item.data.get("name"), item.data.get("parent"), item.kind) for item in symbols]
    assert attributes["_items"].get("visibility").get("kind") == "private"
    assert attributes["taxRate"].get("static") is True
    assert by_name["describe"].data.get("parameters")[1].get("kind") == "keyword_only"
    assert by_name["describe"].data.get("parameters")[1].get("default") is None
    assert by_name["OrderStatus"].data.get("enum_members") == ("draft", "paid")
    assert facts.coverage.full_scope is True


@pytest.mark.parametrize(
    ("sdk_range", "full_scope"),
    [
        (">=2.0.0 <4.0.0", False),
        (">=2.12.0 <4.0.0", True),
        (">=2.19.0 <4.0.0", True),
        ("<4.0.0", False),
    ],
)
def test_native_process_rejects_unsupported_package_language_floor(
    tmp_path: Path, sdk_range: str, full_scope: bool
) -> None:
    _write_package(
        tmp_path,
        "class Order {}\n",
        pubspec=f"name: commerce\nenvironment:\n  sdk: '{sdk_range}'\n",
    )
    facts = _native_facts(tmp_path)
    assert facts.coverage.full_scope is full_scope
    if not full_scope:
        assert any(gap.kind == "SdkConstraintError" for gap in facts.coverage.gaps)


def test_native_process_marks_duplicate_declarations_incomplete(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text(
        "name: commerce\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n", encoding="utf-8"
    )
    source = tmp_path / "lib/orders.dart"
    source.parent.mkdir()
    source.write_text(
        "class Duplicate { final String id = ''; }\nclass Duplicate {}\n", encoding="utf-8"
    )
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("lib",), "commerce"),
        DartSettings(),
    )
    facts = require_native_dart(collect_native_dart(request))
    assert facts.coverage.full_scope is False
    assert any(gap.kind == "DuplicateDeclaration" for gap in facts.coverage.gaps)
    duplicate = next(
        record
        for section in facts.sections
        for record in section.records
        if section.name == "symbols" and record.kind == "class"
    )
    assert duplicate.data.get("source_binding_unique") is False


def test_native_process_keeps_part_declaration_in_library_module(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text(
        "name: commerce\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n", encoding="utf-8"
    )
    main = tmp_path / "lib/main.dart"
    part = tmp_path / "lib/parts/item.dart"
    main.parent.mkdir()
    part.parent.mkdir()
    main.write_text("part 'parts/item.dart';\n", encoding="utf-8")
    part.write_text("part of '../main.dart';\nclass PartThing {}\n", encoding="utf-8")
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("lib",), "commerce"),
        DartSettings(),
    )
    facts = require_native_dart(collect_native_dart(request))
    declaration = next(
        record
        for section in facts.sections
        for record in section.records
        if section.name == "symbols" and record.data.get("name") == "PartThing"
    )
    assert declaration.data.get("module") == "commerce.main"
    evidence = next(item for item in facts.evidence if item.id in declaration.evidence_ids)
    assert evidence.file == "lib/parts/item.dart"
    assert facts.coverage.full_scope is True


def test_native_declarations_match_the_independently_reviewed_checkout_target() -> None:
    import json

    fixture = _REPO / "fixtures/H-uml-dart"
    request = CollectionRequest(
        SnapshotInput(str(fixture), "7" * 40, True),
        SourceScope(("lib",), "commerce"),
        DartSettings(),
    )
    facts = require_native_dart(collect_native_dart(request))
    assert facts.coverage.full_scope is True, facts.coverage.gaps

    actual = {
        record.data.get("qualified_name"): record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    }
    attributes: dict[str, dict[str, object]] = {}
    enum_literals: dict[str, set[str]] = {}
    for qualified_name, record in actual.items():
        if record.kind == "class":
            data = dict(record.data.entries)
            for attribute in data.get("attribute_declarations", ()):
                attribute_data = dict(attribute.entries)
                attributes[f"{qualified_name}.{attribute_data['name']}"] = attribute_data
            if data.get("class_kind") == "enum":
                enum_literals[qualified_name] = set(data.get("enum_members", ()))

    target_entities = []
    for contract in (
        fixture / "architecture-contract.json",
        *sorted((fixture / "contracts").glob("*.json")),
    ):
        payload = json.loads(contract.read_text(encoding="utf-8"))
        target_entities.extend(payload["declarations"]["uml"]["entities"])
    by_id = {item["id"]: item for item in target_entities}

    represented = {
        "class",
        "interface",
        "enum",
        "enum_literal",
        "method",
        "function",
        "attribute",
        "type_alias",
        "constant",
    }
    for expected in target_entities:
        if expected.get("presence") != "planned" or expected["kind"] not in represented:
            continue
        name = expected["qualified_name"]
        kind = expected["kind"]
        if kind == "attribute":
            found = attributes[name]
            assert found["annotation"] == expected.get("annotation"), name
            visibility = dict(found["visibility"].entries)
            assert visibility["kind"] == expected["visibility"]["kind"], name
            assert found["static"] is ("static" in expected.get("modifiers", [])), name
            continue
        if kind == "enum_literal":
            parent = by_id[expected["parent_id"]]["qualified_name"]
            assert name.rsplit(".", 1)[-1] in enum_literals[parent], name
            continue
        record = actual[name]
        expected_record_kind = (
            "class"
            if kind in {"class", "interface", "enum"}
            else {"type_alias": "alias"}.get(kind, kind)
        )
        assert record.kind == expected_record_kind, name
        data = dict(record.data.entries)
        if kind in {"class", "interface", "enum"}:
            expected_class_kind = {"class": "class", "interface": "protocol", "enum": "enum"}[kind]
            assert data["class_kind"] == expected_class_kind, name
        if kind in {"method", "function"}:
            signature = expected.get("signature", {})
            actual_parameters = [dict(parameter.entries) for parameter in data["parameters"]]
            expected_parameters = signature.get("parameters", [])
            assert len(actual_parameters) == len(expected_parameters), name
            for actual_parameter, expected_parameter in zip(
                actual_parameters, expected_parameters, strict=True
            ):
                for key in ("name", "annotation", "kind"):
                    assert actual_parameter.get(key) == expected_parameter.get(key), name
                if "default" in expected_parameter:
                    assert actual_parameter.get("default") == expected_parameter["default"], name
                else:
                    assert actual_parameter.get("default") is None, name
            assert data["returns"] == signature.get("returns"), name

    for classifier in (
        item
        for item in target_entities
        if item.get("presence") == "planned" and item["kind"] in {"class", "interface", "enum"}
    ):
        name = classifier["qualified_name"]
        observed_members = {
            member.rsplit(".", 1)[-1]
            for member in [
                *attributes,
                *(
                    name
                    for name, record in actual.items()
                    if record.data.get("parent") == classifier["qualified_name"]
                ),
            ]
            if member.startswith(name + ".")
        } | enum_literals.get(name, set())
        expected_members = {
            item["qualified_name"].rsplit(".", 1)[-1]
            for item in target_entities
            if item.get("presence") == "planned" and item.get("parent_id") == classifier["id"]
        }
        assert observed_members == expected_members, name


def test_native_sites_project_all_reviewed_target_relationships() -> None:
    import json
    from hashlib import sha256

    from archkeel.check.uml_compare import compare_graphs
    from archkeel.ir.codec import load_inside_contract_tree, parse_contract
    from archkeel.ir.target_graph import declared_tree_graph

    root = _REPO / "fixtures/H-uml-dart"
    facts = _native_facts(root)
    graph = _source_graph(facts)
    target_entities = []
    target_relationships = []
    root_payload = json.loads((root / "architecture-contract.json").read_text(encoding="utf-8"))
    target_entities.extend(root_payload["declarations"]["uml"]["entities"])
    target_relationships.extend(root_payload["declarations"]["uml"]["relationships"])
    for path in sorted((root / "contracts").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        target_entities.extend(payload["declarations"]["uml"]["entities"])
        target_relationships.extend(payload["declarations"]["uml"]["relationships"])
    declarations = {item["id"]: item["qualified_name"] for item in target_entities}
    expected = {
        (item["kind"], declarations[item["source_id"]], declarations[item["target_id"]])
        for item in target_relationships
        if item["kind"] in {"inherits", "realizes", "calls", "references", "creates", "instance_of"}
    }
    assert len(expected) == 20
    by_id = {item.id: item for item in graph.entities}
    observed = {
        (item.kind, by_id[item.source_id].qualified_name, by_id[item.target_id].qualified_name)
        for item in graph.relationships
        if item.resolution == "resolved" and item.target_id is not None
    }
    assert expected <= observed, sorted(expected - observed)
    checkout_save = next(
        dict(record.data.entries)
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if record.data.get("expression") == "_repository.save(order)"
    )
    assert checkout_save["targets"] == (
        "commerce.ordering.ports.order_repository.OrderRepository.save",
    )
    assert not any("InMemoryOrderRepository.save" in name for name in checkout_save["targets"])
    root_bytes = (root / "architecture-contract.json").read_bytes()
    tree = load_inside_contract_tree(
        "architecture-contract.json",
        parse_contract(json.loads(root_bytes)),
        sha256(root_bytes).hexdigest(),
        "architecture-contract.json",
        lambda path: ((root / path).read_bytes(), path),
    )
    target = declared_tree_graph(tree, root_path="architecture-contract.json")
    comparison = compare_graphs(graph, target)
    relationship_assessments = [
        item for item in comparison.assessments if item.aspect == "relationship"
    ]
    assert len(relationship_assessments) == 20
    assert all(item.status == "PASS" for item in relationship_assessments), relationship_assessments


def test_native_local_binding_reference_projects_without_fabricated_call(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """class Order { final String id = ''; }
String receipt(Order order) { final receiptId = order.id; return receiptId; }
""",
    )
    facts = _native_facts(tmp_path)
    graph = _source_graph(facts)
    by_id = {item.id: item for item in graph.entities}
    binding = next(item for item in graph.entities if item.kind == "binding")
    assert binding.qualified_name == "commerce.main.receipt.receiptId"
    assert binding.initializer == "order.id"
    assert any(
        item.kind == "references"
        and item.source_id == binding.id
        and item.target_id is not None
        and by_id[item.target_id].qualified_name == "commerce.main.Order.id"
        for item in graph.relationships
    )
    assert not facts.sections[[section.name for section in facts.sections].index("calls")].records


def test_native_typedef_bases_resolve_to_the_aliased_classifier(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """class Base {}
typedef Alias = Base;
class Child extends Alias {}
class Implements implements Alias {}
""",
    )
    facts = _native_facts(tmp_path)
    graph = _source_graph(facts)
    by_id = {item.id: item for item in graph.entities}
    bases = {
        (item.kind, by_id[item.source_id].qualified_name): (
            by_id[item.target_id].qualified_name if item.target_id else None,
            item.resolution,
        )
        for item in graph.relationships
        if item.kind in {"inherits", "realizes"}
    }
    assert bases[("inherits", "commerce.main.Child")] == (
        "commerce.main.Base",
        "resolved",
    )
    assert bases[("realizes", "commerce.main.Implements")] == (
        "commerce.main.Base",
        "resolved",
    )


def test_native_mixin_declarations_and_with_compositions_are_shared_classifier_facts(
    tmp_path: Path,
) -> None:
    _write_package(
        tmp_path,
        """part 'main.freezed.dart';
class Root {}
class Base extends Root {}
class Child extends Base with Stamp, Track, Shared {}
enum Status with Track { started, ended }
""",
    )
    (tmp_path / "lib/main.freezed.dart").write_text(
        """part of 'main.dart';
mixin Stamp on Root { String get stamp => 'stamp'; }
mixin Track {}
mixin class Shared {}
mixin _$Order { String get id; }
class Order with _$Order {}
""",
        encoding="utf-8",
    )

    facts = _native_facts(tmp_path)
    graph = _source_graph(facts)
    by_id = {item.id: item for item in graph.entities}
    by_name = {item.qualified_name: item for item in graph.entities}
    symbols = [
        item for section in facts.sections if section.name == "symbols" for item in section.records
    ]
    mixin_records = {
        item.data.get("qualified_name"): item
        for item in symbols
        if item.data.get("class_kind") == "mixin"
    }
    assert set(mixin_records) == {
        "commerce.main.Stamp",
        "commerce.main.Track",
        "commerce.main._$Order",
    }
    assert {name for name, entity in by_name.items() if entity.kind == "mixin"} == set(
        mixin_records
    )
    assert by_name["commerce.main.Shared"].kind == "class"
    assert "mixin" in by_name["commerce.main.Shared"].modifiers
    assert by_name["commerce.main._$Order.id::getter"].kind == "method"
    assert (
        by_name["commerce.main._$Order.id::getter"].parent_id == by_name["commerce.main._$Order"].id
    )

    edges = {
        (
            by_id[edge.source_id].qualified_name,
            edge.kind,
            by_id[edge.target_id].qualified_name if edge.target_id else None,
        )
        for edge in graph.relationships
        if edge.kind in {"inherits", "mixes_in"}
    }
    assert edges == {
        ("commerce.main.Base", "inherits", "commerce.main.Root"),
        ("commerce.main.Child", "inherits", "commerce.main.Base"),
        ("commerce.main.Child", "mixes_in", "commerce.main.Stamp"),
        ("commerce.main.Child", "mixes_in", "commerce.main.Track"),
        ("commerce.main.Child", "mixes_in", "commerce.main.Shared"),
        ("commerce.main.Status", "mixes_in", "commerce.main.Track"),
        ("commerce.main.Order", "mixes_in", "commerce.main._$Order"),
    }
    assert ("commerce.main.Child", "inherits", "commerce.main.Stamp") not in edges
    evidence = {item.id: item for item in facts.evidence}
    generated = mixin_records["commerce.main._$Order"]
    assert evidence[generated.evidence_ids[0]].file == "lib/main.freezed.dart"
    assert any(
        gap.kind == "UnsupportedDeclaration" and "on" in gap.title for gap in facts.coverage.gaps
    )
    assert any(
        receipt.scope_id == by_name["commerce.main.Stamp"].id
        and "mixes_in" in receipt.relationship_kinds
        and receipt.status == "partial"
        for receipt in graph.coverage
    )

    symbol_index = next(
        index for index, section in enumerate(facts.sections) if section.name == "symbols"
    )
    symbol_section = facts.sections[symbol_index]
    symbol_index_in_section = next(
        index
        for index, record in enumerate(symbol_section.records)
        if record.data.get("base_declarations")
    )
    symbol_record = symbol_section.records[symbol_index_in_section]
    bases = symbol_record.data.get("base_declarations")
    invalid_base = replace(
        bases[0],
        entries=tuple(
            (key, "compose") if key == "relationship_kind" else (key, value)
            for key, value in bases[0].entries
        ),
    )
    invalid_record = replace(
        symbol_record,
        data=replace(
            symbol_record.data,
            entries=tuple(
                (key, (invalid_base, *bases[1:])) if key == "base_declarations" else (key, value)
                for key, value in symbol_record.data.entries
            ),
        ),
    )
    invalid_section = replace(
        symbol_section,
        records=tuple(
            invalid_record if index == symbol_index_in_section else record
            for index, record in enumerate(symbol_section.records)
        ),
    )
    invalid_facts = replace(
        facts,
        sections=tuple(
            invalid_section if index == symbol_index else section
            for index, section in enumerate(facts.sections)
        ),
    )
    with pytest.raises(ValueError, match="invalid typed base declaration"):
        validate_source_facts(invalid_facts)


def test_native_with_clause_does_not_confirm_an_ordinary_class_as_a_mixin(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        "class Ordinary {}\nclass InvalidUse with Ordinary {}\n",
    )
    facts = _native_facts(tmp_path)
    graph = _source_graph(facts)
    entities = {item.id: item for item in graph.entities}
    [edge] = [item for item in graph.relationships if item.kind == "mixes_in"]
    assert entities[edge.source_id].qualified_name == "commerce.main.InvalidUse"
    assert edge.target_id is None
    assert edge.resolution == "unresolved"
    assert edge.reason and "mixin" in edge.reason.lower()


def test_native_sites_keep_unprovable_and_shadowed_bindings_unknown(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """import 'model.dart' as m show Widget;
import 'hidden.dart' hide Hidden;
import 'package:absent/external.dart';

class UsesMixin with LocalMixin {}
mixin LocalMixin {}
extension TextTools on String { String get reversed => this; }

class Widget {
  Widget.named();
  factory Widget.factory() => Widget.named();
  static void run() {}
}

class Repeated { void run() {} }
class Repeated { void run() {} }

void helper() {}
void main() {
  m.Widget.run();
  final named = m.Widget.named();
  final factory = Widget.factory();
  final helper = () {};
  helper();
  Missing.run();
  Hidden.run();
  dynamic value;
  value.run();
  Repeated().run();
}
""",
    )
    (tmp_path / "lib/model.dart").write_text(
        "class Widget { Widget.named(); static void run() {} }\n", encoding="utf-8"
    )
    (tmp_path / "lib/hidden.dart").write_text(
        "class Hidden { static void run() {} }\n", encoding="utf-8"
    )
    facts = _native_facts(tmp_path)
    calls = [
        dict(record.data.entries)
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
    ]
    assert next(item for item in calls if item["expression"] == "m.Widget.run()")["targets"] == (
        "commerce.model.Widget.run",
    )
    for expression in ("helper()", "Missing.run()", "Hidden.run()", "value.run()"):
        site = next(item for item in calls if item["expression"] == expression)
        assert site["status"] == "unresolved", (expression, site)
        assert site["targets"] == (), (expression, site)

    constructions = {
        item["expression"]: dict(item["construction"].entries)
        for item in calls
        if item.get("construction") is not None
    }
    assert constructions["m.Widget.named()"]["status"] == "resolved"
    assert constructions["Widget.factory()"]["status"] == "partially_resolved"
    repeated = next(item for item in calls if item["expression"] == "Repeated()")
    assert repeated["status"] == "unresolved"
    assert repeated["targets"] == ()
    assert repeated.get("construction") is None
    graph = _source_graph(facts)
    repeated_run = next(
        item
        for item in graph.relationships
        if item.kind == "calls" and item.expression == "Repeated().run()"
    )
    assert repeated_run.resolution == "partial"
    assert facts.coverage.full_scope is False
    assert any(gap.kind == "DuplicateDeclaration" for gap in facts.coverage.gaps)
    assert not any(
        gap.kind == "UnsupportedDeclaration" and "mixin declarations" in gap.title
        for gap in facts.coverage.gaps
    )
    assert any(
        gap.kind == "UnsupportedDeclaration" and "extension" in gap.title.lower()
        for gap in facts.coverage.gaps
    )


def test_native_missing_named_constructor_is_not_a_resolved_construction(
    tmp_path: Path,
) -> None:
    _write_package(
        tmp_path,
        """class Widget {}
void main() {
  final implicit = Widget();
  final missing = Widget.missing();
  final explicitMissing = new Widget.missing();
}
""",
    )
    facts = _native_facts(tmp_path)
    sites = {
        item["expression"]: item
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if (item := dict(record.data.entries)).get("expression")
    }
    assert dict(sites["Widget()"]["construction"].entries) == {
        "status": "resolved",
        "targets": ("commerce.main.Widget",),
        "candidates_truncated": False,
        "reason": "Analyzer resolved a local generative constructor",
    }
    assert sites["Widget.missing()"]["status"] == "unresolved"
    assert sites["Widget.missing()"]["targets"] == ()
    explicit = dict(sites["new Widget.missing()"]["construction"].entries)
    assert explicit["status"] == "unresolved"
    assert explicit["targets"] == ()


def test_native_generic_redirected_factory_stays_unknown_in_core_graph(tmp_path: Path) -> None:
    from archkeel.check.uml_compare import compare_graphs
    from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, Relationship

    _write_package(
        tmp_path,
        """abstract interface class Repository<T> {
  factory Repository() = MemoryRepository<T>;
}
class MemoryRepository<T> implements Repository<T> {
  MemoryRepository();
}
Repository<int> make() => Repository<int>();
""",
    )

    facts = _native_facts(tmp_path)
    factory_call = next(
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if record.data.get("expression") == "Repository<int>()"
    )
    assert factory_call.data.get("status") == "resolved"
    assert factory_call.data.get("targets") == ("commerce.main.Repository",)
    assert factory_call.data.get("construction").get("status") == "partially_resolved"

    graph = _source_graph(facts)
    names = {entity.id: entity.qualified_name for entity in graph.entities}
    [creation] = [
        edge
        for edge in graph.relationships
        if edge.kind == "creates" and edge.expression == "Repository<int>()"
    ]
    assert creation.resolution == "partial"
    assert creation.target_id is None
    assert names[creation.candidate_ids[0]] == "commerce.main.Repository"

    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "make",
                "function",
                "commerce.main.make",
                "dart",
                presence="planned",
                provenance=("test",),
            ),
            Entity(
                "repository",
                "interface",
                "commerce.main.Repository",
                "dart",
                presence="planned",
                provenance=("test",),
            ),
        ),
        (Relationship("factory-create", "creates", "make", "repository", provenance=("test",)),),
    )
    assessment = next(
        item
        for item in compare_graphs(graph, target).assessments
        if item.subject_id == "factory-create" and item.aspect == "relationship"
    )
    assert assessment.status == "UNKNOWN"


def test_native_generic_inherited_call_resolves_in_core_graph(tmp_path: Path) -> None:
    from archkeel.check.uml_compare import compare_graphs
    from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, Relationship

    _write_package(
        tmp_path,
        """class Base<T> {
  T echo(T value) => value;
}
class Derived<T> extends Base<T> {
  T forward(T value) => echo(value);
}
void external() { print('external'); }
""",
    )

    facts = _native_facts(tmp_path)
    call = next(
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if record.data.get("expression") == "echo(value)"
    )
    assert call.data.get("status") == "resolved"
    assert call.data.get("targets") == ("commerce.main.Base.echo",)
    external_call = next(
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if record.data.get("expression") == "print('external')"
    )
    assert external_call.data.get("status") == "unresolved"
    assert external_call.data.get("targets") == ()

    graph = _source_graph(facts)
    names = {entity.id: entity.qualified_name for entity in graph.entities}
    [resolved_call] = [
        edge
        for edge in graph.relationships
        if edge.kind == "calls" and edge.expression == "echo(value)"
    ]
    assert resolved_call.resolution == "resolved"
    assert names[resolved_call.source_id] == "commerce.main.Derived.forward"
    assert names[resolved_call.target_id] == "commerce.main.Base.echo"
    [unresolved_external] = [
        edge
        for edge in graph.relationships
        if edge.kind == "calls" and edge.expression == "print('external')"
    ]
    assert unresolved_external.resolution == "unresolved"
    assert unresolved_external.target_id is None

    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "base",
                "class",
                "commerce.main.Base",
                "dart",
                presence="planned",
                provenance=("test",),
            ),
            Entity(
                "derived",
                "class",
                "commerce.main.Derived",
                "dart",
                presence="planned",
                provenance=("test",),
            ),
            Entity(
                "echo",
                "method",
                "commerce.main.Base.echo",
                "dart",
                parent_id="base",
                presence="planned",
                provenance=("test",),
            ),
            Entity(
                "forward",
                "method",
                "commerce.main.Derived.forward",
                "dart",
                parent_id="derived",
                presence="planned",
                provenance=("test",),
            ),
        ),
        (Relationship("generic-call", "calls", "forward", "echo", provenance=("test",)),),
    )
    assessment = next(
        item
        for item in compare_graphs(graph, target).assessments
        if item.subject_id == "generic-call" and item.aspect == "relationship"
    )
    assert assessment.status == "PASS"


def test_native_import_combinators_intersect_and_preserve_empty_dependencies(
    tmp_path: Path,
) -> None:
    _write_package(
        tmp_path,
        "import 'b.dart' show A, B show B;\nvoid use(B value) {}\n",
    )
    (tmp_path / "lib/b.dart").write_text("class A {}\nclass B {}\n", encoding="utf-8")
    (tmp_path / "lib/empty.dart").write_text(
        "import 'b.dart' show A hide A;\nvoid empty() {}\n", encoding="utf-8"
    )
    (tmp_path / "lib/conditional.dart").write_text(
        "import 'b.dart' if (dart.library.io) 'b.dart';\nvoid conditional() {}\n",
        encoding="utf-8",
    )
    facts = _native_facts(tmp_path)
    imports = [
        dict(record.data.entries)
        for section in facts.sections
        if section.name == "imports"
        for record in section.records
    ]
    selected = [item for item in imports if item["source_module"] == "commerce.main"]
    assert len(selected) == 1
    assert selected[0]["symbol"] == "B"
    assert selected[0]["symbols_known"] is True
    empty_dependency = next(item for item in imports if item["source_module"] == "commerce.empty")
    assert empty_dependency["target_module"] == "commerce.b"
    assert empty_dependency["symbol"] is None
    assert empty_dependency["symbols_known"] is False
    conditional_records = [
        record
        for section in facts.sections
        if section.name == "imports"
        for record in section.records
        if record.data.get("source_module") == "commerce.conditional"
    ]
    alternatives = [dict(record.data.entries) for record in conditional_records]
    assert len(alternatives) == 1
    conditional_targets = [
        target for target in facts.imports if target.import_id == conditional_records[0].id
    ]
    assert len(conditional_targets) == 1
    assert conditional_targets[0].file == "lib/b.dart"


def test_native_sites_keep_part_declarations_in_the_library_scope(tmp_path: Path) -> None:
    _write_package(tmp_path, "part 'part.dart';\nvoid helper() {}\n")
    (tmp_path / "lib/part.dart").write_text(
        "part of 'main.dart';\nvoid caller() { helper(); }\n", encoding="utf-8"
    )
    facts = _native_facts(tmp_path)
    call = next(
        dict(record.data.entries)
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if record.data.get("expression") == "helper()"
    )
    assert call["source_scope"] == "commerce.main.caller"
    assert call["source_module"] == "commerce.main"
    assert call["targets"] == ("commerce.main.helper",)
    evidence = {item.id: item for item in facts.evidence}
    record = next(
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if record.data.get("expression") == "helper()"
    )
    assert evidence[record.evidence_ids[0]].file == "lib/part.dart"


def _native_facts(root: Path, roots: tuple[str, ...] = ("lib",)):
    request = CollectionRequest(
        SnapshotInput(str(root), "b" * 40, False),
        SourceScope(roots, "commerce"),
        DartSettings(),
    )
    return require_native_dart(collect_native_dart(request))


def _write_package(root: Path, source: str, *, pubspec: str = "name: commerce\n") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pubspec.yaml").write_text(pubspec, encoding="utf-8")
    path = root / "lib/main.dart"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _source_graph(facts):
    from archkeel.ir.model import (
        AnalyzerInfo,
        ContractInfo,
        Coverage,
        Observation,
        Section,
        SourceInfo,
    )
    from archkeel.ir.source_graph import observed_graph

    observation = Observation(
        schema_version="2.1.0",
        analyzer=AnalyzerInfo(facts.adapter.name, facts.adapter.version, facts.adapter.code_digest),
        source=SourceInfo(
            facts.source.git_head,
            facts.source.dirty,
            facts.source.source_digest,
            ("lib",),
        ),
        contract=ContractInfo("2.1.0", "0" * 64, "contract.json"),
        coverage=Coverage(
            "PASS" if facts.coverage.full_scope else "UNKNOWN",
            len(facts.files),
            facts.coverage.files_read,
            facts.coverage.files_parsed,
            None,
            None,
            None,
            None,
            100.0 if facts.coverage.full_scope else 0.0,
            None,
            (),
        ),
        sections=tuple(Section(section.name, section.records) for section in facts.sections),
        evidence=facts.evidence,
    )
    return observed_graph(observation)


def test_native_closure_result_binding_keeps_lexical_identity_and_exact_call_site(
    tmp_path: Path,
) -> None:
    _write_package(
        tmp_path,
        """class Inner {}
Inner makeInner() => Inner();
class Box { Box(Inner value); }
void register(void Function() callback) {}
void configure() {
  register(() {
    final value = Box(makeInner());
  });
}
""",
    )
    facts = _native_facts(tmp_path)
    sections = {section.name: section.records for section in facts.sections}
    configure = next(
        record
        for record in sections["symbols"]
        if record.data.get("qualified_name", "").endswith(".configure")
    )
    binding = next(
        record
        for record in sections["symbols"]
        if record.kind == "binding" and record.data.get("name") == "value"
    )
    outer = next(
        record
        for record in sections["calls"]
        if record.data.get("expression") == "Box(makeInner())"
    )
    inner = next(
        record for record in sections["calls"] if record.data.get("expression") == "makeInner()"
    )

    [site] = outer.data.get("result_bindings")
    assert site.get("id") == binding.id
    assert site.get("name") == "value"
    assert "_closure_" in binding.data.get("qualified_name")
    assert binding.data.get("lexical_parent_id") == configure.id
    assert outer.data.get("source_definition_id") == configure.id
    assert not inner.data.get("result_bindings")

    graph = _source_graph(facts)
    observed_binding = next(item for item in graph.entities if item.id == binding.id)
    assert observed_binding.qualified_name == binding.data.get("qualified_name")
    assert observed_binding.parent_id == configure.id
    assert observed_binding.initializer == "Box(makeInner())"
    assert any(
        edge.kind == "creates" and edge.source_id == configure.id for edge in graph.relationships
    )
    assert any(
        edge.kind == "instance_of" and edge.source_id == binding.id for edge in graph.relationships
    )


def test_native_async_body_binding_stays_in_its_callable_scope(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """class Value {}
Future<Value> load() async {
  final result = Value();
  return result;
}
""",
    )

    facts = _native_facts(tmp_path)
    binding = next(
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "binding" and record.data.get("name") == "result"
    )

    assert binding.data.get("qualified_name") == "commerce.main.load.result"


def test_native_declarations_project_enum_literals_interfaces_and_signatures(
    tmp_path: Path,
) -> None:
    _write_package(
        tmp_path,
        """enum State { pending, complete }
abstract interface class Repository { void save(String value); }
void configure(String id, void callback(String value), {required String title, String? subtitle}) {}
void optionalPositional([String? label]) {}
class Box { Box(this.value); final String value; }
""",
    )

    facts = _native_facts(tmp_path)
    graph = _source_graph(facts)
    entities = {entity.qualified_name: entity for entity in graph.entities}

    literals = {name: entities[f"commerce.main.State.{name}"] for name in ("pending", "complete")}
    evidence = {item.id: item for item in graph.evidence}
    assert all(entity.kind == "enum_literal" for entity in literals.values())
    assert all(entity.id.startswith("DARTATTR") for entity in literals.values())
    assert all(
        len(entity.evidence_ids) == 1
        and evidence[entity.evidence_ids[0]].file == "lib/main.dart"
        and evidence[entity.evidence_ids[0]].line == 1
        for entity in literals.values()
    )
    state_fact = next(
        record
        for section in facts.sections
        for record in section.records
        if section.name == "symbols" and record.data.get("name") == "State"
    )
    attribute_inventory = next(
        inventory
        for inventory in state_fact.data.get("member_inventories")
        if inventory.get("kind") == "attribute"
    )
    assert attribute_inventory.get("status") == "complete"
    assert set(attribute_inventory.get("definition_ids")) == {
        entity.id for entity in literals.values()
    }
    assert entities["commerce.main.Repository"].kind == "interface"
    save = entities["commerce.main.Repository.save"].signature
    assert save is not None
    assert save.parameters[0].annotation == "String"

    configured = entities["commerce.main.configure"].signature
    assert configured is not None
    required_positional, callback, title, subtitle = configured.parameters
    assert required_positional.kind == "positional"
    assert required_positional.default_known and required_positional.default is None
    assert callback.annotation is not None and "Function" in callback.annotation
    assert "String value" in callback.annotation
    assert title.kind == "keyword_only" and title.default_known and title.default is None
    assert subtitle.kind == "keyword_only" and subtitle.default_known and subtitle.default == "null"

    positional = entities["commerce.main.optionalPositional"].signature
    assert positional is not None
    assert positional.parameters[0].kind == "positional"
    assert positional.parameters[0].default_known
    assert positional.parameters[0].default == "null"
    constructor = entities["commerce.main.Box.Box"].signature
    assert constructor is not None
    assert constructor.parameters[0].annotation == "String"


def test_native_duplicate_attributes_do_not_publish_unique_graph_members(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """enum State { pending, pending, complete }
class Box {
  final String id;
  final String id;
  final String label;
}
""",
    )

    facts = _native_facts(tmp_path)
    assert facts.coverage.full_scope is False
    duplicate_gaps = [gap for gap in facts.coverage.gaps if gap.kind == "DuplicateDeclaration"]
    assert len(duplicate_gaps) == 2
    evidence = {item.id: item for item in facts.evidence}
    assert all(
        len(gap.evidence_ids) == 2
        and all(evidence[item].file == "lib/main.dart" for item in gap.evidence_ids)
        for gap in duplicate_gaps
    )

    graph = _source_graph(facts)
    entities = {entity.qualified_name: entity for entity in graph.entities}
    assert "commerce.main.State.pending" not in entities
    assert entities["commerce.main.State.complete"].kind == "enum_literal"
    assert "commerce.main.Box.id" not in entities
    assert entities["commerce.main.Box.label"].kind == "attribute"

    for name in ("State", "Box"):
        owner = next(
            record
            for section in facts.sections
            for record in section.records
            if section.name == "symbols" and record.data.get("name") == name
        )
        inventory = next(
            item for item in owner.data.get("member_inventories") if item.get("kind") == "attribute"
        )
        assert inventory.get("status") == "partial"
        attributes = owner.data.get("attribute_declarations")
        assert len(attributes) == 1
        assert attributes[0].get("name") == ("complete" if name == "State" else "label")


def test_native_malformed_unit_is_unknown_and_not_counted_parsed(tmp_path: Path) -> None:
    _write_package(tmp_path, "class Broken {\n")
    facts = _native_facts(tmp_path)
    assert facts.coverage.full_scope is False
    assert facts.coverage.files_read == 1
    assert facts.coverage.files_parsed == 0
    assert any(gap.kind in {"LibraryError", "SyntaxError"} for gap in facts.coverage.gaps)
    assert not any(
        record.data.get("name") == "Broken"
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    )


def test_native_part_with_multiple_library_owners_is_unknown(tmp_path: Path) -> None:
    _write_package(tmp_path, "library shared;\npart 'part.dart';\nclass A {}\n")
    (tmp_path / "lib/b.dart").write_text(
        "library shared;\npart 'part.dart';\nclass B {}\n", encoding="utf-8"
    )
    (tmp_path / "lib/part.dart").write_text("part of shared;\nclass Part {}\n", encoding="utf-8")

    facts = _native_facts(tmp_path)

    assert facts.coverage.full_scope is False
    assert any(gap.kind == "PartOwnershipConflict" for gap in facts.coverage.gaps)
    assert not any(
        record.data.get("name") == "Part"
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    )


def test_native_out_of_scope_part_is_unknown(tmp_path: Path) -> None:
    _write_package(tmp_path, "part '../outside.dart';\nclass Main {}\n")
    facts = _native_facts(tmp_path)
    assert facts.coverage.full_scope is False
    assert any(gap.kind == "DirectiveError" for gap in facts.coverage.gaps)
    assert not any(
        record.data.get("name") == "Main"
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    )


def test_native_unsupported_declaration_cannot_claim_full_coverage(tmp_path: Path) -> None:
    _write_package(tmp_path, "extension TextTools on String { String get reversed => this; }\n")
    facts = _native_facts(tmp_path)
    assert facts.coverage.full_scope is False
    assert any(gap.kind == "UnsupportedDeclaration" for gap in facts.coverage.gaps)


@pytest.mark.parametrize(
    ("sdk_constraint", "supported"),
    [
        (">=3.9.0 <3.10.0", True),
        ("^3.9", True),
        (">=3.99.0 <4.0.0", False),
        (">=3.11.0 <2.12.0", False),
    ],
)
def test_native_project_sdk_range_is_checked(
    tmp_path: Path,
    sdk_constraint: str,
    supported: bool,
) -> None:
    _write_package(tmp_path, "class Item { final int id = 1; }\n")
    (tmp_path / "pubspec.yaml").write_text(
        f"name: commerce\nenvironment:\n  sdk: '{sdk_constraint}'\n", encoding="utf-8"
    )

    facts = _native_facts(tmp_path)
    assert facts.runtime.name == "python"
    assert facts.coverage.full_scope is supported
    assert any(gap.kind == "SdkConstraintError" for gap in facts.coverage.gaps) == (not supported)
    if not supported:
        assert not any(
            record.data.get("member_inventories")
            for section in facts.sections
            if section.name == "symbols"
            for record in section.records
        )


@pytest.mark.parametrize(
    ("override", "complete"),
    [("3.99", False), ("3.9", True), ("2.19", True), ("3.x", False)],
)
def test_native_language_version_overrides_are_checked_by_analyzer(
    tmp_path: Path, override: str, complete: bool
) -> None:
    _write_package(tmp_path, f"// @dart={override}\nclass Item {{ final int id = 1; }}\n")
    (tmp_path / "pubspec.yaml").write_text(
        "name: commerce\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n", encoding="utf-8"
    )

    facts = _native_facts(tmp_path)

    assert facts.coverage.full_scope is complete
    if not complete:
        assert any(gap.kind == "LanguageVersionError" for gap in facts.coverage.gaps)


def test_native_library_part_language_version_mismatch_is_unknown(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        "// @dart=3.9\npart 'part.dart';\nclass Main {}\n",
    )
    (tmp_path / "lib/part.dart").write_text(
        "// @dart=2.19\npart of 'main.dart';\nclass Part {}\n", encoding="utf-8"
    )
    (tmp_path / "pubspec.yaml").write_text(
        "name: commerce\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n", encoding="utf-8"
    )

    facts = _native_facts(tmp_path)

    assert facts.coverage.full_scope is False
    assert any(gap.kind == "LanguageVersionError" for gap in facts.coverage.gaps)


def test_native_malformed_project_sdk_is_unknown(tmp_path: Path) -> None:
    _write_package(tmp_path, "class Item {}\n")
    (tmp_path / "pubspec.yaml").write_text(
        "name: commerce\nenvironment:\n  sdk: '>=3.9 broken'\n", encoding="utf-8"
    )

    facts = _native_facts(tmp_path)

    assert facts.coverage.full_scope is False
    assert any(gap.kind == "SdkConstraintError" for gap in facts.coverage.gaps)


def test_native_missing_selected_root_is_an_explicit_gap(tmp_path: Path) -> None:
    _write_package(tmp_path, "class Main {}\n")
    facts = _native_facts(tmp_path, ("lib/missing",))
    assert facts.coverage.full_scope is False
    assert any(gap.kind == "SelectedRootError" for gap in facts.coverage.gaps)


def test_unsafe_uri_units_never_enter_the_analyzer_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.dart"
    outside.write_text("class OutsideValue {}\n", encoding="utf-8")
    (root / "pubspec.yaml").write_text("name: commerce\n", encoding="utf-8")
    (root / "lib/parts").mkdir(parents=True)
    (root / "lib/direct.dart").write_text(
        "import '../../outside.dart';\nclass Direct {}\n", encoding="utf-8"
    )
    (root / "lib/bridge.dart").write_text(
        "import '../../outside.dart';\nclass Bridge {}\n", encoding="utf-8"
    )
    (root / "lib/transitive.dart").write_text(
        "import 'bridge.dart';\nclass Transitive {}\n", encoding="utf-8"
    )
    (root / "lib/malformed.dart").write_text(
        "import '../../outside.dart';\nclass Broken {\n", encoding="utf-8"
    )
    (root / "lib/parts/item.dart").write_text(
        "part of '../../../outside.dart';\nclass PartValue {}\n", encoding="utf-8"
    )

    facts = _native_facts(root)
    assert facts.coverage.full_scope is False
    assert any(
        gap.kind in {"DirectiveError", "SyntaxError", "IncompleteDependency"}
        for gap in facts.coverage.gaps
    )
    assert not any(
        record.data.get("name") == "OutsideValue"
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    )

    assert {item.path for item in facts.inputs}.isdisjoint({"outside.dart", "../outside.dart"})


def test_native_source_root_dot_uses_paths_relative_to_that_root(tmp_path: Path) -> None:
    _write_package(tmp_path, "class Main {}\n")
    facts = _native_facts(tmp_path, (".",))
    file = next(
        (file for file in facts.files if file.rel_path == "lib/main.dart"),
        None,
    )
    assert file is not None, (facts.coverage, facts.files)
    assert file.module == "commerce.lib.main"
    assert facts.coverage.full_scope is True


def test_native_dart_module_names_normalize_and_collisions_are_unknown(tmp_path: Path) -> None:
    _write_package(tmp_path, "class Main {}\n")
    nested = tmp_path / "lib/folder-name/file.v1.dart"
    nested.parent.mkdir(parents=True)
    nested.write_text("class Nested {}\n", encoding="utf-8")
    facts = _native_facts(tmp_path)
    assert any(file.module == "commerce.folder_name.file_v1" for file in facts.files)
    assert facts.coverage.full_scope is True

    (tmp_path / "lib/file-name.dart").write_text("class One {}\n", encoding="utf-8")
    (tmp_path / "lib/file.name.dart").write_text("class Two {}\n", encoding="utf-8")
    collision = _native_facts(tmp_path)
    assert collision.coverage.full_scope is False
    assert any(gap.kind == "DartModuleCollision" for gap in collision.coverage.gaps)


def test_native_symlinked_dart_source_is_an_explicit_gap(tmp_path: Path) -> None:

    outside = tmp_path / "outside.dart"
    outside.write_text("class OutsideValue {}\n", encoding="utf-8")
    root = tmp_path / "repo"
    _write_package(root, "class Main {}\n")
    (root / "lib/linked.dart").symlink_to(outside)
    facts = _native_facts(root)
    assert facts.coverage.full_scope is False
    assert any(gap.kind == "DartSourceLink" for gap in facts.coverage.gaps)
    assert not any(
        record.data.get("name") == "OutsideValue"
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    )


def test_native_pubspec_symlink_is_rejected_before_read(tmp_path: Path) -> None:
    from archkeel.ir.protocol import CollectionError

    outside = tmp_path / "outside-pubspec.yaml"
    outside.write_text("name: commerce\n", encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "lib").mkdir()
    (root / "lib/main.dart").write_text("class Main {}\n", encoding="utf-8")
    (root / "pubspec.yaml").symlink_to(outside)
    result = collect_native_dart(
        CollectionRequest(
            SnapshotInput(str(root), "c" * 40, False),
            SourceScope(("lib",), "commerce"),
            DartSettings(),
        )
    )
    assert isinstance(result, CollectionError)
    assert "regular pubspec.yaml" in result.message


def test_native_callback_locals_use_their_function_expression_scope(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """void invoke(void Function() callback) => callback();
void work() {
  invoke(() { final value = 'first'; print(value); });
  invoke(() { final value = 'second'; print(value); });
}
""",
    )

    facts = _native_facts(tmp_path)
    symbols = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "binding" and record.data.get("name") == "value"
    ]

    assert len(symbols) == 2
    assert len({record.data.get("qualified_name") for record in symbols}) == 2
    assert len({record.data.get("lexical_parent_id") for record in symbols}) == 1
    target_ids = {
        record.data.get("targets")[0]
        for section in facts.sections
        if section.name == "references"
        for record in section.records
        if record.data.get("expression") == "value"
    }
    assert target_ids == {record.data.get("qualified_name") for record in symbols}


def test_native_same_initializer_bindings_stay_in_their_lexical_functions(
    tmp_path: Path,
) -> None:
    _write_package(
        tmp_path,
        """class Value {}
Value first() { final result = Value(); return result; }
Value second() { final result = Value(); return result; }
""",
    )

    facts = _native_facts(tmp_path)
    graph = _source_graph(facts)
    bindings = [
        item
        for item in graph.entities
        if item.kind == "binding" and item.qualified_name.endswith(".result")
    ]

    assert {item.qualified_name for item in bindings} == {
        "commerce.main.first.result",
        "commerce.main.second.result",
    }
    assert len({item.id for item in bindings}) == 2


def test_native_multiline_call_expression_uses_canonical_source_text(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """class Backend {}
class Store {}
class ShopApp { ShopApp(Backend backend, Store store); }
void main(Backend backend, Store store) {
  final app = ShopApp(
    backend,
    store,
  );
}
""",
    )

    facts = _native_facts(tmp_path)
    call = next(
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if record.data.get("expression", "").startswith("ShopApp")
    )

    assert call.data.get("expression") == "ShopApp(backend, store)"
    assert call.title == "ShopApp(backend, store)"


def test_native_getter_and_setter_references_bind_to_their_own_declarations(
    tmp_path: Path,
) -> None:
    _write_package(
        tmp_path,
        """class Box {
  String get value => 'read';
  set value(String next) {}
}
String get status => 'ready';
set status(String value) {}
void use(Box box) {
  final read = box.value;
  box.value = 'write';
  final current = status;
  status = 'changed';
  box.value += 'more';
}
""",
    )

    facts = _native_facts(tmp_path)
    accessors = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "method" and record.data.get("name") == "value"
    ]
    assert len(accessors) == 2
    assert {record.data.get("accessor_kind") for record in accessors} == {"getter", "setter"}
    accessors_by_kind = {record.data.get("accessor_kind"): record for record in accessors}
    assert len({record.data.get("qualified_name") for record in accessors}) == 2
    evidence = {item.id: item for item in facts.evidence}
    by_line = {
        evidence[record.evidence_ids[0]].line: record.data.get("targets")
        for section in facts.sections
        if section.name == "references"
        for record in section.records
        if record.data.get("expression") == "box.value"
    }
    all_references_by_line = {
        evidence[record.evidence_ids[0]].line: record.data.get("targets")
        for section in facts.sections
        if section.name == "references"
        for record in section.records
    }
    assert by_line[8] == (accessors_by_kind["getter"].data.get("qualified_name"),)
    assert by_line[9] == (accessors_by_kind["setter"].data.get("qualified_name"),)
    assert by_line[8] != by_line[9]

    top_level = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "function" and record.data.get("name") == "status"
    ]
    assert len(top_level) == 2
    assert {record.data.get("accessor_kind") for record in top_level} == {"getter", "setter"}
    top_level_by_kind = {record.data.get("accessor_kind"): record for record in top_level}
    assert len({record.data.get("qualified_name") for record in top_level}) == 2
    assert all_references_by_line[10] == (top_level_by_kind["getter"].data.get("qualified_name"),)
    assert all_references_by_line[11] == (top_level_by_kind["setter"].data.get("qualified_name"),)
    assert all_references_by_line[10] != all_references_by_line[11]
    compound = {
        record.data.get("use"): record.data.get("targets")
        for section in facts.sections
        if section.name == "references"
        for record in section.records
        if evidence[record.evidence_ids[0]].line == 12
        and record.data.get("expression") == "box.value"
    }
    assert compound == {
        "read": (accessors_by_kind["getter"].data.get("qualified_name"),),
        "write": (accessors_by_kind["setter"].data.get("qualified_name"),),
    }


def test_native_super_formal_inherits_resolved_type_and_default(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """class Parent {
  Parent({String key = 'x'});
}
class Child extends Parent {
  Child({super.key});
}
class DynamicParent {
  DynamicParent({dynamic value});
}
class DynamicChild extends DynamicParent {
  DynamicChild({super.value});
}
class GenericParent<T> {
  GenericParent({required T value});
}
class GenericChild extends GenericParent<String> {
  GenericChild({required super.value});
}
""",
    )

    facts = _native_facts(tmp_path)
    methods = {
        record.data.get("qualified_name"): record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "method"
    }
    child = methods["commerce.main.Child.Child"].data
    assert child.get("signature_complete") is True
    key = child.get("parameters")[0]
    assert key.get("name") == "key"
    assert key.get("annotation") == "String"
    assert key.get("kind") == "keyword_only"
    assert key.get("default") == "'x'"
    assert key.get("default_known") is True

    dynamic_child = methods["commerce.main.DynamicChild.DynamicChild"].data
    assert dynamic_child.get("signature_complete") is True
    value = dynamic_child.get("parameters")[0]
    assert value.get("annotation") == "dynamic"
    assert value.get("default_known") is True

    generic_child = methods["commerce.main.GenericChild.GenericChild"].data
    generic_value = generic_child.get("parameters")[0]
    assert generic_value.get("annotation") == "String"
    assert generic_value.get("default") is None
    assert generic_value.get("default_known") is True


def test_native_unresolved_super_formal_stays_present_but_incomplete(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """class Child extends MissingParent {
  Child({super.key});
}
""",
    )

    facts = _native_facts(tmp_path)
    child = next(
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "method"
        and record.data.get("qualified_name") == "commerce.main.Child.Child"
    )
    assert child.data.get("signature_complete") is False
    key = child.data.get("parameters")[0]
    assert key.get("name") == "key"
    assert key.get("annotation") is None
    assert key.get("kind") == "keyword_only"
    assert key.get("default") is None
    assert key.get("default_known") is False
    assert [gap.kind for gap in facts.coverage.gaps] == ["source_resolution_gap"]
    gap = facts.coverage.gaps[0]
    evidence = {item.id: item for item in facts.evidence}
    assert gap.evidence_ids
    assert all(evidence[item].file == "lib/main.dart" for item in gap.evidence_ids)
    assert all(evidence[item].line == 2 for item in gap.evidence_ids)

    from archkeel.check.uml_compare import compare_graphs
    from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, Parameter, Signature

    observed = _source_graph(facts)
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "target-child",
                "class",
                "commerce.main.Child",
                "dart",
                provenance=("independent-target-spec",),
            ),
            Entity(
                "target-constructor",
                "method",
                "commerce.main.Child.Child",
                "dart",
                parent_id="target-child",
                signature=Signature(
                    (Parameter("key", "String", "keyword_only", None),),
                    "Child",
                ),
                provenance=("independent-target-spec",),
            ),
        ),
    )
    comparison = compare_graphs(observed, target)
    assert comparison.status == "UNKNOWN"
    signature = next(
        item
        for item in comparison.assessments
        if item.subject_id == "target-constructor" and item.aspect == "signature"
    )
    assert signature.status == "UNKNOWN"


def test_native_unmatched_resolved_super_parameter_stays_generic_gap(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """class Parent {
  Parent({required String other});
}
class Child extends Parent {
  Child({super.key});
}
""",
    )

    facts = _native_facts(tmp_path)
    child = next(
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "method"
        and record.data.get("qualified_name") == "commerce.main.Child.Child"
    )
    assert child.data.get("signature_complete") is False
    key = child.data.get("parameters")[0]
    assert key.get("name") == "key"
    assert key.get("annotation") is None
    assert {gap.kind for gap in facts.coverage.gaps} == {"UnsupportedParameter"}


def test_native_invalid_inherited_super_parameter_type_stays_generic_gap(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """class Parent {
  Parent({required MissingType key});
}
class Child extends Parent {
  Child({super.key});
}
""",
    )

    facts = _native_facts(tmp_path)
    child = next(
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "method"
        and record.data.get("qualified_name") == "commerce.main.Child.Child"
    )
    assert child.data.get("signature_complete") is False
    assert {gap.kind for gap in facts.coverage.gaps} == {"UnsupportedParameter"}


def test_native_redirecting_factory_defaults_follow_typed_constructor_chain(
    tmp_path: Path,
) -> None:
    _write_package(
        tmp_path,
        """abstract interface class Direct {
  List<String> get value;
  factory Direct({List<String> value}) = DirectImpl;
}
class DirectImpl implements Direct {
  DirectImpl({this.value = const []});
  @override final List<String> value;
}
abstract interface class Multi {
  List<String> get left;
  List<String> get right;
  factory Multi({List<String> left, List<String> right}) = MultiHop;
}
abstract class MultiHop implements Multi {
  List<String> get left;
  List<String> get right;
  factory MultiHop({List<String> right, List<String> left}) = MultiImpl;
}
class MultiImpl implements MultiHop {
  MultiImpl({this.right = const [], this.left = const []});
  @override final List<String> left;
  @override final List<String> right;
}
abstract interface class Positional {
  String get value;
  factory Positional([String requested]) = PositionalImpl;
}
class PositionalImpl implements Positional {
  PositionalImpl([this.value = 'position']);
  @override final String value;
}
abstract interface class AbsentDefault {
  String? get value;
  factory AbsentDefault({String? value}) = AbsentDefaultImpl;
}
class AbsentDefaultImpl implements AbsentDefault {
  AbsentDefaultImpl({this.value});
  @override final String? value;
}
""",
    )

    facts = _native_facts(tmp_path)
    constructors = {
        record.data.get("qualified_name"): record.data
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "method" and record.data.get("method_kind") == "factory"
    }

    def defaults(name):
        return [parameter.get("default") for parameter in constructors[name].get("parameters")]

    assert defaults("commerce.main.Direct.Direct") == ["const []"]
    assert defaults("commerce.main.Multi.Multi") == ["const []", "const []"]
    assert defaults("commerce.main.Positional.Positional") == ["'position'"]
    assert defaults("commerce.main.AbsentDefault.AbsentDefault") == ["null"]
    assert all(
        all(parameter.get("default_known") for parameter in data.get("parameters", ()))
        for data in constructors.values()
    )


@pytest.mark.parametrize(
    ("source", "factory_name"),
    [
        pytest.param(
            """abstract interface class MissingTarget {
  factory MissingTarget({String value}) = MissingImpl;
}
""",
            "MissingTarget",
            id="unresolved",
        ),
        pytest.param(
            """abstract interface class Mismatch {
  factory Mismatch({String value}) = MismatchImpl;
}
class MismatchImpl implements Mismatch {
  MismatchImpl({String other = 'wrong'});
}
""",
            "Mismatch",
            id="mismatched-formal",
        ),
        pytest.param(
            """class RedirectCycle {
  factory RedirectCycle({String value}) = RedirectCycle.named;
  factory RedirectCycle.named({String value}) = RedirectCycle;
}
""",
            "RedirectCycle",
            id="cycle",
        ),
        pytest.param(
            """abstract interface class FactoryTerminal {
  factory FactoryTerminal({String value}) = FactoryBody;
}
class FactoryBody implements FactoryTerminal {
  factory FactoryBody({String value = 'body'}) { return Impl(); }
}
class Impl implements FactoryBody {}
""",
            "FactoryTerminal",
            id="unproven-factory-terminal",
        ),
    ],
)
def test_native_unresolved_redirecting_factory_default_stays_unknown_and_blocked(
    tmp_path: Path, source: str, factory_name: str
) -> None:
    from archkeel.check.uml_compare import compare_graphs
    from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, Parameter, Signature

    _write_package(tmp_path, source)
    facts = _native_facts(tmp_path)
    factory = next(
        record.data
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "method"
        and record.data.get("method_kind") == "factory"
        and record.data.get("qualified_name") == f"commerce.main.{factory_name}.{factory_name}"
    )
    parameter = factory.get("parameters")[0]
    assert parameter.get("default") is None
    assert parameter.get("default_known") is False
    assert factory.get("signature_complete") is False
    assert any(gap.kind == "UnsupportedParameter" for gap in facts.coverage.gaps)
    assert not any(gap.kind == "source_resolution_gap" for gap in facts.coverage.gaps)
    if factory_name == "FactoryTerminal":
        body_factory = next(
            record.data
            for section in facts.sections
            if section.name == "symbols"
            for record in section.records
            if record.data.get("qualified_name") == "commerce.main.FactoryBody.FactoryBody"
        )
        body_parameter = body_factory.get("parameters")[0]
        assert body_parameter.get("default") == "'body'"
        assert body_parameter.get("default_known") is True

    observed = _source_graph(facts)
    owner = factory.get("parent")
    target = ArchitectureGraph(
        "declared",
        (
            Entity("target-owner", "class", owner, "dart", provenance=("test",)),
            Entity(
                "target-factory",
                "method",
                factory.get("qualified_name"),
                "dart",
                parent_id="target-owner",
                signature=Signature(
                    (Parameter(parameter.get("name"), "String", "keyword_only", "fallback"),),
                    owner.rsplit(".", 1)[-1],
                ),
                provenance=("test",),
            ),
        ),
    )
    comparison = compare_graphs(observed, target)
    assessment = next(
        item
        for item in comparison.assessments
        if item.subject_id == "target-factory" and item.aspect == "signature"
    )
    assert assessment.status == "UNKNOWN"


def test_native_constructor_returns_setters_and_private_names_keep_dart_semantics(
    tmp_path: Path,
) -> None:
    _write_package(
        tmp_path,
        """class Box<T> {
  Box();
  Box.named();
  Box._();
}
class _Hidden {
  _Hidden.named();
  _Hidden._();
}
class Maker<T> {
  factory Maker() = MakerImpl<T>;
}
class MakerImpl<T> implements Maker<T> {
  MakerImpl();
}
class Values {
  int get value => 1;
  set value(int next) {}
  int set invalid(int next) {}
}
int get status => 1;
set status(int next) {}
String describe() => 'value';
""",
    )

    facts = _native_facts(tmp_path)
    symbols = {
        record.data.get("qualified_name"): record.data
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "method" or record.kind == "function"
    }
    assert symbols["commerce.main.Box.Box"].get("returns") == "Box<T>"
    assert symbols["commerce.main.Box.Box.named"].get("returns") == "Box<T>"
    assert symbols["commerce.main.Maker.Maker"].get("returns") == "Maker<T>"
    assert symbols["commerce.main.MakerImpl.MakerImpl"].get("returns") == "MakerImpl<T>"
    assert symbols["commerce.main.Values.value::getter"].get("returns") == "int"
    assert symbols["commerce.main.Values.value::setter"].get("returns") == "void"
    assert symbols["commerce.main.Values.invalid::setter"].get("returns") == "int"
    assert symbols["commerce.main.status::getter"].get("returns") == "int"
    assert symbols["commerce.main.status::setter"].get("returns") == "void"
    assert symbols["commerce.main.describe"].get("returns") == "String"
    assert symbols["commerce.main.Box.Box._"].get("qualified_name") == "commerce.main.Box.Box._"
    assert symbols["commerce.main.Box.Box._"].get("visibility_detail").get("kind") == "private"
    assert symbols["commerce.main.Box.Box._"].get("visibility_detail").get("spelling") == "_"
    assert symbols["commerce.main.Box.Box.named"].get("visibility_detail").get("kind") == "public"
    assert (
        symbols["commerce.main._Hidden._Hidden.named"].get("visibility_detail").get("kind")
        == "public"
    )
    assert (
        symbols["commerce.main._Hidden._Hidden.named"].get("visibility_detail").get("spelling")
        == "named"
    )
    assert symbols["commerce.main.Box.Box"].get("visibility_detail").get("kind") == "public"


def test_native_duplicate_functions_remain_an_explicit_gap(tmp_path: Path) -> None:
    _write_package(
        tmp_path,
        """String value() => 'first';
String value() => 'second';
""",
    )

    facts = _native_facts(tmp_path)

    assert facts.coverage.full_scope is False
    assert any(gap.kind == "DuplicateDeclaration" for gap in facts.coverage.gaps)
