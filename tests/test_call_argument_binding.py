# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Actuals bind only through admitted pure-data Python signatures."""

from archkeel.check.evaluation.call_arguments import bind_call_arguments
from archkeel.ir.facts import CallArgument, CallArgumentKind, CallArgumentValueKind, RecordData


def _parameter(name, kind, *, default=None, default_known=True):
    return RecordData(
        (
            ("name", name),
            ("kind", kind),
            ("default", default),
            ("default_known", default_known),
        )
    )


def _signature(*parameters, receiver_parameter=None):
    return RecordData(
        (("parameters", tuple(parameters)), ("receiver_parameter", receiver_parameter))
    )


def _argument(kind, keyword=None, *, value_kind="other", evidence="e"):
    return CallArgument(
        CallArgumentKind(kind),
        keyword,
        CallArgumentValueKind(value_kind),
        "written" if value_kind == "string_literal" else None,
        (evidence,),
    )


def test_binds_written_keyword_and_leaves_omitted_default_unbound():
    signature = _signature(
        _parameter("query", "positional", default=""),
        _parameter("label", "keyword_only", default=""),
    )

    result = bind_call_arguments(
        signature,
        (_argument("keyword", "label", value_kind="string_literal", evidence="label"),),
        bound_receiver=False,
    )

    assert result is not None
    assert result.by_parameter == (("label", (0,)),)


def test_positional_only_name_keyword_binds_to_kwargs_instead():
    signature = _signature(
        _parameter("query", "positional_only", default="default"),
        _parameter("options", "kwargs"),
    )

    result = bind_call_arguments(
        signature,
        (_argument("keyword", "query", value_kind="string_literal"),),
        bound_receiver=False,
    )

    assert result is not None
    assert result.by_parameter == (("options", (0,)),)
    assert not dict(result.by_parameter).get("query")


def test_invalid_duplicate_and_spread_actuals_remain_unbound():
    signature = _signature(_parameter("query", "positional"))

    duplicate = bind_call_arguments(
        signature,
        (_argument("positional"), _argument("keyword", "query")),
        bound_receiver=False,
    )
    spread = bind_call_arguments(
        signature,
        (_argument("starred_positional"),),
        bound_receiver=False,
    )

    assert duplicate is None
    assert spread is None


def test_positional_only_keyword_with_kwargs_is_a_distinct_actual():
    signature = _signature(
        _parameter("query", "positional_only", default="default"),
        _parameter("options", "kwargs"),
    )
    result = bind_call_arguments(
        signature,
        (_argument("positional"), _argument("keyword", "query", value_kind="string_literal")),
        bound_receiver=False,
    )

    assert result is not None
    assert result.by_parameter == (("query", (0,)), ("options", (1,)))


def test_duplicate_keyword_actuals_are_unknown_even_with_kwargs():
    signature = _signature(_parameter("query", "positional"), _parameter("options", "kwargs"))
    result = bind_call_arguments(
        signature,
        (_argument("keyword", "query"), _argument("keyword", "query")),
        bound_receiver=False,
    )

    assert result is None


def test_variadic_actuals_keep_their_own_formal_destinations():
    signature = _signature(
        _parameter("query", "positional"),
        _parameter("parts", "varargs"),
        _parameter("label", "keyword_only", default=""),
        _parameter("options", "kwargs"),
    )
    result = bind_call_arguments(
        signature,
        (
            _argument("positional"),
            _argument("positional", value_kind="string_literal"),
            _argument("keyword", "label"),
            _argument("keyword", "extra", value_kind="string_literal"),
        ),
        bound_receiver=False,
    )

    assert result is not None
    assert result.by_parameter == (
        ("query", (0,)),
        ("parts", (1,)),
        ("label", (2,)),
        ("options", (3,)),
    )
