# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Rust tokenizer and the test-file rule that `rust_clones.py` and `rust_api.py` share (AD-327).

The tokenizer drops comments (a block comment may nest) and white space. It keeps a string, a raw
string, a byte string and a character as one literal token, and a lifetime as one name token.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
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
