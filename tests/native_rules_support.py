# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The rules of native/ that the contract language cannot say for Rust yet (AD-382).

Consumers: `tests/test_native_self_rules.py` and `tests/test_native_core.py`. Each function reads
a `native/` directory, so a test can plant a violation in a copy. Each rule stays a test until a
Rust rule kind can say it.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from rust_source import inline_test_mask, read_sources, test_files, tokenize  # noqa: E402

CORE_SIDE = ("model", "eval", "report", "core")
LANGUAGES = re.compile(r"python|typescript|dart|\brust\b", re.IGNORECASE)
SYSTEM = frozenset({"fs", "env", "net", "process", "os"})
PATH_METHODS = frozenset(
    "exists try_exists is_file is_dir is_symlink metadata symlink_metadata read_dir read_link"
    " canonicalize".split()
)
Use = tuple[list[str], str | None]
COLLECTORS = ("typescript_collector", "rust_collector", "python_collector", "dart_collector")
# The crate order: base crates by level, the core chain from low to high, the collectors.
BASE = {"facts": 0, "pytext": 0, "build_support": 0, "dart_grammar": 0}
BASE |= {"snapshot": 1, "wire": 1, "store": 1}
CHAIN = ("contract", "model", "model_barrier", "eval", "report", "core")
# AD-406: the one crate between the core and the collectors.
COMPOSITION = "collect"
# AD-406 review F4: the exact base crates that collect uses besides the collectors.
COMPOSITION_USES = frozenset({"facts", "store", "wire"})


def production_sources(native: Path, crate: str) -> dict[str, str]:
    """The text of each production file of one crate, by path below `native/`."""
    sources = read_sources(native / crate / "src")
    marked = test_files(sources)
    return {f"{crate}/src/{name}": text for name, text in sources.items() if name not in marked}


def language_names(native: Path) -> Counter[str]:
    """Each language name in the core side, comments included, as `<file>: <name>`."""
    return Counter(
        f"{name}: {match.group(0).lower()}"
        for crate in CORE_SIDE
        for name, text in production_sources(native, crate).items()
        for match in LANGUAGES.finditer(text)
    )


def system_uses(native: Path) -> Counter[str]:
    """Each system access in the production code of the core side, as `<file>: <path>`.

    It counts a path or a `use` of `std::fs`, `std::env`, `std::net`, `std::process` and
    `std::os`, of `std::io::{stdin, stdout, stderr}` and of `std::time::{SystemTime, Instant}`,
    also as `::std::..`, in a `use` group, under an alias of `std` or of the module, and each
    call of a file method of `Path` (`.exists()`, `Path::is_file(p)`). Inline `#[cfg(test)]`
    code does not count. The limits of a text scan are in AD-382.
    """
    found: Counter[str] = Counter()
    for crate in CORE_SIDE:
        for name, text in production_sources(native, crate).items():
            found.update(f"{name}: {hit}" for hit in _file_hits(_words(text)))
    return found


def _words(text: str) -> list[str]:
    """The production tokens of a file, with `::` as one word."""
    tokens = tokenize(text)
    words: list[str] = []
    for token, test in zip(tokens, inline_test_mask(tokens), strict=True):
        if test:
            continue
        if token.text == ":" and words and words[-1] == ":":
            words[-1] = "::"
        else:
            words.append(token.text)
    return [*words, ";", ";"]


def _classify(path: list[str]) -> str | None:
    if len(path) < 2 or path[0] != "std":
        return None
    if path[1] in SYSTEM:
        return f"std::{path[1]}"
    member = path[2] if len(path) > 2 else ""
    if path[1] == "io" and member in {"stdin", "stdout", "stderr", "*"}:
        return f"std::io::{member}"
    if path[1] == "time" and member in {"SystemTime", "Instant", "*"}:
        return f"std::time::{member}"
    return None


