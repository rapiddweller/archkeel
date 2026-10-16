# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The parser publishes one owned nominal syntax port, never raw control strings."""

from enum import Enum
from typing import get_args, get_type_hints

import pytest

from archkeel.analyzer.typescript import parse as parser


@pytest.mark.parametrize(
    ("owner", "field", "optional"),
    [
        (parser.Reference, "form", False),
        (parser.Definition, "kind", False),
        (parser.Definition, "visibility", True),
        (parser.Member, "visibility", True),
        (parser.Base, "relationship", False),
        (parser.Site, "kind", False),
        (parser.Site, "use", False),
        (parser.Site, "receiver_kind", False),
    ],
)
def test_semantic_control_fields_are_owned_nominal_enums(owner, field, optional):
    hint = get_type_hints(owner)[field]
    domain = next(item for item in get_args(hint) if item is not type(None)) if optional else hint
    assert isinstance(domain, type) and issubclass(domain, Enum)
    assert not issubclass(domain, str)
    assert domain.__module__ == "archkeel.analyzer.typescript.syntax"


@pytest.mark.parametrize(
    "owner",
    [
        parser.Span,
        parser.Reference,
        parser.Concern,
        parser.Parameter,
        parser.Member,
        parser.Base,
        parser.Definition,
        parser.Site,
        parser.ImportBinding,
        parser.Syntax,
    ],
)
def test_existing_dtos_are_moved_to_one_syntax_owner_without_copies(owner):
    assert owner.__module__ == "archkeel.analyzer.typescript.syntax"


def test_unknown_member_kind_does_not_create_a_complete_inventory(monkeypatch):
    monkeypatch.delitem(parser._NODE_KINDS, "method_definition")
    observed = parser.parse("main.ts", b"class Owner { run(): void {} }")
    (owner,) = observed.definitions
    assert owner.kind is parser.DefinitionKind.CLASS
    assert owner.members_complete is False


def test_unknown_receiver_kind_does_not_infer_this_from_its_spelling(monkeypatch):
    monkeypatch.delitem(parser._NODE_KINDS, "this")
    observed = parser.parse("main.ts", b"class Owner { field = 1; run() { this.field; } }")
    site = next(item for item in observed.sites if item.receiver == "this")
    assert site.receiver_kind is parser.ReceiverKind.OTHER


def test_each_raw_node_kind_is_decoded_once_per_parse_identity(monkeypatch):
    raw = parser.Parser(parser._grammar(parser._Grammar.TYPESCRIPT)).parse(b"class A {}").root_node
    tree = parser._Tree()
    first = tree.node(raw.named_children[0])
    monkeypatch.delitem(parser._NODE_KINDS, "class_declaration")
    assert tree.node(raw.named_children[0]) is first
    assert first.kind is parser._NodeKind.CLASS_DECLARATION
    assert parser._Tree().node(raw.named_children[0]).kind is None


@pytest.mark.parametrize("failed", [False, True], ids=["success", "exception"])
def test_parse_releases_its_node_identity_cache_on_every_exit(monkeypatch, failed):
    trees = []
    original_init = parser._Tree.__init__

    def track(tree):
        original_init(tree)
        trees.append(tree)

    def stop(source):
        raise RuntimeError("decoder stopped")

    monkeypatch.setattr(parser._Tree, "__init__", track)
    if failed:
        monkeypatch.setattr(parser, "_inner", stop)
        with pytest.raises(RuntimeError, match="decoder stopped"):
            parser.parse("sample.ts", b"class A {}")
    else:
        parser.parse("sample.ts", b"class A {}")
    assert len(trees) == 1
    assert not trees[0].nodes


@pytest.mark.parametrize(
    "member",
    [b"run(): void {}", b"constructor(public value: string) {}"],
    ids=["method", "constructor"],
)
def test_unknown_member_name_kind_cannot_certify_named_inventory(monkeypatch, member):
    monkeypatch.delitem(parser._NODE_KINDS, "property_identifier")
    observed = parser.parse("main.ts", b"class Owner { " + member + b" }")
    owner = next(item for item in observed.definitions if item.kind is parser.DefinitionKind.CLASS)
    assert owner.members_complete is False
    assert not any(item.kind is parser.DefinitionKind.METHOD for item in observed.definitions)
