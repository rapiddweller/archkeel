# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Token runs of Rust code that carry no logic: the clone check skips them (AD-584).

The clone check exists to find duplicated logic. Three kinds of item repeat without logic, so
two of them that look alike are no clone:

- a `use` item: an import list names things, it computes nothing;
- a `const` or `static` whose value is an array or a slice of literals and paths, with tuples of
  them and no call, no operator and no block: a table of data;
- a `mod name;` declaration, and a struct of named fields that have plain types (a `pub(crate)`
  visibility is allowed): a declaration of names and types;
- a declaration macro (`closed! { pub enum E { A = "a", } }`) whose body is names, literals and
  brackets, each `=` followed by a literal;
- a `match` in which each arm is `path => literal` (or a tuple of literals) or
  `literal => path`, with no guard and no other expression: a table of words and variants.

Each rule is strict. A call, an operator, a block, a guard or a second expression in the item
makes it logic again, and logic in the same file stays visible to the check.
"""

from __future__ import annotations

from collections.abc import Sequence

from rust_source import Token, group_end

TABLE_PUNCT = frozenset({",", ":", "(", ")", "[", "]", "&", "-"})
PATTERN_PUNCT = frozenset({":", "|"})


def inert_mask(tokens: Sequence[Token]) -> list[bool]:
    """Return, for each token, whether it is in an import, a data table or a word table."""
    mask = [False] * len(tokens)
    for start, token in enumerate(tokens):
        if token.kind != "name":
            continue
        end = None
        if token.text == "use":
            end = _use_end(tokens, start)
        elif token.text in {"const", "static"}:
            end = _table_end(tokens, start)
        elif token.text == "match":
            end = _match_end(tokens, start)
        elif token.text == "mod":
            end = _mod_end(tokens, start)
        elif token.text == "struct":
            first = _struct_start(tokens, start)
            end = _struct_end(tokens, start)
            if end is not None:
                mask[first:start] = [True] * (start - first)
        elif start + 1 < len(tokens) and _is(tokens[start + 1], "!"):
            end = _words_end(tokens, start)
        if end is not None:
            mask[start:end] = [True] * (end - start)
    return mask


def _is(token: Token, text: str) -> bool:
    return token.kind == "punct" and token.text == text


def _use_end(tokens: Sequence[Token], start: int) -> int | None:
    """Return the index after the `;` of the `use` item that starts at `start`."""
    depth = 0
    for position in range(start + 1, len(tokens)):
        token = tokens[position]
        if token.kind == "punct" and token.text == "{":
            depth += 1
        elif token.kind == "punct" and token.text == "}":
            depth -= 1
            if depth < 0:
                return None
        elif depth == 0 and _is(token, ";"):
            return position + 1
    return None


def _table_end(tokens: Sequence[Token], start: int) -> int | None:
    """Return the index after a `const` or `static` that is an array or slice of plain values."""
    if start + 1 < len(tokens) and tokens[start + 1].text in {"fn", "unsafe", "async"}:
        return None
    position = start + 1
    while position < len(tokens) and not _is(tokens[position], "="):
        if _is(tokens[position], ";") or _is(tokens[position], "{"):
            return None
        position = group_end(tokens, position) if _opens(tokens[position]) else position + 1
    position += 1
    if position < len(tokens) and _is(tokens[position], "&"):
        position += 1
    if position >= len(tokens) or not _is(tokens[position], "["):
        return None
    end = group_end(tokens, position)
    if end >= len(tokens) or not _is(tokens[end], ";") or not _plain(tokens[position:end]):
        return None
    return end + 1


def _opens(token: Token) -> bool:
    return token.kind == "punct" and token.text in {"(", "[", "{"}


def _plain(tokens: Sequence[Token]) -> bool:
    """Whether the tokens are only literals, paths, commas, tuples and nested arrays."""
    for index, token in enumerate(tokens):
        if token.kind == "literal":
            continue
        if token.kind == "name":
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            if following is not None and _is(following, "("):
                return False  # a call
            continue
        if token.text not in TABLE_PUNCT:
            return False
    return True


def _match_end(tokens: Sequence[Token], start: int) -> int | None:
    """Return the index after a `match` whose arms are all `path => literal` or the reverse."""
    position = start + 1
    while position < len(tokens) and not _is(tokens[position], "{"):
        if _is(tokens[position], ";") or _is(tokens[position], "}"):
            return None
        position = group_end(tokens, position) if _opens(tokens[position]) else position + 1
    if position >= len(tokens):
        return None
    end = group_end(tokens, position)
    body = tokens[position + 1 : end - 1]
    return end if _arms(body) else None


def _arms(body: Sequence[Token]) -> bool:
    """Whether the arms of a match body are plain: a path and a literal, in either order."""
    index, count = 0, 0
    while index < len(body):
        arrow = _arrow(body, index)
        if arrow is None:
            return False
        pattern = body[index:arrow]
        stop = arrow + 2
        depth = 0
        while stop < len(body) and not (depth == 0 and _is(body[stop], ",")):
            depth += _is(body[stop], "(") - _is(body[stop], ")")
            stop += 1
        value = body[arrow + 2 : stop]
        if not _arm(pattern, value):
            return False
        index, count = stop + 1, count + 1
    return count > 0


def _arrow(body: Sequence[Token], index: int) -> int | None:
    for position in range(index, len(body) - 1):
        if _is(body[position], "=") and _is(body[position + 1], ">"):
            return position
        if body[position].kind == "name" and body[position].text in {"if", "match", "let"}:
            return None
    return None


def _arm(pattern: Sequence[Token], value: Sequence[Token]) -> bool:
    """A path pattern with a literal value, or literal patterns with a path value."""
    wildcard = len(pattern) == 1 and pattern[0].text == "_"
    if wildcard:
        return _literal(value) or _path(value, or_allowed=False)
    return (_path(pattern, or_allowed=True) and _literal(value)) or (
        _literals(pattern) and _path(value, or_allowed=False)
    )


def _path(tokens: Sequence[Token], *, or_allowed: bool) -> bool:
    """Whether the tokens are names joined by `::`, and by `|` when allowed."""
    if not tokens or tokens[0].kind != "name":
        return False
    for token in tokens:
        if token.kind == "name":
            continue
        if token.kind != "punct" or token.text not in (PATTERN_PUNCT if or_allowed else {":"}):
            return False
    return True


def _literal(tokens: Sequence[Token]) -> bool:
    """A literal, or a tuple of literals: the value of one word."""
    if len(tokens) == 1:
        return tokens[0].kind == "literal"
    inside = tokens[1:-1]
    return (
        len(tokens) > 2
        and _is(tokens[0], "(")
        and _is(tokens[-1], ")")
        and all(token.kind == "literal" or _is(token, ",") for token in inside)
    )


def _literals(tokens: Sequence[Token]) -> bool:
    return bool(tokens) and all(
        token.kind == "literal" or (token.kind == "punct" and token.text == "|") for token in tokens
    )


def _mod_end(tokens: Sequence[Token], start: int) -> int | None:
    """Return the index after `mod name;`."""
    if (
        start + 3 < len(tokens) + 0
        and tokens[start + 1].kind == "name"
        and _is(tokens[start + 2], ";")
    ):
        return start + 3
    return None


def _struct_start(tokens: Sequence[Token], start: int) -> int:
    """Return the index of the first attribute or visibility before the `struct` at `start`."""
    first = start
    if first > 0 and tokens[first - 1].text == "pub":
        first -= 1
    elif first > 0 and _is(tokens[first - 1], ")"):
        opener = first - 1
        while opener > 0 and not _is(tokens[opener], "("):
            opener -= 1
        if opener > 0 and tokens[opener - 1].text == "pub":
            first = opener - 1
    while first > 0 and _is(tokens[first - 1], "]"):
        depth, position = 0, first - 1
        while position >= 0:
            depth += _is(tokens[position], "]") - _is(tokens[position], "[")
            if depth == 0:
                break
            position -= 1
        if position < 1 or not _is(tokens[position - 1], "#"):
            break
        first = position - 1
    return first


def _struct_end(tokens: Sequence[Token], start: int) -> int | None:
    """Return the index after a struct whose fields are `[pub(..)] name: plain type`."""
    if start + 2 >= len(tokens) or not _is(tokens[start + 2], "{"):
        return None
    end = group_end(tokens, start + 2)
    body = tokens[start + 3 : end - 1]
    index = 0
    while index < len(body):
        token = body[index]
        if token.kind == "name" and token.text == "pub" and index + 1 < len(body):
            if _is(body[index + 1], "("):
                # A visibility `pub(crate)`, `pub(super)` or `pub(in path)` computes nothing.
                index = group_end(body, index + 1)
                continue
        if token.kind == "literal":
            return None
        if token.kind == "punct" and token.text not in {
            ",",
            ":",
            "<",
            ">",
            "&",
            "'",
            "[",
            "]",
            ";",
        }:
            return None
        if token.kind == "name" and index + 1 < len(body) and _is(body[index + 1], "("):
            return None
        index += 1
    return end


def _words_end(tokens: Sequence[Token], start: int) -> int | None:
    """Return the index after a declaration macro whose body is only words."""
    opener = start + 2
    if opener >= len(tokens) or not _opens(tokens[opener]):
        return None
    end = group_end(tokens, opener)
    body = tokens[opener + 1 : end - 1]
    equals = 0
    for index, token in enumerate(body):
        if _is(token, "="):
            equals += 1
            if index + 1 >= len(body) or body[index + 1].kind != "literal":
                return None
        elif token.kind == "punct" and token.text not in {",", "{", "}", ":", "(", ")"}:
            if not _is(token, "="):
                return None
        elif token.kind == "name" and index + 1 < len(body) and _is(body[index + 1], "("):
            return None
    if equals == 0:
        return None
    if end < len(tokens) and _is(tokens[end], ";"):
        end += 1
    return end
