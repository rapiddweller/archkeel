# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the JSDoc tags of a comment that name a module (#744).

tsc 5.9.3 reads JSDoc types only in JavaScript files. This module takes the text of one comment and
says whether an `@import` tag, or `import(` in the type of a tag, is in it. It reads no syntax tree.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Final


class _JSDocType(Enum):
    """How a JSDoc tag can name a module; tsc 5.9.3 reads these only in JavaScript (#744)."""

    BRACED = "braced"
    BARE = "bare"  # The type can omit its braces.
    TEMPLATE = "template"  # A `[name=default]` also holds a type.
    IMPORT = "import"


_JSDOC_TAGS: Final = {
    "import": _JSDocType.IMPORT,
    "template": _JSDocType.TEMPLATE,
    **dict.fromkeys(
        ("type", "this", "enum", "extends", "augments", "implements", "satisfies"), _JSDocType.BARE
    ),
    **dict.fromkeys(
        (
            "return",
            "returns",
            "param",
            "arg",
            "argument",
            "prop",
            "property",
            "typedef",
            "throws",
            "exception",
        ),
        _JSDocType.BRACED,
    ),
}
# Only a `/**` comment is a JSDoc block. tsc starts a tag at `@` after whitespace or a margin
# `*`, so `a@type` is no tag.
_JSDOC_TOKEN: Final = re.compile(
    r"(?P<block>\A/\*\*)|(?<![^\s*])@(?P<tag>\w+)(?P<braced>[\s*]*\{)?"
    r"|(?P<open>\{)|(?P<close>\})|(?P<bracket>\[)|(?P<end>\])|(?P<quote>['\"`])"
    r"|(?P<call>\bimport[\s*]*\()"
)


def jsdoc_imports(body: str) -> bool:
    """An `@import` tag, or `import(` in the type of a tag; prose is no type (#744)."""
    kind: _JSDocType | None = None
    depth = 0
    # `armed`: the end of a type is not known, so any later import counts.
    armed = False
    # The quotes seen an odd number of times in the open types.
    odd: set[str] = set()
    tokens = _JSDOC_TOKEN.finditer(body)
    first = next(tokens, None)
    if first is None or first["block"] is None:
        return False
    for token in tokens:
        if token["call"] is not None:
            if armed or depth:
                return True
        elif token["tag"] is not None:
            # A tag inside an open type: a broken type, or an `@` inside a string.
            armed = armed or depth > 0
            kind = _JSDOC_TAGS.get(token["tag"])
            if kind is _JSDocType.IMPORT:
                return True
            depth = 1 if kind is not None and token["braced"] is not None else 0
            # Without braces the end of the type is not known.
            armed = armed or (kind is _JSDocType.BARE and not depth)
        elif kind is None:
            continue
        elif token["open"] is not None or (
            token["bracket"] is not None and kind is _JSDocType.TEMPLATE
        ):
            depth += 1
        elif (
            token["close"] is not None or (token["end"] is not None and kind is _JSDocType.TEMPLATE)
        ) and depth:
            depth -= 1
            # An odd quote count can put this brace or bracket inside a string.
            armed = armed or bool(odd)
        elif token["quote"] is not None and depth:
            odd ^= {token["quote"]}
    return False
