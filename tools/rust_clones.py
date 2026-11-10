# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find duplicated blocks in the Rust code of `native/` and ratchet them (AD-327).

The tool tokenizes each `.rs` file, drops comments and white space, and hashes each window of
`WINDOW` tokens. In the default mode (type 2) an identifier and a literal become a placeholder, so
a renamed copy is still a clone. `--exact` keeps them. Each copy of a window links to the copy
before it, and windows that follow each other join into one block. A block whose every window is a
table (it repeats within 24 tokens) is skipped; a table inside a function is a clone with the code
around it. A block is a test block only when both sides are test code: a test file
(`rust_source.test_files`) or an inline `#[cfg(test)] mod name { ... }`.

Production code is a gate: `native/clone_baseline.json` lists each block that exists with the
reason it stays. A new block fails, and so does a block that grew. A block that shrank or went
away fails until its entry is lowered or removed (`--lower` does it). Test files may repeat a
fixture, so their blocks are a warning only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from rust_source import inline_test_mask, read_sources, test_files, tokenize

WINDOW = 70
# A window that repeats with a period up to this many tokens is a table of similar rows.
PERIOD = 24
KEYWORDS = frozenset(
    "as async await break const continue crate dyn else enum extern false fn for if impl in let "
    "loop match mod move mut pub ref return self Self static struct super trait true type unsafe "
    "use where while".split()
)
NAME, LITERAL = "\0name", "\0literal"


@dataclass(frozen=True, slots=True)
class Block:
    """A run of equal windows in two places."""

    key: str
    first: str
    second: str
    tokens: int
    first_lines: tuple[int, int]
    second_lines: tuple[int, int]
    is_test: bool


def _texts(text: str, exact: bool) -> tuple[list[str], list[int], list[bool]]:
    """Return the token texts and lines; type 2 hides names and literal values."""
    tokens = tokenize(text)
    inside = inline_test_mask(tokens)
    if exact:
        return [token.text for token in tokens], [token.line for token in tokens], inside
    texts = [
        LITERAL
        if token.kind == "literal"
        else NAME
        if token.kind == "name" and token.text not in KEYWORDS
        else token.text
        for token in tokens
    ]
    return texts, [token.line for token in tokens], inside


