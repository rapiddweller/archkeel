# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dart URI and source-name resolution stays inside the selected snapshot."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from archkeel.analyzer.dart.parse import parse
from archkeel.analyzer.dart.resolve import Resolver
from archkeel.analyzer.dart.snapshot import read_snapshot
from archkeel.ir.protocol import CollectionRequest, DartSettings, SnapshotInput, SourceScope


def _snapshot(root: Path, files: dict[str, str], *, package: str = "package_name"):
    (root / "pubspec.yaml").write_text(f"name: {package}\n", encoding="utf-8")
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    request = CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(("lib",), "configured_namespace"),
        DartSettings(),
    )
    snapshot = read_snapshot(request)
    syntax = {source.rel_path: parse(source.content) for source in snapshot.sources}
    return snapshot, syntax


def test_package_identity_is_distinct_from_output_namespace_and_show_hide_resolves_names(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/dependency.dart": "class Visible {}\nclass Hidden {}\n",
            "lib/main.dart": "import 'package:package_name/dependency.dart' as dep "
            "show Visible hide Hidden;\n"
            "void run() { dep.Visible(); dep.Hidden(); }\n",
        },
    )
    resolver = Resolver(snapshot, syntax)

    assert snapshot.sources[0].module.startswith("configured_namespace.")
    assert resolver.resolve_uri("lib/main.dart", "package:package_name/dependency.dart") is not None
    # The pubspec declares another package, so the namespace name must not become external.
    assert (
        resolver.resolve_uri("lib/main.dart", "package:configured_namespace/dependency.dart")
        is None
    )
    calls = [site for site in resolver.resolved_sites("lib/main.dart") if site.site.kind == "call"]
    visible = next(item for item in calls if item.site.name == "Visible")
    hidden = next(item for item in calls if item.site.name == "Hidden")
    assert visible.status == "resolved"
    assert visible.bindings[0].module == "configured_namespace.dependency"
    assert visible.bindings[0].via_prefix == "dep"
    assert hidden.status == "unresolved"


def test_conditional_uris_keep_every_selected_branch(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "import 'stub.dart' if (dart.library.io) 'io.dart';\n",
            "lib/stub.dart": "class Stub {}\n",
            "lib/io.dart": "class Io {}\n",
        },
    )
    directive = next(item for item in syntax["lib/main.dart"].directives if item.kind == "import")

    targets = Resolver(snapshot, syntax).resolve_directive("lib/main.dart", directive)

    assert {item.rel_path for item in targets} == {"lib/stub.dart", "lib/io.dart"}


def test_parts_inherit_unique_library_module_and_orphans_stay_unresolved(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "part 'parts/model.dart';\n",
            "lib/parts/model.dart": "part of '../main.dart';\nclass PartModel {}\n",
            "lib/orphan.dart": "part of 'missing.dart';\n",
        },
    )
    resolver = Resolver(snapshot, syntax)

    assert resolver.module_for("lib/main.dart") == "configured_namespace.main"
    assert resolver.module_for("lib/parts/model.dart") == "configured_namespace.main"
    assert resolver.module_for("lib/orphan.dart") is None
    assert any(
        issue.kind == "PartError" and issue.path == "lib/orphan.dart" for issue in resolver.problems
    )


def test_invalid_part_uri_suppresses_the_library_and_owner_conflicts_are_single_issues(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/outside.dart": "class Outside {}\n",
            "lib/a.dart": "part '../outside.dart';\nclass A {}\n",
            "lib/b.dart": "library shared_owner;\npart 'shared.dart';\n",
            "lib/c.dart": "library shared_owner;\npart 'shared.dart';\n",
            "lib/shared.dart": "part of shared_owner;\nclass Shared {}\n",
        },
    )
    resolver = Resolver(snapshot, syntax)

    assert resolver.module_for("lib/a.dart") is None
    assert resolver.module_for("lib/b.dart") is None
    assert resolver.module_for("lib/c.dart") is None
    assert [item.kind for item in resolver.problems].count("PartOwnershipConflict") == 1
    assert any(item.kind == "PartError" and item.path == "lib/a.dart" for item in resolver.problems)


