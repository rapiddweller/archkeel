# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A local callable cannot become an unrelated global class construction."""

from dataclasses import replace

import pytest
from test_dart_resolve import _snapshot

from archkeel.analyzer.dart import resolve, syntax


@pytest.mark.parametrize(
    "body",
    [
        "void run() { void Box() {} Box().work(); }",
        "void run() { var callback = () { void Box() {} Box().work(); }; callback(); }",
        "void run() { var Box = () {}; Box().work(); }",
        "void run(void Function() Box) { Box().work(); }",
        "void run() { Box().work(); void Box() {} }",
    ],
)
def test_local_callable_never_proves_global_constructor_member(tmp_path, body):
    snapshot, parsed = _snapshot(
        tmp_path,
        {"lib/main.dart": "class Box { Box(); void work() {} } " + body},
    )
    resolver = resolve.Resolver(snapshot, parsed)
    results = [
        result
        for result in resolver.resolved_sites("lib/main.dart")
        if result.site.kind is syntax.SiteKind.CALL and result.site.name == "work"
    ]
    assert results
    assert all(result.status is not resolve.ResolutionStatus.RESOLVED for result in results)
    assert all(not result.bindings for result in results)


@pytest.mark.parametrize(
    "body",
    [
        "void run() { Box().work(); }",
        "void other() { void Box() {} } void run() { Box().work(); }",
        "void run() { { void Box() {} } Box().work(); }",
        "void run() { var callback = () { void Box() {} }; Box().work(); }",
    ],
)
def test_local_function_scope_does_not_hide_unrelated_global_constructor(tmp_path, body):
    snapshot, parsed = _snapshot(
        tmp_path,
        {"lib/main.dart": "class Box { Box(); void work() {} } " + body},
    )
    results = resolve.Resolver(snapshot, parsed).resolved_sites("lib/main.dart")
    matches = [
        result
        for result in results
        if result.site.kind is syntax.SiteKind.CALL and result.site.name == "work"
    ]
    assert len(matches) == 1
    assert matches[0].status is resolve.ResolutionStatus.RESOLVED
    assert [binding.name for binding in matches[0].bindings] == ["Box.work"]


def test_repeated_receiver_spelling_uses_the_actual_inner_call_scope(tmp_path):
    snapshot, parsed = _snapshot(
        tmp_path,
        {
            "lib/main.dart": (
                "class Box { Box(); void work() {} } "
                "void plain() { Box().work(); } "
                "void shadowed() { void Box() {} Box().work(); }"
            )
        },
    )
    results = resolve.Resolver(snapshot, parsed).resolved_sites("lib/main.dart")
    matches = {
        result.site.scope: result
        for result in results
        if result.site.kind is syntax.SiteKind.CALL and result.site.name == "work"
    }
    assert matches["plain"].status is resolve.ResolutionStatus.RESOLVED
    assert matches["shadowed"].status is not resolve.ResolutionStatus.RESOLVED
    assert not matches["shadowed"].bindings


def test_ambiguous_duplicate_receiver_facts_do_not_prove_construction(tmp_path):
    snapshot, parsed = _snapshot(
        tmp_path,
        {"lib/main.dart": "class Box { Box(); void work() {} } void run() { Box().work(); }"},
    )
    source = parsed["lib/main.dart"]
    call = next(site for site in source.sites if site.expression == "Box()")
    ambiguous = replace(source, sites=(*source.sites, call))
    resolver = resolve.Resolver(snapshot, {"lib/main.dart": ambiguous})
    results = resolver.resolved_sites("lib/main.dart")
    matches = [result for result in results if result.site.name == "work"]
    assert matches
    assert all(result.status is not resolve.ResolutionStatus.RESOLVED for result in matches)