def _is_table(texts: Sequence[str]) -> bool:
    """A table repeats itself in a few tokens: that is data, not logic."""
    return any(
        texts[:-period] == texts[period:] for period in range(1, min(PERIOD, len(texts) // 2) + 1)
    )


def _digest(texts: Sequence[str]) -> str:
    return hashlib.sha256("\x00".join(texts).encode()).hexdigest()


def find_blocks(
    sources: Mapping[str, str], exact: bool = False, window: int = WINDOW
) -> list[Block]:
    """Return one block for each pair of neighbouring copies of at least `window` tokens.

    The copies of one window are in file order. Each copy links to the one before it, so a block
    of three copies gives two blocks and a new copy always adds one.
    """
    parsed = {name: _texts(text, exact) for name, text in sources.items()}
    places: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for name in sorted(parsed):
        texts = parsed[name][0]
        for start in range(len(texts) - window + 1):
            places[_digest(texts[start : start + window])].append((name, start))
    pairs: dict[tuple[str, str, int], list[tuple[int, str]]] = defaultdict(list)
    for digest, found in places.items():
        for (before, at), (after, start) in zip(found, found[1:], strict=False):
            if before == after and start - at < window:
                continue  # a line that repeats itself, not a copy
            pairs[(before, after, start - at)].append((at, digest))
    marked = test_files(sources)
    blocks: list[Block] = []
    for (first, second, delta), runs in sorted(pairs.items()):
        runs.sort()
        begin, previous = 0, runs[0][0]
        for index in range(1, len(runs) + 1):
            if index < len(runs) and runs[index][0] == previous + 1:
                previous = runs[index][0]
                continue
            starts = [start for start, _ in runs[begin:index]]
            first_texts = parsed[first][0]
            if not all(_is_table(first_texts[start : start + window]) for start in starts):
                blocks.append(
                    _block(parsed, first, second, delta, starts, runs[begin][1], window, marked)
                )
            if index < len(runs):
                begin = index
                previous = runs[index][0]
    return _keyed(blocks)


def _keyed(blocks: list[Block]) -> list[Block]:
    """Give a second copy in the same two files and with the same text its own key."""
    seen: dict[str, int] = defaultdict(int)
    result: list[Block] = []
    for block in sorted(blocks, key=lambda item: (item.first, item.second, item.first_lines)):
        seen[block.key] += 1
        key = block.key if seen[block.key] == 1 else f"{block.key}#{seen[block.key]}"
        result.append(replace(block, key=key))
    return result


def _in_tests(
    parsed: Mapping[str, tuple[list[str], list[int], list[bool]]],
    marked: frozenset[str],
    name: str,
    begin: int,
    length: int,
) -> bool:
    """Whether a range of tokens is in a test file or only in inline test modules."""
    return name in marked or all(parsed[name][2][begin : begin + length])


def _block(
    parsed: Mapping[str, tuple[list[str], list[int], list[bool]]],
    first: str,
    second: str,
    delta: int,
    starts: Sequence[int],
    digest: str,
    window: int,
    marked: frozenset[str],
) -> Block:
    begin = starts[0]
    length = starts[-1] - begin + window
    if first == second:
        length = min(length, delta)  # a unit that repeats in one file: the copies must not overlap
    first_lines, second_lines = parsed[first][1], parsed[second][1]
    return Block(
        key=f"{first}|{second}|{digest[:10]}",
        first=first,
        second=second,
        tokens=length,
        first_lines=(first_lines[begin], first_lines[begin + length - 1]),
        second_lines=(second_lines[begin + delta], second_lines[begin + delta + length - 1]),
        is_test=_in_tests(parsed, marked, first, begin, length)
        and _in_tests(parsed, marked, second, begin + delta, length),
    )


def ratchet_problems(
    blocks: Iterable[Block], baseline: Mapping[str, Mapping[str, object]]
) -> list[str]:
    """Return one line for each production block that the baseline does not allow."""
    problems: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        seen.add(block.key)
        entry = baseline.get(block.key)
        where = (
            f"{block.first}:{block.first_lines[0]}-{block.first_lines[1]} and "
            f"{block.second}:{block.second_lines[0]}-{block.second_lines[1]}"
        )
        if entry is None:
            problems.append(
                f"New clone of {block.tokens} tokens in {where}. Share the code. "
                "Never add it to native/clone_baseline.json without a reason."
            )
        elif block.tokens > int(str(entry["tokens"])):
            problems.append(
                f"The clone in {where} grew from {entry['tokens']} to {block.tokens} tokens."
            )
        elif block.tokens < int(str(entry["tokens"])):
            problems.append(
                f"The clone in {where} shrank to {block.tokens} tokens. "
                f"Lower its entry {block.key} (run with --lower)."
            )
    problems.extend(
        f"The clone {key} is gone. Remove its entry from the baseline (run with --lower)."
        for key in sorted(set(baseline) - seen)
    )
    return problems


def lowered(
    blocks: Iterable[Block], baseline: Mapping[str, Mapping[str, object]]
) -> dict[str, dict[str, object]]:
    """Return the baseline without gone blocks and with the shrunk counts; it never adds a block."""
    now = {block.key: block for block in blocks}
    return {
        key: {**entry, "tokens": min(int(str(entry["tokens"])), now[key].tokens)}
        for key, entry in baseline.items()
        if key in now
    }


def describe(block: Block) -> str:
    return (
        f"{block.tokens:4d} tokens  {block.first}:{block.first_lines[0]}-{block.first_lines[1]}"
        f"  =  {block.second}:{block.second_lines[0]}-{block.second_lines[1]}  [{block.key}]"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--native", type=Path, default=Path("native"))
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--window", type=int, default=WINDOW)
    parser.add_argument("--exact", action="store_true", help="keep identifiers and literals")
    parser.add_argument("--lower", action="store_true", help="rewrite the baseline downwards")
    parser.add_argument("--list", action="store_true", help="print every block and exit 0")
    args = parser.parse_args(argv)
    baseline_path = args.baseline or args.native / "clone_baseline.json"
    blocks = find_blocks(read_sources(args.native), args.exact, args.window)
    production = [block for block in blocks if not block.is_test]
    tests = [block for block in blocks if block.is_test]
    if args.list:
        print(f"clones: {len(production)} in production, {len(tests)} in tests")
        for block in production:
            print(describe(block))
        for block in tests:
            print(f"warning (test code): {describe(block)}")
        return 0
    baseline = (
        json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    )
    if args.lower:
        baseline_path.write_text(
            json.dumps(lowered(production, baseline), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    problems = ratchet_problems(production, baseline)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"clones: {len(production)} in production, {len(tests)} in tests (warning)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