def test_relative_uri_escape_is_rejected_without_reading_target(
    tmp_path: Path, monkeypatch
) -> None:
    snapshot, syntax = _snapshot(tmp_path, {"lib/main.dart": "class Main {}\n"})
    outside = tmp_path.parent / f"{tmp_path.name}-outside.dart"
    outside.write_text("class Outside {}\n", encoding="utf-8")
    original = Path.read_bytes

    def guarded_read(path: Path) -> bytes:
        if path == outside:
            raise AssertionError("outside source was read")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    resolver = Resolver(snapshot, syntax)

    assert resolver.resolve_uri("lib/main.dart", "../../outside.dart") is None
    assert resolver.problems[-1].kind == "ImportError"


@pytest.mark.parametrize(
    "uri",
    (
        "../../outside.dart",
        "%2e%2e/%2e%2e/outside.dart",
        "/outside.dart",
        "file:///outside.dart",
        "package:package_name/%2e%2e/outside.dart",
    ),
)
def test_uri_escapes_and_unsupported_schemes_never_resolve(tmp_path: Path, uri: str) -> None:
    snapshot, syntax = _snapshot(tmp_path, {"lib/main.dart": "class Main {}\n"})
    resolver = Resolver(snapshot, syntax)

    assert resolver.resolve_uri("lib/main.dart", uri) is None
    assert resolver.problems[-1].kind == "ImportError"


def test_constructor_binding_uses_actual_declarations_and_never_guesses_by_capitalization(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "class HasCtor { HasCtor(); HasCtor.named(); }\n"
            "class NoCtor {}\nclass NamedOnly { NamedOnly.named(); }\n"
            "void run() { new HasCtor(); new HasCtor.named(); new NoCtor(); "
            "new NamedOnly(); HasCtor(); NoCtor(); }\n",
        },
    )
    resolver = Resolver(snapshot, syntax)
    sites = resolver.resolved_sites("lib/main.dart")
    creations = [item for item in sites if item.site.kind == "creation"]
    plain_call = next(
        item for item in sites if item.site.kind == "call" and item.site.name == "HasCtor"
    )
    implicit_call = next(
        item for item in sites if item.site.kind == "call" and item.site.name == "NoCtor"
    )

    assert [item.status for item in creations] == ["resolved", "resolved", "resolved", "unresolved"]
    assert creations[0].bindings[0].kind == "constructor"
    assert creations[1].bindings[0].kind == "constructor"
    assert plain_call.status == "resolved"
    assert implicit_call.status == "resolved"
    assert implicit_call.bindings[0].kind == "implicit_constructor"


@pytest.mark.parametrize("other", ["typedef Box = int;", "void Box() {}", "class Box {}"])
def test_prefixed_constructor_reference_keeps_mixed_declarations_ambiguous(
    tmp_path: Path, other: str
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Box { Box.named(); }\n",
            "lib/other.dart": other + "\n",
            "lib/main.dart": "import 'model.dart' as m; import 'other.dart' as m;\n"
            "void run() { final constructor = m.Box.named; }\n",
        },
    )
    resolver = Resolver(snapshot, syntax)
    reference = next(
        item
        for item in resolver.resolved_sites("lib/main.dart")
        if item.site.kind == "reference" and item.site.expression == "m.Box.named"
    )
    assert reference.status != "resolved"
    assert reference.bindings == ()


def test_prefixed_constructor_reference_deduplicates_the_same_exported_class(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Box { Box.named(); }\n",
            "lib/facade.dart": "export 'model.dart' show Box;\n",
            "lib/main.dart": "import 'model.dart' as m; import 'facade.dart' as m;\n"
            "void run() { final constructor = m.Box.named; }\n",
        },
    )
    reference = next(
        item
        for item in Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
        if item.site.kind == "reference" and item.site.expression == "m.Box.named"
    )
    assert reference.status == "resolved"
    assert len(reference.bindings) == 1
    assert reference.bindings[0].name == "Box.named"
    assert reference.bindings[0].rel_path == "lib/model.dart"


