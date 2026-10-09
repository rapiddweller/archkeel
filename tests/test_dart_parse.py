# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dart syntax facts retain source evidence without returning parser nodes."""

from archkeel.analyzer.dart.parse import Syntax, parse


def test_declarations_keep_member_kinds_and_source_written_signatures() -> None:
    syntax = parse(
        b"""abstract interface class Box<T> implements Value {
  final String id;
  Box(this.id, {required int count = 1});
  String get value => id;
  set value(String next) {}
  static const size = 2;
}
mixin Stamp {}
enum State { pending, complete }
typedef Handler = void Function(String value);
"""
    )

    box, stamp, state, handler = syntax.definitions
    assert (box.name, box.kind, box.implements) == ("Box", "interface", ("Value",))
    assert [member.kind for member in box.members] == [
        "field",
        "constructor",
        "getter",
        "setter",
        "field",
    ]
    constructor = box.members[1]
    field_formal, named = constructor.parameters
    assert (field_formal.name, field_formal.field_formal) == ("id", True)
    assert field_formal.annotation is None
    assert (named.name, named.kind, named.default, named.default_known) == (
        "count",
        "named",
        "1",
        True,
    )
    assert (box.members[2].name, box.members[3].name) == ("value", "value")
    assert box.members[3].return_type is None
    assert (box.members[4].static, box.members[4].constant) == (True, True)
    assert (stamp.kind, state.kind, state.enum_members, handler.kind) == (
        "mixin",
        "enum",
        ("pending", "complete"),
        "typedef",
    )
    assert all(
        item.span.start_byte >= 0 and item.span.end_byte > item.span.start_byte
        for item in syntax.definitions
    )


def test_directives_keep_ordered_combinators_and_conditional_uris() -> None:
    syntax = parse(
        b"import 'base.dart' if (dart.library.io) 'io.dart' "
        b"if (dart.library.html) 'web.dart' as base show A hide B show C;\n"
        b"part 'details.dart';\n"
        b"part of 'main.dart';\n"
    )

    imported, part, part_of = syntax.directives
    assert (imported.kind, imported.target) == ("import", "base.dart")
    assert imported.prefix == "base"
    assert imported.alternatives == (
        ("dart.library.io", "io.dart"),
        ("dart.library.html", "web.dart"),
    )
    assert imported.combinators == (("show", ("A",)), ("hide", ("B",)), ("show", ("C",)))
    assert (part.kind, part.target, part_of.kind, part_of.target) == (
        "part",
        "details.dart",
        "part_of",
        "main.dart",
    )


def test_sites_preserve_creation_calls_and_lexical_bindings() -> None:
    syntax = parse(
        b"""class Box { Box(Inner value); }
Inner makeInner() => new Inner();
void configure() {
  register(() { final value = Box(makeInner()); print(value); });
}
"""
    )

    creations = {site.expression: site for site in syntax.sites if site.kind == "creation"}
    calls = {site.expression for site in syntax.sites if site.kind == "call"}
    assert set(creations) == {"new Inner()"}
    assert {"Box(makeInner())", "makeInner()"} <= calls
    binding = next(site for site in syntax.sites if site.kind == "binding" and site.initializer)
    assert (binding.name, binding.initializer) == ("value", "Box(makeInner())")
    assert binding.scope_span is not None
    assert any(site.kind == "reference" and site.expression == "value" for site in syntax.sites)


def test_factory_constructor_remains_a_constructor_member() -> None:
    syntax = parse(
        b"class Box { factory Box.named(String id) => Box(id); }\n"
        b"class Other {}\n"
        b"abstract class Alias { factory Alias.from() = Other.named; }"
    )
    box = next(item for item in syntax.definitions if item.name == "Box")
    (factory,) = box.members
    assert (factory.kind, factory.name, factory.factory) == ("constructor", "Box.named", True)
    assert factory.redirect is None
    alias = next(item for item in syntax.definitions if item.name == "Alias")
    assert alias.members[0].redirect == "Other.named"
    assert any(site.kind == "call" and site.expression == "Box(id)" for site in syntax.sites)


