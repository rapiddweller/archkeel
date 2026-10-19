# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reuse fixed syntax scans while mutable import and member evidence stays live."""


def test_member_containment_closure_visits_each_edge_once() -> None:
    from archkeel.analyzer.python.source import member_binding_closure

    class CountedEdges(set[tuple[str, str]]):
        visits = 0

        def __iter__(self):
            for edge in super().__iter__():
                self.visits += 1
                yield edge

    edges = CountedEdges((f"item{i}", f"item{i + 1}") for i in range(128))
    assert member_binding_closure((), {"item0"}, member_surface=True, contained=edges) == {
        f"item{i}" for i in range(129)
    }
    assert edges.visits == len(edges)
    edges.visits = 0
    assert member_binding_closure((), set(), member_surface=True, contained=edges) == set()
    assert edges.visits == 0


def test_namespace_fanout_expands_once_when_an_owner_is_reached_transitively() -> None:
    from archkeel.analyzer.python.source import member_binding_closure

    class CountedNames(set[str]):
        visits = 0

        def __iter__(self):
            for name in super().__iter__():
                self.visits += 1
                yield name

    namespace = CountedNames(f"value{i}" for i in range(256))
    result = member_binding_closure(
        (),
        {"root"},
        member_surface=True,
        contained={("root", "Owner"), ("value0", "tail")},
        namespace_owners={"Owner", *namespace},
        namespace_bindings=namespace,
    )
    assert namespace.visits == len(namespace)
    assert result == {"root", "Owner", "tail", *namespace}


def test_namespace_fanout_keeps_direction_and_empty_roots() -> None:
    from archkeel.analyzer.python.source import member_binding_closure

    for roots in (set(), {"value"}):
        assert (
            member_binding_closure(
                (),
                roots,
                member_surface=True,
                namespace_owners={"Owner"},
                namespace_bindings={"value"},
            )
            == roots
        )


def test_namespace_fanout_matches_materialized_edges() -> None:
    import ast
    import random

    from archkeel.analyzer.python.source import member_binding_closure

    randomizer = random.Random(604)
    names = [f"value{i}" for i in range(12)]
    nodes = tuple(ast.walk(ast.parse("value1 = value0\nvalue3 = value2.member\n")))
    for _ in range(120):
        roots, owners, namespace = (
            {name for name in names if randomizer.randrange(4) == 0} for _ in range(3)
        )
        edges = {
            (owner, value) for owner in names for value in names if randomizer.randrange(20) == 0
        }
        for member_surface in (False, True):
            assert member_binding_closure(
                nodes,
                roots,
                member_surface=member_surface,
                contained=edges,
                namespace_owners=owners,
                namespace_bindings=namespace,
            ) == member_binding_closure(
                nodes,
                roots,
                member_surface=member_surface,
                contained=edges | {(owner, value) for owner in owners for value in namespace},
            )


def test_plain_name_spelling_avoids_repeated_unparsing() -> None:
    import ast
    from unittest.mock import patch

    from archkeel.analyzer.python.source import annotation_text

    nodes = [
        ast.Name(id=name, ctx=context())
        for name in ("Client", "_private", "é", "类")
        for context in (ast.Load, ast.Store, ast.Del)
    ]
    expected = [ast.unparse(node) for node in nodes]
    with patch("archkeel.analyzer.python.source.ast.unparse", wraps=ast.unparse) as unparse:
        assert [annotation_text(node) for node in nodes] == expected
        unparse.assert_not_called()


def test_name_spelling_keeps_alias_resolution_live() -> None:
    import ast

    from test_analyzer import _parsed_module

    from archkeel.analyzer.python.binding_types import AliasBinding, ImportKind
    from archkeel.analyzer.python.source import resolve_static_name

    module = _parsed_module("Client\n")
    node = ast.parse("Client", mode="eval").body
    assert resolve_static_name(module, node) == "Client"
    module.aliases["Client"] = AliasBinding("first.Client", ImportKind.SYMBOL)
    assert resolve_static_name(module, node) == "first.Client"
    module.aliases["Client"] = AliasBinding("second.Client", ImportKind.SYMBOL)
    assert resolve_static_name(module, node) == "second.Client"
    module.aliases.clear()
    assert resolve_static_name(module, node) == "Client"


def test_complex_spelling_keeps_stdlib_formatting_and_failure() -> None:
    import ast
    from unittest.mock import patch

    from archkeel.analyzer.python.source import annotation_text

    class DerivedName(ast.Name):
        pass

    nodes = [ast.parse(text, mode="eval").body for text in ("pkg.Client", "A | None", "list[A]")]
    nodes.append(DerivedName(id="Client", ctx=ast.Load()))
    expected = [ast.unparse(node) for node in nodes]
    with patch("archkeel.analyzer.python.source.ast.unparse", wraps=ast.unparse) as unparse:
        assert [annotation_text(node) for node in nodes] == expected
        assert unparse.call_count == len(nodes)
    with patch("archkeel.analyzer.python.source.ast.unparse", side_effect=ValueError):
        assert annotation_text(nodes[0]) is None
    assert annotation_text(None) is None


def test_namespace_scan_is_reused_without_caching_mutable_member_proofs() -> None:
    from unittest.mock import patch

    from test_analyzer import _parsed_module

    from archkeel.analyzer.python.binding_types import AliasBinding, ImportKind
    from archkeel.analyzer.python.source import (
        exposes_dynamic_namespace,
        unproven_member_bindings,
    )

    module = _parsed_module("marker = 1\nprobe()\n")
    with patch(
        "archkeel.analyzer.python.source.exposes_dynamic_namespace",
        wraps=exposes_dynamic_namespace,
    ) as scan:
        initial = unproven_member_bindings(module)
        assert "marker" not in initial
        initial_visits = scan.call_count
        module.incoming_member_escapes.add("marker")
        assert unproven_member_bindings(module) == initial | {"marker"}
        module.incoming_member_escapes.clear()
        assert unproven_member_bindings(module) == initial
        assert scan.call_count == initial_visits

        module.aliases["probe"] = AliasBinding("builtins.globals", ImportKind.SYMBOL)
        assert unproven_member_bindings(module) == frozenset(module.bound_names)
        assert scan.call_count > initial_visits
        module.aliases.clear()
        assert unproven_member_bindings(module) == initial

    fresh = _parsed_module("class Other: pass\nglobals()\n")
    assert unproven_member_bindings(fresh) == {"Other"}
