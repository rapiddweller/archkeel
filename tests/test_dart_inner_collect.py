# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native Dart collector publishes declarations from complete source units."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from archkeel.ir.facts_codec import decode_response, encode_request
from archkeel.ir.protocol import CollectionRequest, DartSettings, SnapshotInput, SourceScope

_REPO = Path(__file__).parents[1]
_NATIVE = _REPO / "src/archkeel/analyzer/dart/native"


def test_native_process_collects_dart_declarations_and_member_coverage(tmp_path: Path) -> None:
    dart = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if dart is None:
        pytest.skip("Dart SDK is not installed; native collector checks require Dart")
    package_config = _NATIVE / ".dart_tool/package_config.json"
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
    result = subprocess.run(
        [
            dart,
            f"--packages={package_config}",
            str(_NATIVE / "bin/collect.dart"),
        ],
        input=encode_request(request),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    facts = decode_response(result.stdout).facts
    assert facts.profile == "archkeel-dart-analyzer"
    assert facts.runtime.name == "dart"
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


def test_native_process_marks_duplicate_declarations_incomplete(tmp_path: Path) -> None:
    dart = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if dart is None:
        pytest.skip("Dart SDK is not installed; native collector checks require Dart")
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
    result = subprocess.run(
        [
            dart,
            f"--packages={_NATIVE / '.dart_tool/package_config.json'}",
            str(_NATIVE / "bin/collect.dart"),
        ],
        input=encode_request(request),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    facts = decode_response(result.stdout).facts
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
    dart = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if dart is None:
        pytest.skip("Dart SDK is not installed; native collector checks require Dart")
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
    result = subprocess.run(
        [
            dart,
            f"--packages={_NATIVE / '.dart_tool/package_config.json'}",
            str(_NATIVE / "bin/collect.dart"),
        ],
        input=encode_request(request),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    facts = decode_response(result.stdout).facts
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
    dart = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if dart is None:
        pytest.skip("Dart SDK is not installed; native collector checks require Dart")
    result = subprocess.run(
        [
            dart,
            f"--packages={_NATIVE / '.dart_tool/package_config.json'}",
            str(_NATIVE / "bin/collect.dart"),
        ],
        input=encode_request(request),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    facts = decode_response(result.stdout).facts
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
    for contract in sorted((fixture / "contracts").glob("*.json")):
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
            for member in [*attributes, *actual]
            if member.startswith(name + ".")
        } | enum_literals.get(name, set())
        expected_members = {
            item["qualified_name"].rsplit(".", 1)[-1]
            for item in target_entities
            if item.get("presence") == "planned" and item.get("parent_id") == classifier["id"]
        }
        assert observed_members == expected_members, name


def _native_facts(root: Path, roots: tuple[str, ...] = ("lib",)):
    dart = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if dart is None:
        pytest.skip("Dart SDK is not installed; native collector checks require Dart")
    request = CollectionRequest(
        SnapshotInput(str(root), "b" * 40, False),
        SourceScope(roots, "commerce"),
        DartSettings(),
    )
    result = subprocess.run(
        [
            dart,
            f"--packages={_NATIVE / '.dart_tool/package_config.json'}",
            str(_NATIVE / "bin/collect.dart"),
        ],
        input=encode_request(request),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return decode_response(result.stdout).facts


def _write_package(root: Path, source: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pubspec.yaml").write_text("name: commerce\n", encoding="utf-8")
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


def test_native_missing_selected_root_is_an_explicit_gap(tmp_path: Path) -> None:
    _write_package(tmp_path, "class Main {}\n")
    facts = _native_facts(tmp_path, ("lib/missing",))
    assert facts.coverage.full_scope is False
    assert any(gap.kind == "SelectedRootError" for gap in facts.coverage.gaps)


def test_unsafe_uri_units_never_enter_the_analyzer_snapshot(tmp_path: Path) -> None:
    import os

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

    dart = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if dart is None:
        pytest.skip("Dart SDK is not installed; snapshot-boundary checks require Dart")
    boundary = subprocess.run(
        [
            dart,
            f"--packages={_NATIVE / '.dart_tool/package_config.json'}",
            str(_NATIVE / "test/snapshot_boundary.dart"),
            str(root),
        ],
        capture_output=True,
        check=False,
    )
    assert boundary.returncode == 0, boundary.stderr.decode(errors="replace")


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
    import os

    outside = tmp_path / "outside-pubspec.yaml"
    outside.write_text("name: commerce\n", encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "lib").mkdir()
    (root / "lib/main.dart").write_text("class Main {}\n", encoding="utf-8")
    (root / "pubspec.yaml").symlink_to(outside)
    dart = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if dart is None:
        pytest.skip("Dart SDK is not installed; native collector checks require Dart")
    result = subprocess.run(
        [
            dart,
            f"--packages={_NATIVE / '.dart_tool/package_config.json'}",
            str(_NATIVE / "bin/collect.dart"),
        ],
        input=encode_request(
            CollectionRequest(
                SnapshotInput(str(root), "c" * 40, False),
                SourceScope(("lib",), "commerce"),
                DartSettings(),
            )
        ),
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert b"regular pubspec.yaml" in result.stderr