@pytest.mark.parametrize(
    "directive,known",
    [
        ("import 'package:external/widgets.dart' as m;", False),
        ("import 'package:external/widgets.dart' as m show Box;", False),
        ("import 'package:external/widgets.dart' as m show Other;", True),
        ("import 'package:external/widgets.dart' as m hide Box;", True),
        ("import 'package:external/widgets.dart' as m hide named;", False),
        ("import 'package:external/widgets.dart' as m show named;", True),
    ],
)
def test_prefixed_constructor_reference_requires_visible_import_namespace_closure(
    tmp_path: Path, directive: str, known: bool
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Box { Box.named(); }\n",
            "lib/main.dart": f"import 'model.dart' as m; {directive}\n"
            "void run() { final constructor = m.Box.named; }\n",
        },
    )
    reference = next(
        item
        for item in Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
        if item.site.kind == "reference" and item.site.expression == "m.Box.named"
    )
    assert (reference.status == "resolved") is known


@pytest.mark.parametrize(
    "external_export,known",
    [
        ("export 'package:external/widgets.dart';", False),
        ("export 'package:external/widgets.dart' show Box;", False),
        ("export 'package:external/widgets.dart' show Other;", True),
        ("export 'package:external/widgets.dart' hide Box;", True),
        ("export 'package:external/widgets.dart' hide named;", False),
        ("export 'package:external/widgets.dart' show named;", True),
    ],
)
def test_prefixed_constructor_reference_requires_visible_export_namespace_closure(
    tmp_path: Path, external_export: str, known: bool
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Box { Box.named(); }\n",
            "lib/facade.dart": f"export 'model.dart'; {external_export}\n",
            "lib/main.dart": "import 'facade.dart' as m;\n"
            "void run() { final constructor = m.Box.named; }\n",
        },
    )
    reference = next(
        item
        for item in Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
        if item.site.kind == "reference" and item.site.expression == "m.Box.named"
    )
    assert (reference.status == "resolved") is known


@pytest.mark.parametrize(
    "extra,known",
    [
        ({}, False),
        ({"lib/boundary.dart": "class Broken {"}, False),
        ({"lib/boundary.dart": "export 'missing.dart';"}, False),
        (
            {
                "lib/boundary.dart": "export 'other.dart';",
                "lib/other.dart": "export 'package:external/widgets.dart';",
            },
            False,
        ),
        (
            {"lib/boundary.dart": "export 'model.dart' if (dart.library.io) 'missing.dart';"},
            False,
        ),
        (
            {
                "lib/boundary.dart": "part 'piece.dart';",
                "lib/piece.dart": "part of 'boundary.dart'; class Broken {",
            },
            False,
        ),
        (
            {
                "lib/boundary.dart": "export 'model.dart'; export 'other.dart';",
                "lib/other.dart": "export 'boundary.dart';",
            },
            True,
        ),
        (
            {
                "lib/boundary.dart": "export 'other.dart' show Other;",
                "lib/other.dart": "export 'package:external/widgets.dart';",
            },
            True,
        ),
        (
            {
                "lib/boundary.dart": "export 'other.dart' hide Box;",
                "lib/other.dart": "export 'package:external/widgets.dart';",
            },
            True,
        ),
        ({"lib/boundary.dart": "import 'package:external/widgets.dart';"}, True),
    ],
)
def test_prefixed_constructor_reference_closes_every_visible_source_path(
    tmp_path: Path, extra: dict[str, str], known: bool
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Box { Box.named(); }\n",
            "lib/main.dart": "import 'model.dart' as m; import 'boundary.dart' as m;\n"
            "void run() { final constructor = m.Box.named; }\n",
            **extra,
        },
    )
    reference = next(
        item
        for item in Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
        if item.site.kind == "reference" and item.site.expression == "m.Box.named"
    )
    assert (reference.status == "resolved") is known


def test_constructor_namespace_guard_preserves_preexisting_static_member_behavior(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Box { Box.named(); static void run() {} }\n",
            "lib/main.dart": "import 'model.dart' as m; "
            "import 'package:external/widgets.dart' as m;\n"
            "void main() { final ctor = m.Box.named; final method = m.Box.run; }\n",
        },
    )
    references = {
        item.site.expression: item
        for item in Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
        if item.site.kind == "reference"
    }
    assert references["m.Box.named"].status != "resolved"
    assert references["m.Box.run"].status == "resolved"


