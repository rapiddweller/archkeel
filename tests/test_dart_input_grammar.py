# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Actual Dart grammar and compatible visibility ingress controls."""

from dataclasses import FrozenInstanceError, replace
from typing import get_type_hints

import pytest
from test_dart_resolve import _snapshot


from archkeel.analyzer.dart import collect, parse, resolve, syntax
from archkeel.ir.protocol import CollectionRequest, DartSettings, SnapshotInput, SourceScope


@pytest.mark.parametrize(
    "name,expected",
    [
        ("value", syntax.Visibility.PUBLIC),
        ("_value", syntax.Visibility.PRIVATE),
        ("Widget._named", syntax.Visibility.PRIVATE),
        ("_Widget.named", syntax.Visibility.PUBLIC),
        ("module.Widget._named", syntax.Visibility.PRIVATE),
        ("_λ", syntax.Visibility.PRIVATE),
        ("λ", syntax.Visibility.PUBLIC),
        ("", syntax.Visibility.PUBLIC),
    ],
)
def test_visibility_has_one_owned_name_ingress(name, expected):
    decode = getattr(syntax.Visibility, "from_name", None)
    assert callable(decode), "Visibility owns name grammar at ingress"
    assert decode(name) is expected


@pytest.mark.parametrize("keyword", [False, True])
def test_old_binding_constructor_derives_owned_visibility_once(keyword):
    span = syntax.Span(1, 1, 0, "Widget._named", 0, 13)
    arguments = dict(
        module="example.widget",
        name="Widget._named",
        kind=syntax.MemberKind.CONSTRUCTOR,
        via_prefix=None,
        declaration_id="constructor",
        rel_path="lib/widget.dart",
        span=span,
    )
    binding = (
        resolve.ResolvedBinding(**arguments)
        if keyword
        else resolve.ResolvedBinding(*arguments.values())
    )
    assert get_type_hints(resolve.ResolvedBinding).get("visibility") is syntax.Visibility
    assert getattr(binding, "visibility", None) is syntax.Visibility.PRIVATE
    assert (
        getattr(replace(binding, name="Widget.named"), "visibility", None)
        is syntax.Visibility.PUBLIC
    )
    assert (
        getattr(replace(binding, name="Other._hidden"), "visibility", None)
        is syntax.Visibility.PRIVATE
    )
    assert (
        getattr(replace(binding, module="other"), "visibility", None) is syntax.Visibility.PRIVATE
    )
    with pytest.raises(FrozenInstanceError):
        binding.name = "changed"
    assert not hasattr(binding, "__dict__")


def test_actual_named_constructor_visibility_and_const_are_not_name_prefixes():
    result = parse.parse(
        b"class constance { constance(); const constance.fixed(); constance._hidden(); }",
    )
    assert result.complete and not result.concerns
    members = {member.name: member for member in result.definitions[0].members}
    assert members["constance"].constant is False
    assert members["constance.fixed"].constant is True
    assert members["constance._hidden"].visibility is syntax.Visibility.PRIVATE


@pytest.mark.parametrize(
    "source",
    [
        b"/* outer /* inner */ outer */ void main() {}",
        b'var value = "/* string */"; // line\nvoid main() {}',
        b"import /* outside /* nested */ still */ 'other.dart';",
        b"var value = r'/* raw'; void main() {}",
        b'var value = """/* triple */"""; void main() {}',
    ],
)
def test_comment_grammar_keeps_actual_strings_and_nested_comments(source):
    result = parse.parse(source)
    assert result.complete and result.first_error is None


def test_unclosed_nested_comment_retains_concern_and_source_position():
    result = parse.parse(b"void main() {}\n/* outer /* inner */")
    assert not result.complete
    assert result.concerns
    assert any(concern.span.line == 2 for concern in result.concerns)


def test_filename_decoder_retains_dotfile_validation_and_suffix_selection(tmp_path):
    snapshot, _ = _snapshot(
        tmp_path,
        {
            "lib/.dart": "",
            "lib/valid.dart": "class Valid {}",
            "lib/ignored.dartx": "class Ignored {}",
            "lib/ignored.DART": "class IgnoredUppercase {}",
        },
    )
    accounted = {source.rel_path for source in snapshot.sources} | {
        problem.path for problem in snapshot.problems
    }
    assert "lib/.dart" in accounted
    assert "lib/valid.dart" in accounted
    assert "lib/ignored.dartx" not in accounted
    assert "lib/ignored.DART" not in accounted


def test_real_receiver_resolution_requires_existing_call_facts(tmp_path):
    snapshot, parsed = _snapshot(
        tmp_path,
        {"lib/main.dart": "class Box { Box(); void work() {} } void run() { Box().work(); }"},
    )
    source = parsed["lib/main.dart"]
    outer = next(site for site in source.sites if site.kind is syntax.SiteKind.CALL and site.name == "work")
    normal = resolve.Resolver(snapshot, parsed)
    assert normal._receiver_bindings("lib/main.dart", "configured_namespace.main", outer)
    missing = replace(
        source,
        sites=tuple(site for site in source.sites if site.expression != "Box()"),
    )
    without_call = resolve.Resolver(snapshot, {"lib/main.dart": missing})
    assert not without_call._receiver_bindings("lib/main.dart", "configured_namespace.main", outer)


@pytest.mark.parametrize(
    "body",
    [
        "void run(List<Box> boxes) { boxes[0].work(); }",
        "void run() { void Box() {} Box().work(); }",
        "void run() { var callback = () { void Box() {} Box().work(); }; callback(); }",
    ],
)
def test_index_and_shadowed_receiver_forms_do_not_gain_known_targets(tmp_path, body):
    snapshot, parsed = _snapshot(
        tmp_path,
        {"lib/main.dart": "class Box { Box(); void work() {} } " + body},
    )
    resolver = resolve.Resolver(snapshot, parsed)
    results = [
        result for result in resolver.resolved_sites("lib/main.dart")
        if result.site.name == "work" and result.site.kind is syntax.SiteKind.CALL
    ]
    assert results
    assert all(result.status is not resolve.ResolutionStatus.RESOLVED for result in results)


def test_member_constructor_attribute_and_binding_visibility_keep_wire_semantics(tmp_path):
    _snapshot(
        tmp_path,
        {"lib/main.dart": (
            "class _Owner { _Owner.named(); _Owner._hidden(); int _field=0; int field=0; } "
            "void run() { var _local=1; var local=2; }"
        )},
    )
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("lib",), "configured_namespace"),
        DartSettings(),
    )
    facts = collect.collect(request)
    symbols = {
        record.data.get("name"): record for section in facts.sections
        if section.name == "symbols" for record in section.records
    }
    assert symbols["_Owner.named"].data["visibility"].get("kind") == "public"
    assert symbols["_Owner._hidden"].data["visibility"].get("kind") == "private"
    attributes = {
        item.get("name"): item for item in symbols["_Owner"].data["attribute_declarations"]
    }
    assert attributes["_field"]["visibility"].get("kind") == "private"
    assert attributes["field"]["visibility"].get("kind") == "public"
    assert symbols["_local"].data["visibility"].get("kind") == "private"
    assert symbols["local"].data["visibility"].get("kind") == "public"
