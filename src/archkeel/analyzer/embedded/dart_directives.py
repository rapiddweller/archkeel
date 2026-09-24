# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read a Dart file's directive header into typed directives (AD-97).

The grammar is the directive part of the Dart language and nothing more: `library`, `import`,
`export`, `part` and `part of`, in any order, each optionally preceded by metadata. The first
token that starts none of them ends the header. Inside it, anything else is a `DirectiveError`:
a partly read header would publish some edges and silently drop others.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, TypeAlias

from .dart_lexer import DirectiveError, Token, tokens

DirectiveKind: TypeAlias = Literal["import", "export"]


@dataclass(frozen=True, slots=True)
class Directive:
    """One `import` or `export`: every URI it may load and the names it shows, if any."""

    kind: DirectiveKind
    uris: tuple[str, ...]
    shown: tuple[str, ...]
    prefix: str | None
    line: int
    end_line: int
    column: int


@dataclass(frozen=True, slots=True)
class PartReference:
    uri: str
    line: int


@dataclass(frozen=True, slots=True)
class Header:
    directives: tuple[Directive, ...]
    parts: tuple[PartReference, ...]
    # The owner a `part of` names, a URI or a library name; None for a library.
    part_of: str | None


class _Reader:
    def __init__(self, stream: Iterator[Token]) -> None:
        self.stream = stream
        self.current = next(stream)

    def take(self) -> Token:
        token = self.current
        if token.kind != "end":
            self.current = next(self.stream)
        return token

    def at(self, text: str, kind: str = "punct") -> bool:
        return self.current.kind == kind and self.current.text == text

    def expect(self, text: str, kind: str = "punct") -> Token:
        if not self.at(text, kind):
            raise DirectiveError(self.current.line, f"expected {text!r}, found {self._shown()}")
        return self.take()

    def word(self) -> str:
        if self.current.kind != "word":
            raise DirectiveError(self.current.line, f"expected a name, found {self._shown()}")
        return self.take().text

    def dotted(self) -> str:
        parts = [self.word()]
        while self.at("."):
            self.take()
            parts.append(self.word())
        return ".".join(parts)

    def uri(self) -> str:
        """One URI: adjacent string literals concatenate, and none may interpolate."""
        if self.current.kind != "string":
            raise DirectiveError(self.current.line, f"expected a URI, found {self._shown()}")
        parts: list[str] = []
        while self.current.kind == "string":
            token = self.take()
            if token.interpolated:
                raise DirectiveError(token.line, "a URI cannot interpolate")
            parts.append(token.text)
        return "".join(parts)

    def _shown(self) -> str:
        return repr(self.current.text) if self.current.kind != "end" else "end of file"


def _skip_annotation(reader: _Reader) -> None:
    """Skip `@name`, `@name.name` and either with a balanced argument list."""
    reader.expect("@")
    reader.dotted()
    if not reader.at("("):
        return
    line = reader.current.line
    depth = 0
    while True:
        token = reader.take()
        if token.kind == "end":
            raise DirectiveError(line, "unbalanced annotation arguments")
        if token.text == "(" and token.kind == "punct":
            depth += 1
        elif token.text == ")" and token.kind == "punct":
            depth -= 1
            if depth == 0:
                return


def _alternatives(reader: _Reader) -> list[str]:
    """Each `if (dotted.name [== 'value']) 'uri'` a conditional import or export offers."""
    uris = []
    while reader.at("if", "word"):
        reader.take()
        reader.expect("(")
        reader.dotted()
        if reader.at("=="):
            reader.take()
            reader.uri()
        reader.expect(")")
        uris.append(reader.uri())
    return uris


def _combinators(reader: _Reader) -> tuple[str, ...]:
    """The names every `show` lists; `hide` narrows nothing a `show` already named (A5)."""
    shown: list[str] = []
    while reader.at("show", "word") or reader.at("hide", "word"):
        keeps = reader.take().text == "show"
        names = [reader.word()]
        while reader.at(","):
            reader.take()
            names.append(reader.word())
        if keeps:
            shown.extend(name for name in names if name not in shown)
    return tuple(shown)


def _directive(reader: _Reader, kind: DirectiveKind) -> Directive:
    keyword = reader.take()
    uris = [reader.uri(), *_alternatives(reader)]
    prefix = None
    if kind == "import":
        if reader.at("deferred", "word"):
            reader.take()
        if reader.at("as", "word"):
            reader.take()
            prefix = reader.word()
    shown = _combinators(reader)
    end = reader.expect(";")
    return Directive(kind, tuple(uris), shown, prefix, keyword.line, end.line, keyword.column)


def read_header(source: str) -> Header:
    """Parse the directive header of one Dart file, or raise `DirectiveError` with its line."""
    reader = _Reader(tokens(source))
    directives: list[Directive] = []
    parts: list[PartReference] = []
    part_of: str | None = None
    while True:
        if reader.at("@"):
            _skip_annotation(reader)
        elif reader.at("library", "word"):
            reader.take()
            if not reader.at(";"):
                reader.dotted()
            reader.expect(";")
        elif reader.at("import", "word") or reader.at("export", "word"):
            directives.append(
                _directive(reader, "import" if reader.at("import", "word") else "export")
            )
        elif reader.at("part", "word"):
            line = reader.take().line
            if reader.at("of", "word"):
                reader.take()
                part_of = reader.uri() if reader.current.kind == "string" else reader.dotted()
            else:
                parts.append(PartReference(reader.uri(), line))
            reader.expect(";")
        else:
            return Header(tuple(directives), tuple(parts), part_of)
