# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""List the public API of each Rust library crate by name and ratchet the list (AD-327, AD-382).

A library crate of `native/` has `src/lib.rs`. Each one must deny
`unreachable_pub`, so a `pub` item is a part of the crate API. Each public part is one line
`<kind> <module path>::<name>`, with the signature of a `fn` and the type of a field:

- an item: a `pub` item (`fn`, `struct`, `enum`, `trait`, `const`, `static`, `type`, `mod`,
  `union`, `extern crate`, `extern fn`) and each name of a `pub use` list (`pub use a::{b, c}`
  is two lines). A `pub fn` or `pub const` inside an `impl` block is an item of its file,
  whatever the type of the `impl` is.
- a member: `field <path>::Type.name` for a `pub` field of a `pub struct` or `pub union`
  (`Type.0` in a tuple struct), and `variant <path>::Enum::Name` for a variant of a `pub enum`.

`native/api_baseline.json` holds the sorted list of each library. A part that is added or
removed fails until the list changes in the same pull request, so each change of an API shows
in the review by name, also when one part replaces another or a signature changes. Run
`python tools/rust_api.py --write` to write the list, then review the diff.

What the list does not hold: `pub(crate)` and other restricted items, fields of a type that is
not `pub`, items of a trait, and the files of the tests (`rust_source.test_files`). Two `pub fn`
of the same name in two `impl` blocks of one file are two equal lines, so a move between the
two blocks does not show.

Macros: the text of a `macro_rules!` body is read as written. A `pub` item in a template counts
once, and its expansions do not count. A `pub` item in the text of a macro call counts, and a
visibility token that the call passes on does not.

Limit: a declaration macro whose template builds the items (`record!`, `text_type!`,
`closed_enum!` and `rules!` of `archkeel-contract`) shows once in its template, not once for
each call. So the list of `archkeel-contract` misses about 90 public types, their accessors and
their enum variants. A change of a macro call does not show. See `docs/known-limits.md`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import Counter
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
MEMBERS = frozenset({"field", "variant"})
WRITE = "python tools/rust_api.py --write"


def libraries(native: Path) -> dict[str, Path]:
    """Return the source directory of each library crate: it has `src/lib.rs`."""
    found: dict[str, Path] = {}
    for manifest in sorted(native.glob("*/Cargo.toml")):
        source = manifest.parent / "src"
        if (source / "lib.rs").is_file():
            package = tomllib.loads(manifest.read_text(encoding="utf-8"))["package"]
            found[package["name"]] = source
    return found


def _use_names(tokens: Sequence[Token], at: int) -> list[str]:
    """Return the names that the `use` tree after `at` brings in, up to its `;`."""
    names: list[str] = []
    last: str | None = None
    for token in tokens[at:]:
        if token.text in {",", "}", ";"}:
            names += [last] if last is not None else []
            last = None
            if token.text == ";":
                break
        elif token.text == "{":
            last = None
        elif token.kind == "name" and token.text != "as" or token.text == "*":
            last = token.text
    return names


def _variants(tokens: Sequence[Token], at: int) -> list[str]:
    """Return the variants of the enum whose name is at `at`."""
    start = next((i for i in range(at, len(tokens)) if tokens[i].text == "{"), len(tokens))
    names: list[str] = []
    position, expect = start + 1, True
    while position < len(tokens) and tokens[position].text != "}":
        text = tokens[position].text
        if text == "#" and tokens[position + 1].text == "[":
            position = group_end(tokens, position + 1)
        elif expect and tokens[position].kind == "name":
            names.append(text)
            expect = False
            position += 1
        elif text in {"(", "{", "["}:
            position = group_end(tokens, position)
        else:
            expect = expect or text == ","
            position += 1
    return names


def _pub_type_bodies(tokens: Sequence[Token]) -> list[tuple[int, int, str]]:
    """Return the token ranges and the names of the bodies of the `pub struct` and `pub union`.

    The body is the first `(` or `{` after the name that is outside the generic list `<...>`
    and, for a tuple struct, before any `where` clause. A `(` or `{` inside the generics or the
    `where` clause, as in `Fn(u8)`, is skipped by its bracket depth. A unit struct has no body.
    """
    bodies: list[tuple[int, int, str]] = []
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
                bodies.append((position, group_end(tokens, position), tokens[at + 1].text))
                break
            elif text in {"(", "[", "{"}:
                position = group_end(tokens, position)
                continue
            position += 1
    return bodies


def _field(tokens: Sequence[Token], start: int, at: int) -> str:
    """The name of the field whose `pub` is at `at`, or its index in a tuple struct."""
    if tokens[at + 1].kind == "name" and tokens[at + 2].text == ":" != tokens[at + 3].text:
        return tokens[at + 1].text
    depth = index = 0
    for position in range(start + 1, at):
        text = tokens[position].text
        depth += text in {"(", "[", "{", "<"}
        depth -= text in {")", "]", "}"} or text == ">" and tokens[position - 1].text != "-"
        index += text == "," and depth == 0
    return str(index)


