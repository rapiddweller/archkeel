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