@pytest.mark.parametrize(
    "first,alternative,known",
    [
        ("class Box { Box.named(); }", "class Other {}", False),
        ("class Box { Box.named(); }", "class Box { Box.named(); }", False),
        ("export 'model.dart';", "export 'model.dart';", True),
    ],
)
def test_prefixed_constructor_reference_requires_conditional_export_binding_agreement(
    tmp_path: Path, first: str, alternative: str, known: bool
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Box { Box.named(); }\n",
            "lib/barrel.dart": "export 'first.dart' if (dart.library.io) 'alternative.dart';\n",
            "lib/first.dart": first + "\n",
            "lib/alternative.dart": alternative + "\n",
            "lib/main.dart": "import 'barrel.dart' as m;\n"
            "void run() { final constructor = m.Box.named; }\n",
        },
    )
    reference = next(
        item
        for item in Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
        if item.site.kind == "reference" and item.site.expression == "m.Box.named"
    )
    assert (reference.status == "resolved") is known


@pytest.mark.parametrize(
    "barrel,extra,known",
    [
        (
            "export 'cycle.dart' if (dart.library.io) 'model.dart';",
            {"lib/cycle.dart": "export 'barrel.dart';"},
            False,
        ),
        (
            "export 'model.dart'; export 'first.dart' if (dart.library.io) 'alternative.dart';",
            {"lib/first.dart": "class Other {}", "lib/alternative.dart": "class Another {}"},
            True,
        ),
    ],
)
def test_conditional_constructor_namespace_preserves_ancestors_and_equal_absence(
    tmp_path: Path, barrel: str, extra: dict[str, str], known: bool
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Box { Box.named(); }\n",
            "lib/barrel.dart": barrel + "\n",
            "lib/main.dart": "import 'barrel.dart' as m;\n"
            "void run() { final constructor = m.Box.named; }\n",
            **extra,
        },
    )
    reference = next(
        item
        for item in Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
        if item.site.kind == "reference" and item.site.expression == "m.Box.named"
    )
    assert (reference.status == "resolved") is known


def test_duplicate_class_candidates_do_not_resolve_constructor_or_member_call(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "class Repeated { void run() {} }\n"
            "class Repeated { void run() {} }\n"
            "void main() { Repeated().run(); }\n",
        },
    )
    sites = Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
    construction = next(item for item in sites if item.site.expression == "Repeated()")
    member_call = next(item for item in sites if item.site.expression == "Repeated().run()")

    assert construction.status == "unknown"
    assert construction.bindings == ()
    assert member_call.status == "unknown"
    assert len(member_call.bindings) == 2
    assert {item.name for item in member_call.bindings} == {"Repeated.run"}


def test_private_members_and_constructors_are_library_local(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Box { Box._(); void _secret() {} }\n",
            "lib/main.dart": "import 'model.dart';\n"
            "abstract class AbstractBox { AbstractBox(); }\n"
            "void run(Box box) { box._secret(); new Box._(); AbstractBox(); }\n",
        },
    )
    sites = Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
    private_call = next(item for item in sites if item.site.expression == "box._secret()")
    private_creation = next(item for item in sites if item.site.expression == "new Box._()")
    abstract_creation = next(item for item in sites if item.site.expression == "AbstractBox()")

    assert private_call.status == "unknown"
    assert private_call.bindings == ()
    assert private_creation.status == "unknown"
    assert private_creation.bindings == ()
    assert abstract_creation.status == "unresolved"
    assert abstract_creation.bindings == ()


def test_conditional_import_does_not_resolve_a_name_from_one_branch_only(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/base.dart": "class Stub {}\n",
            "lib/io.dart": "class Io {}\n",
            "lib/main.dart": "import 'base.dart' if (dart.library.io) 'io.dart';\n"
            "void run() { Stub(); Io(); }\n",
        },
    )
    sites = Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
    stub = next(item for item in sites if item.site.expression == "Stub()")
    io = next(item for item in sites if item.site.expression == "Io()")

    assert stub.status != "resolved"
    assert io.status != "resolved"


def test_typed_receiver_resolves_declared_member_and_unknown_receiver_stays_unknown(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "class Order { String get id => ''; }\n"
            "void run(Order order, dynamic dynamicOrder) { print(order.id); "
            "print(dynamicOrder.id); }\n",
        },
    )
    sites = Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
    member = next(item for item in sites if item.site.expression == "order.id")
    dynamic = next(item for item in sites if item.site.expression == "dynamicOrder.id")

    assert member.status == "resolved"
    assert member.bindings[0].name == "Order.id"
    assert dynamic.status == "unknown"


