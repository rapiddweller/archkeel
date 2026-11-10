# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Count the public items of each Rust library crate and ratchet the count (AD-327).

`native/layers.toml` names the library crates. Each one that has code must deny
`unreachable_pub`, so a `pub` item is a part of the crate API. `native/api_baseline.json` holds
the count of `pub` items for each library. A count that grows or shrinks fails until the number
changes in the same pull request, so each growth of an API shows in the review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path

PUBLIC = re.compile(
    r"^\s*pub\s+(?:unsafe\s+|async\s+|const\s+)*(?:fn|struct|enum|trait|const|static|type|mod|use|union)\b",
    re.M,
)
NOISE = re.compile(r"//[^\n]*|/\*.*?\*/|b?r(#*)\".*?\"\1|\"(?:\\.|[^\"\\])*\"", re.S)
DENY = re.compile(r"#!\[deny\(unreachable_pub\)\]")
TEST_FILE = re.compile(r"_tests$|^test_tree$")


def libraries(native: Path) -> dict[str, Path]:
    """Return the source directory of each library crate that has code."""
    layers = tomllib.loads((native / "layers.toml").read_text(encoding="utf-8"))
    return {
        name: native / entry["dir"] / "src"
        for name, entry in sorted(layers["crates"].items())
        if entry["role"] == "library" and not entry.get("planned")
    }


def count_public(source: Path) -> int:
    """Count the `pub` items of the production files of one crate."""
    total = 0
    for path in sorted(source.rglob("*.rs")):
        if not TEST_FILE.search(path.stem):
            total += len(PUBLIC.findall(NOISE.sub("", path.read_text(encoding="utf-8"))))
    return total


def problems(native: Path, baseline: Mapping[str, int]) -> list[str]:
    """Return one line for each library that breaks the API rules."""
    found = libraries(native)
    result: list[str] = []
    for name, source in found.items():
        if not DENY.search((source / "lib.rs").read_text(encoding="utf-8")):
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
