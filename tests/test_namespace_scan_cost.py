# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reuse fixed syntax scans while mutable import and member evidence stays live."""


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


def test_opaque_import_reuses_alias_candidates_with_fresh_local_references() -> None:
    from unittest.mock import patch

    from test_analyzer import _parsed_module

    from archkeel.analyzer.python import imports, source
    from archkeel.analyzer.python.binding_types import AliasBinding, ImportKind

    module = _parsed_module(
        "from opaque import Base\nAlias = Base\nclass Consumer(Alias): pass\n" + "0\n" * 400
    )
    module.aliases["Base"] = AliasBinding("opaque.Base", ImportKind.SYMBOL)
    local_name = module.tree.body[1].value
    record = {
        "source_binding_unique": False,
        "origin_definition": "opaque.Base",
        "binding": "Base",
        "symbol": None,
    }
    with (
        patch.object(
            imports, "member_binding_closure", wraps=source.member_binding_closure
        ) as call,
        patch.object(
            imports,
            "setter_local_references",
            side_effect=[frozenset(), frozenset({local_name})],
        ),
    ):
        assert imports._opaque_import_member_escapes(
            record, module, owner_exposure_only=True, unsafe_providers=frozenset()
        ) == {"Consumer"}
        assert (
            imports._opaque_import_member_escapes(
                record, module, owner_exposure_only=True, unsafe_providers=frozenset()
            )
            == set()
        )
    first, second = (item.args[0] for item in call.call_args_list)
    assert first is second and len(first) == 1
