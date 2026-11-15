# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The fragments of a `macro_rules!` matcher: where each one ends in the tokens of a call.

`fragment` returns the end of the fragment of one kind that starts at a place, and raises
`Unreadable` when none starts there. The kinds are `ident`, `vis`, `meta`, `ty`, `tt`, `path`,
`literal`, `lifetime`, `block`, `expr` and `item`.
"""

from __future__ import annotations

from collections.abc import Sequence

from rust_source import Token, group_end

OPEN = {"(": ")", "[": "]", "{": "}"}
TYPE_END = frozenset({",", ";", "=", "|", "{"})


class Unreadable(Exception):
    """A matcher, a transcriber or a call that this reader does not read."""


def fragment(kind: str, tokens: Sequence[Token], at: int) -> int:
    """Return the end of the fragment of `kind` that starts at `at`; raise when none starts."""
    if at > len(tokens) or (at == len(tokens) and kind != "vis"):
        raise Unreadable("the call ends early")
    here = tokens[at] if at < len(tokens) else None
    if kind == "ident":
        if here is None or here.kind != "name" or here.text.startswith("'"):
            raise Unreadable("no identifier")
        raw = [t.text for t in tokens[at + 1 : at + 3]]
        return at + 3 if here.text == "r" and raw[:1] == ["#"] and len(raw) == 2 else at + 1
    if kind == "lifetime":
        if here is None or not here.text.startswith("'"):
            raise Unreadable("no lifetime")
        return at + 1
    if kind == "literal":
        if here is None or here.kind != "literal":
            raise Unreadable("no literal")
        return at + 1
    if kind == "vis":
        if here is None or here.text != "pub":
            return at
        group = tokens[at + 1 : at + 2]
        return group_end(tokens, at + 1) if group and group[0].text == "(" else at + 1
    if kind == "tt":
        return group_end(tokens, at) if here and here.text in OPEN else at + 1
    if kind == "block":
        if here is None or here.text != "{":
            raise Unreadable("no block")
        return group_end(tokens, at)
    if kind == "meta" or kind == "path":
        return _path(tokens, at, kind == "meta")
    return _extent(tokens, at, kind)


def _path(tokens: Sequence[Token], at: int, meta: bool) -> int:
    position = at
    while position < len(tokens) and tokens[position].kind == "name":
        position += 1
        if tokens[position : position + 2] and [
            t.text for t in tokens[position : position + 2]
        ] == [":", ":"]:
            position += 2
        else:
            break
    if position == at:
        raise Unreadable("no path")
    if meta and position < len(tokens):
        if tokens[position].text in OPEN:
            return group_end(tokens, position)
        if tokens[position].text == "=":
            return _extent(tokens, position + 1, "expr")
    return position


def _extent(tokens: Sequence[Token], at: int, kind: str) -> int:
    """The end of a `ty`, `expr` or `item`: up to a stop token outside every group."""
    if kind == "item":
        position = at
        while position < len(tokens):
            text = tokens[position].text
            if text == ";":
                return position + 1
            if text in OPEN:
                end = group_end(tokens, position)
                if text == "{":
                    return end
                position = end
            else:
                position += 1
        return position
    stops = TYPE_END if kind == "ty" else frozenset({",", ";"})
    angle, position = 0, at
    while position < len(tokens):
        token = tokens[position]
        if token.text in OPEN and token.kind == "punct" and (kind != "ty" or token.text != "{"):
            position = group_end(tokens, position)
            continue
        if kind == "ty" and token.text == "<":
            angle += 1
        elif kind == "ty" and token.text == ">" and tokens[position - 1].text != "-":
            angle -= 1
        elif angle <= 0 and token.text in stops:
            break
        elif (
            token.text == "="
            and tokens[position + 1 : position + 2]
            and tokens[position + 1].text == ">"
        ):
            break
        position += 1
    if position == at:
        raise Unreadable(f"no {kind}")
    return position