def test_recovered_or_unsupported_syntax_is_explicitly_incomplete() -> None:
    syntax: Syntax = parse(b"class {")
    assert syntax.complete is False
    assert syntax.first_error is not None
    assert syntax.concerns


def test_language_override_and_optional_parameter_shape_are_explicit() -> None:
    syntax = parse(
        b"// @dart=3.99\n"
        b"const currency = 'USD';\n"
        b"void configure(String id, [String? label = null]) {}\n"
        b"void named({required bool verbose, int retries = 2}) {}\n"
    )
    configure = next(item for item in syntax.definitions if item.name == "configure")
    positional, optional = configure.parameters
    named = next(item for item in syntax.definitions if item.name == "named")
    required, defaulted = named.parameters
    assert (syntax.language_version, syntax.complete) == ("3.99", False)
    assert any(item.kind == "LanguageVersionError" for item in syntax.concerns)
    assert (positional.optional, positional.required) == (False, False)
    assert (optional.kind, optional.optional, optional.default) == ("positional", True, "null")
    assert (required.kind, required.optional, required.required) == ("named", False, True)
    assert (defaulted.kind, defaulted.optional, defaulted.default) == ("named", True, "2")
    currency = next(item for item in syntax.definitions if item.name == "currency")
    assert currency.constant is True


def test_positions_use_utf16_columns_and_byte_offsets() -> None:
    syntax = parse('String text = "😀";\nclass Box {}'.encode())
    box = next(item for item in syntax.definitions if item.name == "Box")
    assert (box.span.line, box.span.column, box.span.start_byte) == (2, 0, 22)


def test_invalid_utf8_is_a_parse_concern_and_crlf_positions_are_stable() -> None:
    syntax = parse(b"// \xf0\x9f\x98\x80\r\nclass Box {}\n\xff")
    box = next(item for item in syntax.definitions if item.name == "Box")
    assert (box.span.line, box.span.column) == (2, 0)
    assert any(item.kind == "invalid_encoding" for item in syntax.concerns)
    assert syntax.complete is False


def test_directive_names_and_call_callees_are_not_duplicate_reference_sites() -> None:
    syntax = parse(
        b"import 'model.dart' show Model, Other;\n"
        b"void use(Box box) { Model.named(); box.value; box.value = 1; }\n"
    )
    references = [site.expression for site in syntax.sites if site.kind == "reference"]
    calls = [site.expression for site in syntax.sites if site.kind == "call"]
    assert "Model" not in references
    assert "named" not in references
    assert "Model.named()" in calls
    assert "box.value" in references
    assert any(
        site.kind == "assignment" and site.expression == "box.value = 1" for site in syntax.sites
    )


def test_generic_field_annotation_retains_type_arguments() -> None:
    syntax = parse(b"class Order {}\nclass Repository { final Map<String, Order> _orders = {}; }\n")
    repository = next(item for item in syntax.definitions if item.name == "Repository")
    (orders,) = repository.members
    assert orders.annotation == "Map<String, Order>"


def test_alias_bases_mixin_modifiers_accessors_and_member_receivers() -> None:
    syntax = parse(
        b"class Base {}\ntypedef Alias = Base;\n"
        b"class Child extends Alias with Stamp, Track {}\n"
        b"mixin class Shared {}\nenum Status with Track { ready }\nint get status => 1;\n"
        b"void read(Order order) { final receiptId = order.id; new Base.named(); }\n"
    )
    alias = next(item for item in syntax.definitions if item.name == "Alias")
    child = next(item for item in syntax.definitions if item.name == "Child")
    shared = next(item for item in syntax.definitions if item.name == "Shared")
    getter = next(item for item in syntax.definitions if item.name == "status")
    status = next(item for item in syntax.definitions if item.name == "Status")
    assert status.with_types == ("Track",)
    assert alias.alias == "Base"
    assert (child.extends, child.with_types) == (("Alias",), ("Stamp", "Track"))
    assert shared.modifiers == ("mixin",)
    assert (getter.kind, getter.return_type) == ("getter", "int")
    access = next(site for site in syntax.sites if site.kind == "reference" and site.name == "id")
    assert (access.expression, access.receiver) == ("order.id", "order")
    receiver = next(
        site for site in syntax.sites if site.kind == "reference" and site.expression == "order"
    )
    assert receiver.span.excerpt == "order"
    creation = next(site for site in syntax.sites if site.kind == "creation")
    assert creation.name == "Base.named"