def test_resolve_name_strips_generic_arguments_from_local_base_types(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "class Parent<T> {}\nclass Child extends Parent<String> {}\n",
        },
    )
    resolver = Resolver(snapshot, syntax)

    assert resolver.resolve_name("lib/main.dart", "Parent<String>") == (
        "configured_namespace.main.Parent",
    )


def test_resolve_name_preserves_prefix_for_generic_imported_base_types(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Parent<T> {}\n",
            "lib/main.dart": "import 'model.dart' as models;\n"
            "class Child extends models.Parent<String> {}\n",
        },
    )
    resolver = Resolver(snapshot, syntax)

    assert resolver.resolve_name("lib/main.dart", "models.Parent<String>") == (
        "configured_namespace.model.Parent",
    )


def test_resolve_name_does_not_drop_prefix_for_local_generic_base_types(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "import 'model.dart' as models;\n"
            "class Parent<T> {}\nclass Child extends models.Parent<String> {}\n",
            "lib/model.dart": "class Other<T> {}\n",
        },
    )
    resolver = Resolver(snapshot, syntax)

    assert resolver.resolve_name("lib/main.dart", "models.Parent<String>") == ()


def test_nearest_untyped_local_shadows_outer_typed_receiver(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "class Box { void run() {} }\n"
            "void main(Box box) { { final box = unknown(); box.run(); } }\n",
        },
    )
    sites = Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
    call = next(item for item in sites if item.site.expression == "box.run()")

    assert call.status == "unknown"
    assert call.bindings == ()


def test_untyped_local_collection_shadows_outer_collection_during_fold_inference(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "class Item { void run() {} }\n"
            "void main(List<Item> items) { { final items = unknown(); "
            "items.fold(0, (sum, item) => item.run()); } }\n",
        },
    )
    sites = Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
    call = next(item for item in sites if item.site.expression == "item.run()")

    assert call.status == "unknown"
    assert call.bindings == ()


def test_constructor_inference_uses_the_call_inside_the_selected_binding(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "class Box { void run() {} }\n"
            "void main() { final first = Box(); { final Box = unknown; "
            "final second = Box(); second.run(); } first.run(); }\n",
        },
    )
    sites = Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
    first = next(item for item in sites if item.site.expression == "first.run()")
    second = next(item for item in sites if item.site.expression == "second.run()")

    assert first.status == "resolved"
    assert second.status == "unknown"


def test_imported_typed_receiver_and_prefixed_static_member_resolve(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/model.dart": "class Order { String get id => ''; static void go() {} }\n",
            "lib/main.dart": "import 'model.dart' as model;\n"
            "void run(model.Order order) { print(order.id); model.Order.go(); }\n",
        },
    )
    sites = Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
    member = next(item for item in sites if item.site.expression == "order.id")
    static = next(item for item in sites if item.site.expression == "model.Order.go()")

    assert member.status == "resolved"
    assert member.bindings[0].module == "configured_namespace.model"
    assert static.status == "resolved"
    assert static.bindings[0].name == "Order.go"


def test_super_formal_inherits_generic_parent_type_and_default(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "class Parent<T> { Parent({required T key}); }\n"
            "class Child extends Parent<String> { Child({required super.key}); }\n",
        },
    )
    resolver = Resolver(snapshot, syntax)
    definition = next(item for item in syntax["lib/main.dart"].definitions if item.name == "Child")
    constructor = next(item for item in definition.members if item.kind == "constructor")

    resolved = resolver.resolve_parameters("lib/main.dart", definition, constructor)

    assert [
        (item.name, item.annotation, item.default, item.default_known)
        for item in resolved.parameters
    ] == [("key", "String", None, True)]
    assert resolved.problems == ()


def test_super_formal_inherits_implicit_null_default(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "class Parent { Parent({String? value}); }\n"
            "class Child extends Parent { Child({super.value}); }\n",
        },
    )
    resolver = Resolver(snapshot, syntax)
    definition = next(item for item in syntax["lib/main.dart"].definitions if item.name == "Child")
    constructor = next(item for item in definition.members if item.kind == "constructor")

    resolved = resolver.resolve_parameters("lib/main.dart", definition, constructor)

    assert len(resolved.parameters) == 1
    assert resolved.parameters[0].default == "null"
    assert resolved.parameters[0].default_known is True
    assert resolved.problems == ()