def _use_tree(words: list[str], at: int, prefix: list[str]) -> tuple[list[Use], int]:
    """The (path, bound name) of each leaf of the `use` tree at `at`, and the index after it."""
    path = list(prefix)
    at += words[at] == "::"
    while True:
        if words[at] == "{":
            leaves, at = [], at + 1
            while words[at] not in {"}", ";"}:
                found, at = _use_tree(words, at, path)
                leaves += found
                at += words[at] == ","
            return leaves, at + 1
        if words[at] == "*":
            return [([*path, "*"], None)], at + 1
        path.append(words[at])
        at += 1
        if words[at] == "::":
            at += 1
            continue
        if path[-1] == "self":
            path.pop()
        bound = path[-1] if path else None
        if words[at] == "as":
            bound, at = words[at + 1], at + 2
        return [(path, bound)], at


def _file_hits(words: list[str]) -> list[str]:
    hits: list[str] = []
    heads: dict[str, list[str]] = {"std": ["std"]}
    skip: set[int] = set()
    for at, word in enumerate(words):
        if word == "use":
            leaves, end = _use_tree(words, at + 1, [])
            skip |= set(range(at, end))
            for path, bound in leaves:
                path = heads.get(path[0], [path[0]]) + path[1:] if path else path
                hits += [hit] if (hit := _classify(path)) else []
                if bound and path[:1] == ["std"] and len(path) <= 2:
                    heads[bound] = path  # a module alias: `use std::io;`, `use std as s;`
        elif words[at : at + 3] == ["extern", "crate", "std"] and words[at + 3] == "as":
            heads[words[at + 4]] = ["std"]
    for at, word in enumerate(words):
        if at in skip:
            continue
        if word in PATH_METHODS and words[at + 1] == "(" and words[at - 1] in {".", "::"}:
            hits.append(f"Path::{word}")
        if (
            word in heads
            and words[at + 1] == "::"
            and (at == 0 or words[at - 1] != "::" or not words[at - 2].isidentifier())
        ):
            path, end = list(heads[word]), at + 2
            while words[end].isidentifier() and words[end + 1] == "::":
                path, end = [*path, words[end]], end + 2
            hits += [hit] if (hit := _classify([*path, words[end]])) else []
    return hits


def _crate(component: dict[str, Any]) -> str:
    names = [*component.get("packages", ()), *component.get("exact_modules", ())]
    return names[0].split(".")[1].removeprefix("archkeel_") if names else ""


def allowed(source: str, target: str) -> bool:
    """Whether crate `source` may require crate `target` by the crate order (AD-382).

    A base crate requires only a base crate of a lower level. The contract crate requires
    nothing. A crate of the core chain requires a base crate or a lower crate of the chain;
    nothing requires the core. A collector requires only base crates. No crate requires a
    collector of another crate. AD-406: only `collect` requires a collector; it requires only
    facts, store, wire and the collectors, and only the core requires it. A collector does not
    require the store.
    """
    if source == target:
        return True
    if source == COMPOSITION:
        return target in COMPOSITION_USES or target in COLLECTORS
    if target == COMPOSITION:
        return source == "core"
    if target in COLLECTORS or target in {"core", "model_barrier"} or source == "contract":
        return False
    if source in BASE:
        return target in BASE and BASE[target] < BASE[source]
    if source in COLLECTORS:
        return target in BASE and target != "store"
    return target in BASE or CHAIN.index(target) < CHAIN.index(source)


def requires_problems(contract: dict[str, Any]) -> list[str]:
    """Each declared `requires` that the crate order does not allow.

    `forbidden_dependency` rules hold only the upward directions of the core chain; a rule that
    names a collector or a base crate keeps pair gaps (AD-357), so this test holds each other
    direction of a declared `requires` (AD-382). An edge without a `requires` is a FAIL of
    `NATIVE-REQUIRES-COMPLETE`.
    """
    crates = {part["label"]: _crate(part) for part in contract["components"]}
    placed = {*BASE, *CHAIN, *COLLECTORS, COMPOSITION}
    unplaced = [
        f"crate {crate} has no place in the crate order"
        for crate in sorted(set(crates.values()) - placed)
    ]
    return unplaced + [
        f"{part['label']} requires {need['component']}"
        for part in contract["components"]
        for need in part.get("requires", ())
        if not unplaced and not allowed(crates[part["label"]], crates[need["component"]])
    ]