def test_setter_return_keyword_is_not_reported_as_a_type() -> None:
    syntax = parse(
        b"class Box { set value(int next) {} }\nclass TypedBox { void set value(int next) {} }"
    )
    setters = [member for definition in syntax.definitions for member in definition.members]
    assert [setter.return_type for setter in setters] == [None, "void"]


def test_multiline_call_span_uses_callee_start_utf16_column_and_byte_range() -> None:
    source = "// 😀\r\nvoid run() {\r\n  process(\r\n    1,\r\n  );\r\n}".encode()
    syntax = parse(source)
    call = next(site for site in syntax.sites if site.kind == "call")
    start = source.index(b"process")
    end = source.index(b"  );") + len(b"  )")
    assert call.span.line == 3
    assert call.span.column == 2
    assert call.span.start_byte == start
    assert call.span.end_byte == end
    assert call.span.excerpt == source[start:end].decode()


def test_typed_const_function_parameter_and_unmodeled_mixin_constraint() -> None:
    syntax = parse(
        b"const int LIMIT = 5;\n"
        b"void configure(void callback(String value)) {}\n"
        b"mixin Stamp on Root {}"
    )
    limit = next(item for item in syntax.definitions if item.name == "LIMIT")
    configure = next(item for item in syntax.definitions if item.name == "configure")
    assert limit.constant is True
    assert configure.parameters[0].annotation == "void Function(String value)"
    assert any(
        item.kind == "unsupported_declaration" and "on-constraints" in item.message
        for item in syntax.concerns
    )


def test_static_methods_callable_scopes_and_enum_literal_spans() -> None:
    syntax = parse(
        b"enum Status { pending, complete }\n"
        b"class Order { static void go() {} }\n"
        b"void configure(void callback(String value)) {\n"
        b"  consume((String item) { print(item); });\n"
        b"}\n"
    )
    status = next(item for item in syntax.definitions if item.name == "Status")
    order = next(item for item in syntax.definitions if item.name == "Order")
    configure = next(item for item in syntax.definitions if item.name == "configure")
    (callback,) = configure.parameters
    (method,) = order.members
    assert method.static is True
    assert len(status.enum_member_spans) == len(status.enum_members) == 2
    assert [span.excerpt for span in status.enum_member_spans] == ["pending", "complete"]
    bindings = [site for site in syntax.sites if site.kind == "binding"]
    callback_binding = next(site for site in bindings if site.name == "callback")
    item_binding = next(site for site in bindings if site.name == "item")
    assert callback.annotation == "void Function(String value)"
    assert (callback_binding.scope, callback_binding.scope_span) == (
        "configure",
        next(
            site.scope_span
            for site in syntax.sites
            if site.kind == "call" and site.name == "consume"
        ),
    )
    assert item_binding.scope == "configure" and item_binding.scope_span is not None
    assert any(
        site.kind == "reference"
        and site.name == "item"
        and site.scope_span == item_binding.scope_span
        for site in syntax.sites
    )
    assert not any(site.kind == "binding" and site.name == "value" for site in syntax.sites)


def test_optional_nullable_named_parameter_defaults_to_null() -> None:
    syntax = parse(b"void configure({String? subtitle}) {}")
    configure = next(item for item in syntax.definitions if item.name == "configure")
    assert configure.parameters[0].default == "null"


def test_generic_base_types_retain_their_type_arguments() -> None:
    syntax = parse(
        b"class Parent<T> {}\n"
        b"mixin Stamp<T> {}\n"
        b"class Child extends Parent<String> with Stamp<int> implements Parent<bool> {}"
    )
    child = next(item for item in syntax.definitions if item.name == "Child")
    assert child.extends == ("Parent<String>",)
    assert child.with_types == ("Stamp<int>",)
    assert child.implements == ("Parent<bool>",)