def test_redirected_factory_inherits_terminal_field_default(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "abstract interface class Direct { "
            "factory Direct({List<String> value}) = DirectImpl; }\n"
            "class DirectImpl { DirectImpl({this.value = const []}); "
            "final List<String> value; }\n",
        },
    )
    resolver = Resolver(snapshot, syntax)
    definition = next(item for item in syntax["lib/main.dart"].definitions if item.name == "Direct")
    factory = next(item for item in definition.members if item.kind == "constructor")

    resolved = resolver.resolve_parameters("lib/main.dart", definition, factory)

    assert [
        (item.name, item.annotation, item.default, item.default_known)
        for item in resolved.parameters
    ] == [("value", "List<String>", "const []", True)]
    assert resolved.problems == ()


def test_redirected_factory_substitutes_dollar_prefixed_generic_parameters(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "abstract class CopyWith<$Res, $Value> { "
            "factory CopyWith($Value value, $Res Function($Value) then) = "
            "CopyWithImpl<$Res, $Value>; }\n"
            "class CopyWithImpl<R, V> implements CopyWith<R, V> { "
            "CopyWithImpl(this.value, this.then); final V value; "
            "final R Function(V) then; }\n",
        },
    )
    resolver = Resolver(snapshot, syntax)
    definition = next(
        item for item in syntax["lib/main.dart"].definitions if item.name == "CopyWith"
    )
    factory = next(item for item in definition.members if item.kind == "constructor")

    resolved = resolver.resolve_parameters("lib/main.dart", definition, factory)

    assert [item.annotation for item in resolved.parameters] == [
        "$Value",
        "$Res Function($Value)",
    ]
    assert resolved.problems == ()


def test_redirected_factory_preserves_typed_collection_default_literal(
    tmp_path: Path,
) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/main.dart": "abstract class Values { "
            "factory Values({List<int> items}) = ValuesImpl; }\n"
            "class ValuesImpl { ValuesImpl({this.items = const <int>[]}); "
            "final List<int> items; }\n",
        },
    )
    resolver = Resolver(snapshot, syntax)
    definition = next(item for item in syntax["lib/main.dart"].definitions if item.name == "Values")
    factory = next(item for item in definition.members if item.kind == "constructor")

    resolved = resolver.resolve_parameters("lib/main.dart", definition, factory)

    assert len(resolved.parameters) == 1
    assert resolved.parameters[0].default == "const <int>[]"
    assert resolved.parameters[0].default_known is True
    assert resolved.problems == ()


def test_shadowed_prefix_does_not_bind_to_import_alias(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/dependency.dart": "class Thing {}\n",
            "lib/main.dart": "import 'dependency.dart' as dep;\nvoid run() { dep.Thing(); }\n",
        },
    )
    parsed = syntax["lib/main.dart"]
    sites = tuple(
        replace(site, shadowed_names=("dep",)) if site.kind == "call" else site
        for site in parsed.sites
    )
    syntax["lib/main.dart"] = replace(parsed, sites=sites)

    resolved = next(
        item
        for item in Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
        if item.site.kind == "call"
    )

    assert resolved.status == "unknown"
    assert resolved.bindings == ()


def test_actual_parameter_shadowing_blocks_an_import_prefix(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {
            "lib/dependency.dart": "class Thing {}\n",
            "lib/main.dart": "import 'dependency.dart' as dep;\n"
            "void run(dynamic dep) { dep.Thing(); }\n",
        },
    )

    resolved = next(
        item
        for item in Resolver(snapshot, syntax).resolved_sites("lib/main.dart")
        if item.site.kind == "call"
    )

    assert resolved.status == "unknown"
    assert resolved.bindings == ()


def test_duplicate_module_ids_do_not_resolve(tmp_path: Path) -> None:
    snapshot, syntax = _snapshot(
        tmp_path,
        {"lib/a-b.dart": "class A {}\n", "lib/a_b.dart": "class B {}\n"},
    )
    resolver = Resolver(snapshot, syntax)

    assert resolver.module_for("lib/a-b.dart") is None
    assert resolver.module_for("lib/a_b.dart") is None
