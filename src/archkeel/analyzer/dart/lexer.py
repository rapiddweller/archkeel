# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Tokenize exactly as much Dart as a file's directive header needs (AD-97).

Tokens are produced lazily: the directive reader stops at the first declaration, so nothing
after the header is ever tokenized, and an `import`-looking string in a later function body
cannot become an edge. What the header holds but this reader cannot read is an error with a
line, never a guess.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

TokenKind: TypeAlias = Literal["word", "string", "punct", "end"]

_WORD_CHARACTERS: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)
_IDENTIFIER_START: Final = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")


@dataclass
class DirectiveError(ValueError):
    """The header holds something this reader cannot decide; the file is not observed."""

    line: int
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    text: str
    line: int
    column: int
    # A string whose value depends on `$name` or `${...}`: a URI may not interpolate.
    interpolated: bool = False


class _Cursor:
    def __init__(self, source: str) -> None:
        self.source = source
        self.offset = 0
        self.line = 1
        self.line_start = 0

    def peek(self, ahead: int = 0) -> str:
        index = self.offset + ahead
        return self.source[index] if index < len(self.source) else ""

    def looking_at(self, text: str) -> bool:
        return self.source.startswith(text, self.offset)

    def advance(self, count: int = 1) -> str:
        taken = self.source[self.offset : self.offset + count]
        for character in taken:
            self.offset += 1
            if character == "\n":
                self.line += 1
                self.line_start = self.offset
        return taken


def _skip_block_comment(cursor: _Cursor) -> None:
    """Skip `/* ... */`, which nests in Dart: `/* a /* b */ c */` is one comment."""
    line = cursor.line
    depth = 0
    while True:
        if cursor.looking_at("/*"):
            depth += 1
            cursor.advance(2)
        elif cursor.looking_at("*/"):
            depth -= 1
            cursor.advance(2)
            if depth == 0:
                return
        elif not cursor.peek():
            raise DirectiveError(line, "unterminated block comment")
        else:
            cursor.advance()


def _skip_trivia(cursor: _Cursor) -> None:
    while True:
        character = cursor.peek()
        if character in (" ", "\t", "\r", "\n", "﻿"):
            cursor.advance()
        elif cursor.looking_at("//"):
            while cursor.peek() not in ("", "\n"):
                cursor.advance()
        elif cursor.looking_at("/*"):
            _skip_block_comment(cursor)
        else:
            return


def _string(cursor: _Cursor, *, raw: bool) -> tuple[str, bool]:
    """Read one string literal after its optional `r`; return its value and interpolation."""
    line = cursor.line
    quote = cursor.peek()
    delimiter = quote * 3 if cursor.looking_at(quote * 3) else quote
    cursor.advance(len(delimiter))
    value: list[str] = []
    interpolated = False
    while not cursor.looking_at(delimiter):
        character = cursor.peek()
        if not character or (character == "\n" and len(delimiter) == 1):
            raise DirectiveError(line, "unterminated string literal")
        if character == "\\" and not raw:
            cursor.advance()
            value.append(cursor.advance())
            continue
        if (
            character == "$"
            and not raw
            and (cursor.peek(1) == "{" or cursor.peek(1) in _IDENTIFIER_START)
        ):
            interpolated = True
        value.append(cursor.advance())
    cursor.advance(len(delimiter))
    return "".join(value), interpolated


def tokens(source: str) -> Iterator[Token]:
    """Yield the tokens of `source` on demand, skipping comments and a leading `#!` line."""
    cursor = _Cursor(source)
    if cursor.looking_at("#!"):
        while cursor.peek() not in ("", "\n"):
            cursor.advance()
    while True:
        _skip_trivia(cursor)
        line, column = cursor.line, cursor.offset - cursor.line_start
        character = cursor.peek()
        if not character:
            yield Token("end", "", line, column)
            return
        raw = character == "r" and cursor.peek(1) in ("'", '"')
        if raw or character in ("'", '"'):
            cursor.advance(1 if raw else 0)
            value, interpolated = _string(cursor, raw=raw)
            yield Token("string", value, line, column, interpolated)
        elif character in _WORD_CHARACTERS:
            start = cursor.offset
            while cursor.peek() and cursor.peek() in _WORD_CHARACTERS:
                cursor.advance()
            yield Token("word", source[start : cursor.offset], line, column)
        elif cursor.looking_at("=="):
            yield Token("punct", cursor.advance(2), line, column)
        else:
            yield Token("punct", cursor.advance(), line, column)
