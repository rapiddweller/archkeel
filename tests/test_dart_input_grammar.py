# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Actual Dart grammar and compatible visibility ingress controls."""

from dataclasses import FrozenInstanceError, replace
from typing import get_type_hints

import pytest

from archkeel.analyzer.dart import parse, resolve, syntax


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
    assert getattr(replace(binding, name="Widget.named"), "visibility", None) is syntax.Visibility.PUBLIC
    assert getattr(replace(binding, name="Other._hidden"), "visibility", None) is syntax.Visibility.PRIVATE
    assert getattr(replace(binding, module="other"), "visibility", None) is syntax.Visibility.PRIVATE
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
