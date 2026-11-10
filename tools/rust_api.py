# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Count the public items of each Rust library crate and ratchet the count (AD-327).

`native/layers.toml` names the library crates. Each one that has code must deny
`unreachable_pub`, so a `pub` item is a part of the crate API. `native/api_baseline.json` holds
the count for each library. A count that grows or shrinks fails until the number changes in the
same pull request, so each growth of an API shows in the review.

What the count holds, one for each: a `pub` item (`fn`, `struct`, `enum`, `trait`, `const`,
`static`, `type`, `mod`, `union`, `extern crate`, `extern fn`), a `pub` field, a member of a
`pub use` list (`pub use a::{b, c}` is two), and a variant of a `pub enum`.
What it does not hold: `pub(crate)` and other restricted items, what a macro adds when it
expands (a `pub` that stands in the text of a macro call is counted), items of a trait, and the
files of the tests (`rust_source.test_files`).
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path

from rust_source import Token, inline_test_mask, read_sources, test_files, tokenize

ITEMS = frozenset("fn struct enum trait static type mod union use crate".split())
MODIFIERS = frozenset({"unsafe", "async", "extern"})


def libraries(native: Path) -> dict[str, Path]:
    """Return the source directory of each library crate that has code."""
    layers = tomllib.loads((native / "layers.toml").read_text(encoding="utf-8"))
    return {
        name: native / entry["dir"] / "src"
        for name, entry in sorted(layers["crates"].items())
        if entry["role"] == "library" and not entry.get("planned")
    }


def _skip_group(tokens: Sequence[Token], at: int, opening: str, closing: str) -> int:
    """Return the index after the group that opens at `at`."""
    depth = 0
    for position in range(at, len(tokens)):
        depth += (tokens[position].text == opening) - (tokens[position].text == closing)
        if depth == 0:
            return position + 1
    return len(tokens)


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
            position = _skip_group(tokens, position + 1, "[", "]")
        elif expect and tokens[position].kind == "name":
            count, expect = count + 1, False
            position += 1
        elif text in {"(", "{", "["}:
            closing = {"(": ")", "{": "}", "[": "]"}[text]
            position = _skip_group(tokens, position, text, closing)
        else:
            expect = expect or text == ","
            position += 1
    return count


def count_tokens(tokens: Sequence[Token]) -> int:
    """Count the public API of one file, given as tokens."""
    total = 0
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
            total += _use_members(tokens, position + 1) if text == "use" else 1
            if text == "enum":
                total += _variants(tokens, position + 1)
        else:
            total += 1  # a field, named or of a tuple struct
    return total


def production_tokens(text: str) -> list[Token]:
    """Return the tokens of a file without its inline `#[cfg(test)]` modules."""
    tokens = tokenize(text)
    return [
        token for token, inside in zip(tokens, inline_test_mask(tokens), strict=True) if not inside
    ]


def count_public(source: Path) -> int:
    """Count the public API of the production files of one crate."""
    sources = read_sources(source)
    marked = test_files(sources)
    return sum(
        count_tokens(production_tokens(text))
        for name, text in sources.items()
        if name not in marked
    )


def problems(native: Path, baseline: Mapping[str, int]) -> list[str]:
    """Return one line for each library that breaks the API rules."""
    found = libraries(native)
    result: list[str] = []
    for name, source in found.items():
        if "#![deny(unreachable_pub)]" not in "".join(
            token.text for token in tokenize((source / "lib.rs").read_text(encoding="utf-8"))
        ):
            result.append(f"{name} must have #![deny(unreachable_pub)] in lib.rs.")
        count, allowed = count_public(source), baseline.get(name)
        if allowed is None:
            result.append(
                f"{name} has {count} public items and no entry in native/api_baseline.json."
            )
        elif count != allowed:
            direction = "grew" if count > allowed else "shrank"
            result.append(
                f"{name} has {count} public items and {direction} from {allowed}. "
                f"Set {name} to {count} in native/api_baseline.json and name the change in the PR."
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
        print(f"pub items {name}: {count_public(source)}")
    if not args.check:
        return 0
    baseline = json.loads((args.native / "api_baseline.json").read_text(encoding="utf-8"))
    found = problems(args.native, baseline)
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
