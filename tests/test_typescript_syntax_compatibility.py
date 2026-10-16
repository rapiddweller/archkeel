# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Valid legacy DTO construction reaches real collector consumers through one nominal boundary."""

import dataclasses

import pytest
from test_typescript_collect import NODE10, _facts

from archkeel.analyzer.typescript import collect as frontend
from archkeel.analyzer.typescript import parse as parser
from archkeel.analyzer.typescript import syntax
from archkeel.ir.facts_codec import encode_response
from archkeel.ir.protocol import CollectionResponse

SOURCE = (
    'import { Base } from "./base";\n'
    "export class Owner extends Base {\n"
    "  private field: number = 1;\n"
    "  public run(): number { return this.field; }\n"
    "  other(): void { this.run(); }\n"
    "}\n"
)
FILES = {"src/main.ts": SOURCE, "src/base.ts": "export class Base {}"}
FAMILIES = ("reference", "definition", "visibility", "base", "site-kind", "site-use", "receiver")


def _legacy(observed, family):
    references = tuple(
        dataclasses.replace(item, form=item.form.value) if family == "reference" else item
        for item in observed.references
    )
    definitions = tuple(
        dataclasses.replace(
            item,
            kind=item.kind.value if family == "definition" else item.kind,
            visibility=item.visibility.value
            if family == "visibility" and item.visibility is not None
            else item.visibility,
            members=tuple(
                dataclasses.replace(member, visibility=member.visibility.value)
                if family == "visibility" and member.visibility is not None
                else member
                for member in item.members
            ),
            bases=tuple(
                dataclasses.replace(base, relationship=base.relationship.value)
                if family == "base"
                else base
                for base in item.bases
            ),
        )
        for item in observed.definitions
    )
    sites = tuple(
        syntax.Site(
            **{
                field.name: (
                    item.kind.value
                    if family == "site-kind" and field.name == "kind"
                    else item.use.value
                    if family == "site-use" and field.name == "use"
                    else getattr(item, field.name)
                )
                for field in dataclasses.fields(item)
                if family != "receiver" or field.name != "receiver_kind"
            }
        )
        for item in observed.sites
    )
    return dataclasses.replace(
        observed, references=references, definitions=definitions, sites=sites
    )


@pytest.mark.parametrize("family", FAMILIES)
def test_valid_legacy_dtos_preserve_real_collector_wire_facts(tmp_path, monkeypatch, family):
    expected = _facts(tmp_path, FILES, options=NODE10)
    original_parse = frontend.parse

    def legacy_parse(rel, raw):
        return _legacy(original_parse(rel, raw), family)

    monkeypatch.setattr(frontend, "parse", legacy_parse)
    observed = _facts(tmp_path, FILES, options=NODE10)
    assert encode_response(CollectionResponse(observed)) == encode_response(
        CollectionResponse(expected)
    )


def _examples():
    observed = parser.parse("main.ts", SOURCE.encode())
    owner = next(item for item in observed.definitions if item.kind is syntax.DefinitionKind.CLASS)
    site = next(item for item in observed.sites if item.receiver == "this")
    return {
        "reference": observed.references[0],
        "definition": owner,
        "member": owner.members[0],
        "base": owner.bases[0],
        "site": site,
    }


@pytest.mark.parametrize(
    "owner, field",
    [
        ("reference", "form"),
        ("definition", "kind"),
        ("definition", "visibility"),
        ("member", "visibility"),
        ("base", "relationship"),
        ("site", "kind"),
        ("site", "use"),
        ("site", "receiver_kind"),
    ],
)
@pytest.mark.parametrize("invalid", ["unknown-control", 42, object()])
def test_invalid_closed_dto_inputs_fail_at_their_owned_constructor(owner, field, invalid):
    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(_examples()[owner], **{field: invalid})


@pytest.mark.parametrize(
    "receiver, expected",
    [
        (None, syntax.ReceiverKind.NONE),
        ("", syntax.ReceiverKind.OTHER),
        ("this", syntax.ReceiverKind.THIS),
        ("THIS", syntax.ReceiverKind.OTHER),
        ("owner", syntax.ReceiverKind.OTHER),
    ],
)
def test_omitted_receiver_kind_preserves_legacy_receiver_semantics(receiver, expected):
    item = syntax.Site(
        syntax.SiteKind.REFERENCE,
        "value",
        syntax.Span(1, 1, 1, "value"),
        None,
        None,
        receiver=receiver,
    )
    assert item.receiver_kind is expected


def test_explicit_unknown_parser_receiver_never_becomes_known_this():
    item = syntax.Site(
        syntax.SiteKind.REFERENCE,
        "this.value",
        syntax.Span(1, 1, 1, "this.value"),
        None,
        None,
        receiver="this",
        receiver_kind=syntax.ReceiverKind.OTHER,
    )
    assert item.receiver_kind is syntax.ReceiverKind.OTHER


def test_normalized_dtos_stay_frozen_and_data_names_stay_strings():
    member = syntax.Member("class", syntax.Span(1, 1, 1, "class"), "interface", "private", False)
    assert member.visibility is syntax.Visibility.PRIVATE
    assert member.name == "class" and member.annotation == "interface"
    with pytest.raises(dataclasses.FrozenInstanceError):
        member.visibility = syntax.Visibility.PUBLIC