def _text(tokens: Sequence[Token], start: int, stops: frozenset[str]) -> str:
    """The tokens from `start` to the first stop at bracket depth 0, as compact text."""
    parts: list[str] = []
    depth, position = 0, start
    while position < len(tokens):
        token = tokens[position]
        if depth == 0 and token.text in stops:
            break
        depth += token.text in {"(", "[", "<"}
        depth -= token.text in {")", "]"} or token.text == ">" and parts[-1:] != ["-"]
        spaced = parts and parts[-1][-1:].isalnum() and token.kind != "punct"
        parts.append((" " if spaced else "") + token.text)
        position += 1
    return "".join(parts)


SIGNATURE_END = frozenset({"{", ";", "where"})
FIELD_END = frozenset({",", "}", ")"})


def public_names(tokens: Sequence[Token]) -> list[tuple[str, str]]:
    """Return the (kind, name) of each part of the public API of one file, given as tokens.

    A kind is an item keyword (`fn`, `struct`, `use`, ...), `field` or `variant`. A field is
    `Type.name` (`Type.0` in a tuple struct) and a variant is `Enum::Name`.
    """
    names: list[tuple[str, str]] = []
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
        after = [t.text for t in tokens[position + 1 : position + 3]] + ["", ""]
        if text == "use":
            names += [("use", name) for name in _use_names(tokens, position + 1)]
        elif text in ITEMS or text == "const":
            name = after[1] if after[0] == "mut" else after[0]
            signature = _text(tokens, position + 2, SIGNATURE_END) if text == "fn" else ""
            names.append((text, name + signature))
            if text == "enum":
                names += [("variant", f"{name}::{v}") for v in _variants(tokens, position + 1)]
        else:
            body = next(((s, n) for s, e, n in bodies if s <= at < e), None)
            if body is not None:  # a field of a pub struct or pub union, with its type
                field = _field(tokens, body[0], at)
                start = at + 3 if field.isidentifier() else at + 1
                names.append(("field", f"{body[1]}.{field}: {_text(tokens, start, FIELD_END)}"))
    return names


def count_tokens(tokens: Sequence[Token]) -> tuple[int, int]:
    """Return the (items, members) of the public API of one file, given as tokens."""
    names = public_names(tokens)
    members = sum(kind in MEMBERS for kind, _ in names)
    return len(names) - members, members


def production_tokens(text: str) -> list[Token]:
    """Return the tokens of a file without its inline `#[cfg(test)]` modules."""
    tokens = tokenize(text)
    return [
        token for token, inside in zip(tokens, inline_test_mask(tokens), strict=True) if not inside
    ]


def _module(name: str) -> str:
    """The module path of a source file of a crate: `a/mod.rs` and `a.rs` are `a`."""
    parts = name.removesuffix(".rs").split("/")
    return "::".join(parts[:-1] if parts[-1] in {"lib", "main", "mod"} else parts)


def public_api(source: Path) -> list[str]:
    """Return the sorted public API of the production files of one crate, one line a part."""
    sources = read_sources(source)
    marked = test_files(sources)
    return sorted(
        f"{kind} {'::'.join(filter(None, (_module(name), part)))}"
        for name, text in sources.items()
        if name not in marked
        for kind, part in public_names(production_tokens(text))
    )


def count_public(source: Path) -> tuple[int, int]:
    """Return the (items, members) of the public API of the production files of one crate."""
    api = public_api(source)
    members = sum(line.split(" ", 1)[0] in MEMBERS for line in api)
    return len(api) - members, members


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
        if not isinstance(expected, list) or not all(isinstance(x, str) for x in expected):
            result.append(f"{name} has no list of public parts in native/api_baseline.json.")
            continue
        now, before = Counter(public_api(source)), Counter(expected)
        result += [f"{name} adds public {line}." for line in sorted((now - before).elements())]
        result += [f"{name} removes public {line}." for line in sorted((before - now).elements())]
    result.extend(
        f"{name} is in native/api_baseline.json and is no library with code."
        for name in sorted(set(baseline) - set(found))
    )
    if any(" public " in line for line in result):
        result.append(f"Run `{WRITE}` and name each change of the API in the PR.")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--native", type=Path, default=Path("native"))
    parser.add_argument(
        "--check", action="store_true", help="fail on a rule or a part that differs"
    )
    parser.add_argument("--write", action="store_true", help="write the lists of the baseline")
    args = parser.parse_args(argv)
    if args.write:
        lists = {name: public_api(source) for name, source in libraries(args.native).items()}
        text = json.dumps(lists, indent=2, sort_keys=True) + "\n"
        (args.native / "api_baseline.json").write_text(text, encoding="utf-8")
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
