# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Count the public API of each Rust library crate and ratchet the counts (AD-327).

A library crate of `native/` has `src/lib.rs`. Each one must deny
`unreachable_pub`, so a `pub` item is a part of the crate API. Each crate has two counts:

- `items`: a `pub` item (`fn`, `struct`, `enum`, `trait`, `const`, `static`, `type`, `mod`,
  `union`, `extern crate`, `extern fn`) and each name of a `pub use` list (`pub use a::{b, c}`
  is two). A `pub fn` or `pub const` inside an `impl` block is an item too, whatever the type
  of the `impl` is.
- `members`: a `pub` field of a `pub struct` or `pub union`, and a variant of a `pub enum`.

`native/api_baseline.json` holds both counts for each library. A count that grows or shrinks
fails until the number changes in the same pull request, so each change of an API shows in
the review.

What the counts do not hold: `pub(crate)` and other restricted items, fields of a type that is
not `pub`, items of a trait, and the files of the tests (`rust_source.test_files`).

Macros: the text of a `macro_rules!` body is read as written. A `pub` item in a template counts
once, and its expansions do not count. A `pub` item in the text of a macro call counts, and a
visibility token that the call passes on does not.

Limit: a declaration macro whose template builds the items (`record!`, `text_type!`,
`closed_enum!` and `rules!` of `archkeel-contract`) counts once in its template, not once for
each call. So the counts of `archkeel-contract` miss about 90 public types, their accessors and
their enum variants. The baseline still ratchets the hand-written items; a change of a macro
call does not show. See `docs/known-limits.md`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path

from rust_source import (
    Token,
    group_end,
    inline_test_mask,
    read_sources,
    test_files,
    tokenize,
)

ITEMS = frozenset("fn struct enum trait static type mod union use crate".split())
MODIFIERS = frozenset({"unsafe", "async", "extern"})
KINDS = ("items", "members")


def libraries(native: Path) -> dict[str, Path]:
    """Return the source directory of each library crate: it has `src/lib.rs`."""
    found: dict[str, Path] = {}
    for manifest in sorted(native.glob("*/Cargo.toml")):
        source = manifest.parent / "src"
        if (source / "lib.rs").is_file():
            package = tomllib.loads(manifest.read_text(encoding="utf-8"))["package"]
            found[package["name"]] = source
    return found


def _use_members(tokens: Sequence[Token], at: int) -> int:
    """Count the names that the `use` tree after `at` brings in, up to its `;`."""
    count, pending = 0, False
    for token in tokens[at:]:
        if token.text in {",", "}", ";"}:
            count, pending = count + pending, False
            if token.text == ";":
                break
        elif token.text == "{":
            pending = False
        elif token.kind == "name" or token.text == "*":
            pending = True
    return count


def _variants(tokens: Sequence[Token], at: int) -> int:
    """Count the variants of the enum whose name is at `at`."""
    start = next((i for i in range(at, len(tokens)) if tokens[i].text == "{"), len(tokens))
    count, position, expect = 0, start + 1, True
    while position < len(tokens) and tokens[position].text != "}":
        text = tokens[position].text
        if text == "#" and tokens[position + 1].text == "[":
            position = group_end(tokens, position + 1)
        elif expect and tokens[position].kind == "name":
            count, expect = count + 1, False
            position += 1
        elif text in {"(", "{", "["}:
            position = group_end(tokens, position)
        else:
            expect = expect or text == ","
            position += 1
    return count


def _pub_type_bodies(tokens: Sequence[Token]) -> list[tuple[int, int]]:
    """Return the token ranges of the bodies of the `pub struct` and `pub union` items.

    The body is the first `(` or `{` after the name that is outside the generic list `<...>`
    and, for a tuple struct, before any `where` clause. A `(` or `{` inside the generics or the
    `where` clause, as in `Fn(u8)`, is skipped by its bracket depth. A unit struct has no body.
    """
    bodies: list[tuple[int, int]] = []
    for at in range(1, len(tokens)):
        if tokens[at].text not in {"struct", "union"} or tokens[at - 1].text != "pub":
            continue
        angle, where, position = 0, False, at + 1
        while position < len(tokens):
            text = tokens[position].text
            if text == "<":
                angle += 1
            elif text == ">" and tokens[position - 1].text != "-":  # `->` is not a closing `>`
                angle = max(angle - 1, 0)
            elif text == "where" and angle == 0:
                where = True
            elif text == ";" and angle == 0:
                break
            elif text == "{" and angle == 0 or text == "(" and angle == 0 and not where:
                bodies.append((position, group_end(tokens, position)))
                break
            elif text in {"(", "[", "{"}:
                position = group_end(tokens, position)
                continue
            position += 1
    return bodies