def test_receiver_references_cover_index_reads_and_typed_call_receivers() -> None:
    syntax = parse(
        b"class Repository { final Map<String, Order> _orders = {}; "
        b"Order? findById(String id) => _orders[id]; }\n"
        b"class Policy { final int _percent; "
        b"int discountCents(int total) => total * _percent.clamp(0, 50); }"
    )
    references = [site for site in syntax.sites if site.kind == "reference"]
    indexed_receiver = next(site for site in references if site.name == "_orders")
    call_receiver = next(site for site in references if site.name == "_percent")
    assert (indexed_receiver.expression, indexed_receiver.receiver) == ("_orders", None)
    assert (call_receiver.expression, call_receiver.receiver) == ("_percent", None)
    assert indexed_receiver.span.excerpt == "_orders"
    assert call_receiver.span.excerpt == "_percent"
    assert indexed_receiver.scope == "findById"
    assert call_receiver.scope == "discountCents"
    assert sum(site.name == "_orders" for site in references) == 1
    assert sum(site.name == "_percent" for site in references) == 1


def test_typed_property_receiver_is_retained_without_prefix_or_unknown_receiver_sites() -> None:
    syntax = parse(
        b"import 'models.dart' as dep;\n"
        b"class Order {}\n"
        b"class Cart { final Order _cart; void read() {\n"
        b"  _cart.lines; unknown.value; dep.Order.named();\n"
        b"} }"
    )
    references = [site for site in syntax.sites if site.kind == "reference"]
    receiver = next(site for site in references if site.expression == "_cart")
    access = next(site for site in references if site.expression == "_cart.lines")
    assert receiver.span.excerpt == "_cart"
    assert access.receiver == "_cart"
    assert sum(site.expression == "_cart" for site in references) == 1
    assert not any(site.expression in {"unknown", "dep"} for site in references)


def test_enhanced_enum_exposes_constructor_fields_and_methods() -> None:
    syntax = parse(
        b"enum Status { pending('pending'), complete('complete');\n"
        b" const Status(this.label);\n"
        b" final String label;\n"
        b" String get displayName => label;\n"
        b"}\n"
    )
    status = next(item for item in syntax.definitions if item.name == "Status")
    assert status.enum_members == ("pending", "complete")
    assert [member.name for member in status.members] == ["Status", "label", "displayName"]
    assert status.members[0].kind == "constructor"
    assert status.members[0].constant is True
    assert status.members[0].parameters[0].field_formal is True
    assert status.members[1].kind == "field"
    assert status.members[1].annotation == "String"
    assert status.members[2].kind == "getter"


def test_const_redirecting_factory_and_equality_operator_metadata() -> None:
    syntax = parse(
        b"class Result { const factory Result.ok() = Ok; bool operator ==(Object other) => true; }"
    )
    result = next(item for item in syntax.definitions if item.name == "Result")
    factory, equality = result.members
    assert (factory.name, factory.factory, factory.constant, factory.redirect) == (
        "Result.ok",
        True,
        True,
        "Ok",
    )
    assert (equality.name, equality.kind) == ("operator==", "operator")


def test_multiline_call_initializer_has_canonical_source_and_raw_evidence() -> None:
    source = b"void build() {\n  final app = ShopApp(\n    backend,\n    store,\n  );\n}\n"
    syntax = parse(source)
    binding = next(site for site in syntax.sites if site.kind == "binding" and site.name == "app")
    call = next(site for site in syntax.sites if site.kind == "call" and site.name == "ShopApp")
    assert binding.initializer_source == "ShopApp(backend, store)"
    assert call.expression_source == "ShopApp(backend, store)"
    assert binding.initializer == "ShopApp(\n    backend,\n    store,\n  )"
    assert binding.span.excerpt == "final app = ShopApp(\n    backend,\n    store,\n  )"


def test_canonical_source_keeps_generic_call_arguments_tight() -> None:
    syntax = parse(b"Repository<int> make() => Repository<int>();")
    call = next(site for site in syntax.sites if site.kind == "call")
    assert call.expression_source == "Repository<int>()"


