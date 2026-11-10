# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find duplicated blocks in the Rust code of `native/` and ratchet them (AD-327).

The tool tokenizes each `.rs` file, drops comments and white space, and hashes each window of
`WINDOW` tokens. In the default mode (type 2) an identifier and a literal become a placeholder, so
a renamed copy is still a clone. `--exact` keeps them. Windows with the same hash that follow each
other join into one block.

Production code is a gate: `native/clone_baseline.json` lists each block that exists with the
reason it stays. A new block fails, and so does a block that grew. A block that shrank or went
away fails until its entry is lowered or removed (`--lower` does it). Test files may repeat a
fixture, so their blocks are a warning only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

WINDOW = 70
# A window that repeats with a period up to this many tokens is a table of similar rows.
PERIOD = 24
TOKEN = re.compile(
    r"""
    (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<literal>b?r(?P<hashes>\#*)".*?"(?P=hashes)|b?"(?:\\.|[^"\\])*"|b?'(?:\\.[^']*|[^\\'\n])'
        |\b\d[\w.]*)
  | (?P<ident>[A-Za-z_]\w*|'[A-Za-z_]\w*)
  | (?P<punct>[^\s\w])
    """,
    re.S | re.X,
)
KEYWORDS = frozenset(
    "as async await break const continue crate dyn else enum extern false fn for if impl in let "
    "loop match mod move mut pub ref return self Self static struct super trait true type unsafe "
    "use where while".split()
)
TEST_FILE = re.compile(r"(?:_tests|^test_\w+|^tests?)$")


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    line: int


@dataclass(frozen=True, slots=True)
class Block:
    """A run of equal windows in two places."""

    key: str
    first: str
    second: str
    tokens: int
    first_lines: tuple[int, int]
    second_lines: tuple[int, int]

    @property
    def is_test(self) -> bool:
        return is_test_file(self.first) or is_test_file(self.second)


def is_test_file(relative: str) -> bool:
    path = Path(relative)
    return "tests" in path.parts or bool(TEST_FILE.search(path.stem))


def tokenize(text: str, exact: bool) -> list[Token]:
    """Return the tokens without comments; a type-2 token hides names and literal values."""
    tokens: list[Token] = []
    for match in TOKEN.finditer(text):
        kind = match.lastgroup
        if kind == "comment":
            continue
        line = text.count("\n", 0, match.start()) + 1
        value = match.group()
        if not exact:
            if kind == "literal":
                value = "#"
            elif kind == "ident" and value not in KEYWORDS:
                value = "$"
        tokens.append(Token(value, line))
    return tokens


def _is_table(window: Sequence[Token]) -> bool:
    """A table (rows of one shape) repeats itself in a few tokens: that is data, not logic."""
    texts = [token.text for token in window]
    return any(
        texts[:-period] == texts[period:] for period in range(1, min(PERIOD, len(texts) // 2) + 1)
    )


def _digest(texts: Sequence[str]) -> str:
    return hashlib.sha256("\x00".join(texts).encode()).hexdigest()


def find_blocks(
    sources: Mapping[str, str], exact: bool = False, window: int = WINDOW
) -> list[Block]:
    """Return each block of at least `window` tokens that appears twice or more."""
    tokens = {name: tokenize(text, exact) for name, text in sources.items()}
    places: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for name in sorted(tokens):
        texts = [token.text for token in tokens[name]]
        for start in range(len(texts) - window + 1):
            places[_digest(texts[start : start + window])].append((name, start))
    # Link each later place to the first one: a block of many copies stays a list of pairs.
    pairs: dict[tuple[str, str, int], list[tuple[int, int, str]]] = defaultdict(list)
    for digest, found in places.items():
        first_name, first_start = found[0]
        if len(found) > 1 and _is_table(tokens[first_name][first_start : first_start + window]):
            continue
        for name, start in found[1:]:
            if name == first_name and abs(start - first_start) < window:
                continue
            pairs[(first_name, name, start - first_start)].append((first_start, start, digest))
    blocks: list[Block] = []
    for (first, second, _), runs in sorted(pairs.items()):
        runs.sort()
        begin = previous = runs[0][0]
        digest = runs[0][2]
        for position, _other, run_digest in [*runs[1:], (-2, 0, "")]:
            if position == previous + 1:
                previous = position
                continue
            blocks.append(_block(tokens, first, second, begin, previous, runs, digest, window))
            begin = previous = position
            digest = run_digest
    return _merged([block for block in blocks if not _overlaps(block)])


def _merged(blocks: Sequence[Block]) -> list[Block]:
    """Keep the longest of the blocks that overlap in the same two files."""
    kept: list[Block] = []
    for block in sorted(
        blocks, key=lambda item: (item.first, item.second, item.first_lines, -item.tokens)
    ):
        last = kept[-1] if kept else None
        if (
            last is not None
            and (last.first, last.second) == (block.first, block.second)
            and block.first_lines[0] <= last.first_lines[1]
        ):
            if block.tokens > last.tokens:
                kept[-1] = block
            continue
        kept.append(block)
    return kept


def _overlaps(block: Block) -> bool:
    """A block that meets itself in one file is a repeated line, not a copy."""
    first, second = block.first_lines, block.second_lines
    return block.first == block.second and first[0] <= second[1] and second[0] <= first[1]


def _block(
    tokens: Mapping[str, list[Token]],
    first: str,
    second: str,
    begin: int,
    last: int,
    runs: Sequence[tuple[int, int, str]],
    digest: str,
    window: int,
) -> Block:
    other = next(other for position, other, _ in runs if position == begin)
    length = last - begin + window
    first_tokens, second_tokens = tokens[first], tokens[second]
    return Block(
        key=f"{first}|{second}|{digest[:10]}",
        first=first,
        second=second,
        tokens=length,
        first_lines=(first_tokens[begin].line, first_tokens[begin + length - 1].line),
        second_lines=(second_tokens[other].line, second_tokens[other + length - 1].line),
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


def read_sources(native: Path) -> dict[str, str]:
    return {
        path.relative_to(native).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(native.rglob("*.rs"))
        if "target" not in path.relative_to(native).parts
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