def count_tokens(tokens: Sequence[Token]) -> tuple[int, int]:
    """Return the (items, members) of the public API of one file, given as tokens."""
    items = members = 0
    bodies = _pub_type_bodies(tokens)
    for at, token in enumerate(tokens):
        if token.text != "pub" or token.kind != "name":
            continue
        position = at + 1
        if position >= len(tokens) or tokens[position].text == "(":
            continue  # pub(crate) and its kin are not a part of the API
        while tokens[position].text in MODIFIERS or tokens[position].kind == "literal":
            position += 1  # `unsafe`, `async`, `extern "C"`
        if tokens[position].text == "const" and tokens[position + 1].text in {
            "fn",
            "unsafe",
            "async",
            "extern",
        }:
            position += 1
        text = tokens[position].text
        if text in ITEMS or text == "const":
            items += _use_members(tokens, position + 1) if text == "use" else 1
            if text == "enum":
                members += _variants(tokens, position + 1)
        elif any(start <= at < stop for start, stop in bodies):
            members += 1  # a field of a pub struct or pub union, named or of a tuple struct
    return items, members


def production_tokens(text: str) -> list[Token]:
    """Return the tokens of a file without its inline `#[cfg(test)]` modules."""
    tokens = tokenize(text)
    return [
        token for token, inside in zip(tokens, inline_test_mask(tokens), strict=True) if not inside
    ]


def count_public(source: Path) -> tuple[int, int]:
    """Return the (items, members) of the public API of the production files of one crate."""
    sources = read_sources(source)
    marked = test_files(sources)
    items = members = 0
    for name, text in sources.items():
        if name not in marked:
            file_items, file_members = count_tokens(production_tokens(text))
            items, members = items + file_items, members + file_members
    return items, members


def problems(native: Path, baseline: Mapping[str, object]) -> list[str]:
    """Return one line for each library that breaks the API rules."""
    found = libraries(native)
    result: list[str] = []
    for name, source in found.items():
        if "#![deny(unreachable_pub)]" not in "".join(
            token.text for token in tokenize((source / "lib.rs").read_text(encoding="utf-8"))
        ):
            result.append(f"{name} must have #![deny(unreachable_pub)] in lib.rs.")
        expected = baseline.get(name)
        if not isinstance(expected, Mapping):
            result.append(
                f"{name} has no entry with items and members in native/api_baseline.json."
            )
            continue
        for kind, count in zip(KINDS, count_public(source), strict=True):
            allowed = expected.get(kind)
            if not isinstance(allowed, int):
                result.append(f"{name} has no {kind} count in native/api_baseline.json.")
            elif count != allowed:
                direction = "grew" if count > allowed else "shrank"
                result.append(
                    f"{name} has {count} public {kind} and {direction} from {allowed}. "
                    f"Set {name} {kind} to {count} in native/api_baseline.json "
                    "and name the change in the PR."
                )
    result.extend(
        f"{name} is in native/api_baseline.json and is no library with code."
        for name in sorted(set(baseline) - set(found))
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--native", type=Path, default=Path("native"))
    parser.add_argument(
        "--check", action="store_true", help="fail on a rule or a count that differs"
    )
    args = parser.parse_args(argv)
    for name, source in libraries(args.native).items():
        items, members = count_public(source)
        print(f"pub items {name}: {items}")
        print(f"pub members {name}: {members}")
    if not args.check:
        return 0
    baseline = json.loads((args.native / "api_baseline.json").read_text(encoding="utf-8"))
    found = problems(args.native, baseline)
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