def test_canonical_call_drops_comments_but_preserves_string_literal_content() -> None:
    source = b'void build() { final app = ShopApp(backend, // note\n "x, y",); }'
    syntax = parse(source)
    call = next(site for site in syntax.sites if site.kind == "call" and site.name == "ShopApp")
    binding = next(site for site in syntax.sites if site.kind == "binding" and site.name == "app")
    assert call.expression_source == 'ShopApp(backend, "x, y")'
    assert binding.initializer_source == call.expression_source
    assert "// note" in binding.span.excerpt


def test_dart_uri_string_forms_are_decoded_as_one_literal() -> None:
    syntax = parse(
        b"import r'package:app/core/api.dart';\n"
        b"import '''package:app/core/impl.dart''';\n"
        b'import """package:app/core/hidden.dart""";\n'
        b"import 'package:app/' \"core/api.dart\";\n"
        b"import 'package:app/core/' r'impl' '.dart';\n"
    )
    assert [item.target for item in syntax.directives] == [
        "package:app/core/api.dart",
        "package:app/core/impl.dart",
        "package:app/core/hidden.dart",
        "package:app/core/api.dart",
        "package:app/core/impl.dart",
    ]
    assert syntax.complete


def test_export_and_deferred_import_directives_keep_literal_uris() -> None:
    syntax = parse(
        b"export 'package:app/core/api.dart' show Api;\n"
        b"export 'package:app/core/impl.dart';\n"
        b"import 'package:app/core/hidden.dart' deferred as lazy;\n"
    )
    assert [(item.kind, item.target) for item in syntax.directives] == [
        ("export", "package:app/core/api.dart"),
        ("export", "package:app/core/impl.dart"),
        ("import", "package:app/core/hidden.dart"),
    ]
    assert syntax.directives[-1].deferred is True
    assert syntax.directives[-1].prefix == "lazy"
    assert syntax.complete


def test_unterminated_nested_block_comment_is_explicitly_incomplete() -> None:
    syntax = parse(b"/* open /* nested */\nimport 'x.dart';\nclass Box {}")
    assert not syntax.complete
    assert any(item.kind == "syntax_error" for item in syntax.concerns)


def test_expression_bodied_member_and_setter_assignment_keep_callable_context() -> None:
    syntax = parse(
        b"class Box { T forward(T value) => echo(value); }\n"
        b"void update(Box box) { box.value = 1; box.count += 1; }"
    )
    forward_call = next(site for site in syntax.sites if site.kind == "call")
    forward_reference = next(
        site for site in syntax.sites if site.kind == "reference" and site.expression == "value"
    )
    assert forward_call.scope == "forward"
    assert forward_reference.scope == "forward"
    writes = [site for site in syntax.sites if site.kind == "reference" and site.receiver == "box"]
    assert [(site.expression, site.receiver, site.use) for site in writes] == [
        ("box.value", "box", "write"),
        ("box.count", "box", "read_write"),
    ]


def test_top_level_getter_reads_and_setter_writes_remain_reference_sites() -> None:
    syntax = parse(
        b"int get status => 1;\n"
        b"set status(int next) {}\n"
        b"void read() { final current = status; status = 2; }"
    )
    references = [
        site for site in syntax.sites if site.kind == "reference" and site.name == "status"
    ]
    assert [(site.expression, site.use) for site in references] == [
        ("status", "read"),
        ("status", "write"),
    ]


def test_signature_and_constructor_initializer_sites_keep_callable_scope() -> None:
    syntax = parse(
        b"class Repository {}\n"
        b"class Service {\n"
        b"  Service(Repository repository) : _repository = repository;\n"
        b"  final Repository _repository;\n"
        b"  Repository load(Repository fallback) => fallback;\n"
        b"}"
    )
    repository_types = [
        site for site in syntax.sites if site.kind == "type" and site.name == "Repository"
    ]
    assert [site.scope for site in repository_types] == ["Service", None, "load", "load"]
    initializer = next(
        site
        for site in syntax.sites
        if site.kind == "reference" and site.expression == "_repository"
    )
    assert initializer.scope == "Service"
    assert initializer.scope_span is not None
