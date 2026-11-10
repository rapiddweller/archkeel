# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Rust tokenizer and the test-file rule that `rust_clones.py` and `rust_api.py` share (AD-327).

The tokenizer drops comments (a block comment may nest) and white space. It keeps a string, a raw
string, a byte string and a character as one literal token, and a lifetime as one name token.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

TOKEN = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<line_comment>//[^\n]*)
  | (?P<block_comment>/\*)
  | (?P<literal>b?r(?P<hashes>\#*)".*?"(?P=hashes)
        |b?"(?:\\.|[^"\\])*"
        |b?'(?:\\(?:u\{[^}]*\}|x[0-9a-fA-F]{2}|.)|[^\\'\n])'
        |\d\w*(?:\.\d\w*)?)
  | (?P<name>[A-Za-z_]\w*|'[A-Za-z_]\w*)
  | (?P<punct>.)
    """,
    re.S | re.X,
)
CFG_TEST_MODULE = re.compile(
    r"#\[cfg\((?:test|any\(test)[^\]]*\]\s*((?:#\[[^\]]*\]\s*)*)(?:pub\s+)?mod\s+(\w+)\s*;"
)
PATH_STEM = re.compile(r'#\[path\s*=\s*"(?:[^"]*/)?(\w+)\.rs"\]')
TEST_DIRECTORIES = frozenset({"tests", "benches", "examples"})


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    line: int
    kind: str  # "name", "literal" or "punct"


def _block_comment_end(text: str, start: int) -> int:
    """Return the index after the block comment that opens at `start`; it may nest."""
    depth, position = 0, start
    while position < len(text):
        pair = text[position : position + 2]
        if pair == "/*":
            depth, position = depth + 1, position + 2
        elif pair == "*/":
            depth, position = depth - 1, position + 2
            if depth == 0:
                return position
        else:
            position += 1
    return len(text)


def tokenize(text: str) -> list[Token]:
    """Return the tokens of Rust text without comments and white space."""
    tokens: list[Token] = []
    position, line = 0, 1
    while position < len(text):
        match = TOKEN.match(text, position)
        if match is None:  # `.` with DOTALL matches any character, so this does not happen
            break
        kind = match.lastgroup
        end = match.end()
        if kind == "block_comment":
            end = _block_comment_end(text, position)
        elif kind in {"literal", "name", "punct"}:
            tokens.append(Token(match.group(), line, kind))
        line += text.count("\n", position, end)
        position = end
    return tokens


def group_end(tokens: Sequence[Token], at: int) -> int:
    """Return the index after the bracket group that opens at `at`; `(`, `[` and `{` all count."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    for position in range(at, len(tokens)):
        text = tokens[position].text
        if tokens[position].kind == "punct" and text in pairs:
            stack.append(pairs[text])
        elif tokens[position].kind == "punct" and stack and text == stack[-1]:
            stack.pop()
            if not stack:
                return position + 1
    return len(tokens)


def item_end(tokens: Sequence[Token], start: int) -> int:
    """Return the index after the item that starts at `start`: its `;`, or its last `}`.

    A `}` that a `;` follows, as in `const X: u8 = { 1 };`, includes that `;`. A brace that
    an expression continues after, as in `{ 1 } + 2;`, ends the item too early.
    """
    position = start
    while position < len(tokens):
        token = tokens[position]
        if token.kind == "punct" and token.text == ";":
            return position + 1
        if token.kind == "punct" and token.text in {"(", "[", "{"}:
            opened = token.text
            position = group_end(tokens, position)
            if opened == "{":
                if position < len(tokens) and tokens[position].text == ";":
                    position += 1
                return position
        else:
            position += 1
    return len(tokens)


def _is_cfg_test(tokens: Sequence[Token], start: int, end: int) -> bool:
    """Whether the attribute tokens[start:end] is `#[cfg(test)]` or `#[cfg(any(test, ...))]`."""
    words = [token.text for token in tokens[start:end]]
    return words[:5] == ["#", "[", "cfg", "(", "test"] or words[:7] == [
        "#",
        "[",
        "cfg",
        "(",
        "any",
        "(",
        "test",
    ]


def inline_test_mask(tokens: Sequence[Token]) -> list[bool]:
    """Mark the tokens of each `#[cfg(test)]` item, from its attribute to the item's end.

    The item is a `mod name { ... }`, or any other item up to its `;` or its last `}` (see
    `item_end`). The braces are balanced on tokens, so a brace in a string or a comment does not
    count.
    """
    mask = [False] * len(tokens)
    at = 0
    while at < len(tokens):
        if tokens[at].text != "#" or at + 1 >= len(tokens) or tokens[at + 1].text != "[":
            at += 1
            continue
        end = group_end(tokens, at + 1)
        if not _is_cfg_test(tokens, at, end):
            at += 1
            continue
        position = end
        while position < len(tokens) and tokens[position].text == "#":
            position = group_end(tokens, position + 1)  # more attributes
        if position < len(tokens) and tokens[position].text == "pub":
            position += 1
            if position < len(tokens) and tokens[position].text == "(":
                position = group_end(tokens, position)
        names = [token.text for token in tokens[position : position + 3]]
        if len(names) == 3 and names[0] == "mod" and names[2] == "{":
            stop = group_end(tokens, position + 2)
        else:
            stop = item_end(tokens, position)
        mask[at:stop] = [True] * (stop - at)
        at = stop
    return mask


def test_files(sources: Mapping[str, str]) -> frozenset[str]:
    """Return the files that only a test build uses; the keys are paths with `/`.

    A test file is one of these: a name that ends in `_tests` or is `tests`; a file under a
    `tests`, `benches` or `examples` directory; a file that its parent declares as a module
    behind `#[cfg(test)]`. A name such as `test_support.rs` is production code until its
    declaration says otherwise.
    """
    found: set[str] = set()
    declared: dict[str, set[str]] = {}
    for name, text in sources.items():
        for match in CFG_TEST_MODULE.finditer(text):
            stems = {match.group(2), *PATH_STEM.findall(match.group(1))}
            declared.setdefault(str(Path(name).parent), set()).update(stems)
    for name in sources:
        path = Path(name)
        if (
            path.stem == "tests"
            or path.stem.endswith("_tests")
            or TEST_DIRECTORIES.intersection(path.parts[:-1])
            or path.stem in declared.get(str(path.parent), ())
        ):
            found.add(name)
    return frozenset(found)


def read_sources(root: Path) -> dict[str, str]:
    """Return the text of each `.rs` file under `root`, except `target/`, by relative path."""
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*.rs"))
        if "target" not in path.relative_to(root).parts
    }
