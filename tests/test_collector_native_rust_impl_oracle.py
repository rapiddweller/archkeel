# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1005: the compiler finds the files that run the impl blocks of a Rust file.

Consumer: the nightly Full run (the file is in `SLOW_FILES`). The oracle is `cargo check`. For a
file `m` of `native/`, delete its impl blocks from a copy and check the workspace. A file other than
`m` that then fails to compile runs code of an impl in `m`. The collector must hold that pair: an
import edge into `m`, or a pair gap `file -> m` of the trait-impl and method-call rules (AD-806).
A failing file that the collector does not reach over its held pairs is a missed edge, a
candidate for a false PASS. A file that it reaches only over a path is pinned in `DIRECT_ONLY`.

The oracle only finds disagreements. It never decides a verdict. The module oracle in
`test_collector_native_rust_module_oracle.py` deletes a `mod` line and runs on seven modules; this
file deletes the impl blocks and runs on every production file of `native/` that has some.
A file holds the pairs of its inline modules too.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest
from frozen_native import frozen_root as frozen_root

Block = tuple[int, int]
HEAD = re.compile(r"\bimpl\b")
TRAIT_IMPL = re.compile(r"\bfor\b(?!\s*<)")
CHECK = ["cargo", "check", "--offline", "--workspace", "--all-features", "--message-format=json"]


# The files that fail without the inherent impls of a file, and hold no pair into it: they reach it
# over a re-exporting module (`data` for `data::imports`), so a cycle rule sees the path, and a
# rule on the direct pair `file -> impl file` gives no edge. Measured on this tree; a difference
# fails the test, so a closed gap is removed here.
DIRECT_ONLY = {
    "native/contract/src/unused_public.rs": ["native/eval/src/unused_public.rs"],
    "native/facts/src/data/imports.rs": [
        "native/dart/src/collection/imports.rs",
        "native/dart/src/import_survey/edges.rs",
        "native/python/src/survey/declared/direct_calls.rs",
        "native/python/src/survey/imports.rs",
        "native/rust/src/edges.rs",
        "native/rust/src/module_edges.rs",
        "native/store/src/call_owners.rs",
        "native/typescript/src/import_record.rs",
        "native/typescript/src/script_records.rs",
    ],
    "native/facts/src/data/sites.rs": [
        "native/python/src/survey/declared/sites.rs",
        "native/rust/src/calls.rs",
        "native/typescript/src/bound_names.rs",
        "native/typescript/src/records_lists.rs",
        "native/typescript/src/script_depend.rs",
        "native/typescript/src/script_effects.rs",
        "native/typescript/src/script_global.rs",
        "native/typescript/src/script_proof.rs",
        "native/typescript/src/site_records.rs",
    ],
    "native/python/src/survey/declared/direct_calls.rs": ["native/python/src/survey/mod.rs"],
    "native/python/src/survey/declared/sites.rs": ["native/python/src/survey/mod.rs"],
    "native/python/src/survey/hazards_trojan_horse.rs": [
        "native/python/src/survey/hazards_split.rs"
    ],
}


def _code(text: str) -> list[tuple[int, str]]:
    """Each code character of `text` with its offset: comments, strings and chars are left out."""
    kept: list[tuple[int, str]] = []
    i, size = 0, len(text)
    while i < size:
        two = text[i : i + 2]
        if two == "//":
            i = text.find("\n", i) if "\n" in text[i:] else size
        elif two == "/*":
            depth = 1
            i += 2
            while i < size and depth:
                step = text[i : i + 2]
                depth += (step == "/*") - (step == "*/")
                i += 2 if step in ("/*", "*/") else 1
        elif raw := re.match(r'b?r(#*)"', text[i:]):
            end = text.find('"' + raw.group(1), i + raw.end())
            i = size if end < 0 else end + 1 + len(raw.group(1))
        elif text[i] == '"':
            i += 1
            while i < size and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
        elif text[i] == "'" and (lit := re.match(r"'(\\.[^']*|[^\\'])'", text[i:])):
            i += lit.end()
        else:
            kept.append((i, text[i]))
            i += 1
    return kept


def _impl_blocks(text: str) -> list[tuple[Block, bool]]:
    """The line range of each top-level impl block, and whether it is a trait impl."""
    code = _code(text)
    flat = "".join(char for _, char in code)
    found: list[tuple[Block, bool]] = []
    depth = 0
    at = 0
    for index, char in enumerate(flat):
        if index < at:
            continue
        depth += (char == "{") - (char == "}")
        before = flat[:index].rstrip()
        item_start = not before or before[-1] in ";}]" or before.endswith("unsafe")
        if not (depth == 0 and item_start and HEAD.match(flat, index)):
            continue
        open_at = flat.find("{", index)
        header = flat[index:open_at]
        level, close = 0, open_at
        for close in range(open_at, len(flat)):
            level += (flat[close] == "{") - (flat[close] == "}")
            if not level:
                break
        first = text.count("\n", 0, code[index][0])
        last = text.count("\n", 0, code[close][0])
        found.append(((first, last), bool(TRAIT_IMPL.search(header.split(" where")[0]))))
        at = close + 1
    return found


def _without(text: str, blocks: list[Block]) -> str:
    """`text` without the lines of `blocks` and the attribute and doc lines above each."""
    lines = text.split("\n")
    gone: set[int] = set()
    for first, last in blocks:
        while first and re.match(r"\s*(#\[|///)", lines[first - 1]):
            first -= 1
        gone |= set(range(first, last + 1))
    return "\n".join(line for number, line in enumerate(lines) if number not in gone)


def _facts(binary: Path, root: Path) -> dict[str, Any]:
    request = {
        "protocol_version": "9.0.0",
        "snapshot": {"root": str(root), "git_head": "0" * 40, "dirty": False},
        "scope": {"roots": ["native"], "namespace": "native", "exclude_test_sources": True},
        "resolver": {"language": "rust"},
    }
    done = subprocess.run([str(binary)], input=json.dumps(request).encode(), capture_output=True)
    assert done.returncode == 0, done.stderr
    return json.loads(zlib.decompress(done.stdout))["facts"]  # type: ignore[no-any-return]


def _site(span: dict[str, Any]) -> str:
    """The file of the code that the author wrote: the call site of the outermost macro."""
    while span.get("expansion"):
        span = span["expansion"]["span"]
    return f"native/{span['file_name']}"


def _failing_files(work: Path, target: Path) -> set[str]:
    """The files with a compile error, as paths relative to the tree root."""
    env = {**os.environ, "CARGO_TARGET_DIR": str(target)}
    checked = subprocess.run(CHECK, cwd=work / "native", capture_output=True, text=True, env=env)
    failing: set[str] = set()
    for line in checked.stdout.splitlines():
        message = json.loads(line) if line.startswith("{") else {}
        body = message.get("message", {})
        if message.get("reason") == "compiler-message" and body.get("level") == "error":
            failing |= {_site(s) for s in body["spans"] if s["is_primary"]}
    return failing


class Held:
    """The pairs that the collector holds: import edges and pair gaps, by file."""

    def __init__(self, facts: dict[str, Any]) -> None:
        self.modules: dict[str, set[str]] = {}
        for item in facts["files"]:
            self.modules.setdefault(item["rel_path"], set()).add(item["module"])
        self.pairs: set[tuple[str, str]] = set()
        for section in facts["sections"]:
            for record in section["records"]:
                data = record["data"]
                if section["name"] == "imports":
                    self.pairs.add((data["source_module"], data["target_module"]))
                elif section["name"] == "unknowns" and "source_module" in data and "module" in data:
                    self.pairs.add((data["source_module"], data["module"]))

    def reaches(self, source: str, target: str) -> bool:
        """True when `source` reaches `target` over the held pairs, as a cycle rule reads them."""
        seen = set(self.modules[source])
        todo = list(seen)
        goal = self.modules[target]
        while todo:
            at = todo.pop()
            for s, t in self.pairs:
                if s == at and t not in seen:
                    seen.add(t)
                    todo.append(t)
        return any(t in goal or any(t.startswith(m + ".") for m in goal) for t in seen)

    def holds(self, source: str, target: str) -> bool:
        """True when a module of `source` holds a pair into a module of the file `target`."""
        into = self.modules[target]
        return any(
            s in self.modules[source] and (t in into or any(t.startswith(m + ".") for m in into))
            for s, t in self.pairs
        )


@pytest.fixture(scope="module")
def facts(rust_binary: Path, frozen_root: Path) -> dict[str, Any]:
    if shutil.which("cargo") is None:
        pytest.skip("cargo is not installed; install Rust to run the oracle.")
    return _facts(rust_binary, frozen_root)


@pytest.fixture(scope="module")
def work(tmp_path_factory: pytest.TempPathFactory, frozen_root: Path) -> tuple[Path, Path]:
    """One copy of the whole frozen tree and one build directory: each run restores its file."""
    root = tmp_path_factory.mktemp("work")
    shutil.copytree(frozen_root, root / "tree", ignore=shutil.ignore_patterns(".git"))
    target = tmp_path_factory.mktemp("target")
    assert not _failing_files(root / "tree", target), "the unchanged tree must compile"
    return root / "tree", target


def _candidates() -> list[Any]:
    """Each production file with impl blocks of one kind: a trait impl or an inherent impl."""
    root = Path(__file__).resolve().parents[1]
    found = []
    for path in sorted((root / "native").glob("*/src/**/*.rs")):
        relative = path.relative_to(root).as_posix()
        if path.name.endswith("_tests.rs") or "/tests/" in relative or path.name == "build.rs":
            continue
        kinds = {is_trait for _, is_trait in _impl_blocks(path.read_text())}
        found += [
            pytest.param(relative, kind, id=f"{'trait' if kind else 'inherent'}-impls-{relative}")
            for kind in sorted(kinds)
        ]
    return found


@pytest.mark.parametrize(("relative", "trait"), _candidates())
def test_each_file_that_fails_without_the_impls_of_a_file_is_held_against_it(
    relative: str, trait: bool, facts: dict[str, Any], work: tuple[Path, Path]
) -> None:
    tree, target = work
    path = tree / relative
    original = path.read_text()
    blocks = [block for block, is_trait in _impl_blocks(original) if is_trait == trait]
    held = Held(facts)
    try:
        path.write_text(_without(original, blocks))
        failing = _failing_files(tree, target)
    finally:
        path.write_text(original)
    others = [other for other in sorted(failing - {relative}) if other in held.modules]
    unreached = [other for other in others if not held.reaches(other, relative)]
    assert not unreached, f"the compiler fails in {unreached} without the impls of {relative}"
    direct_only = [other for other in others if not held.holds(other, relative)]
    assert direct_only == DIRECT_ONLY.get(relative, []), relative


def test_the_scanner_finds_the_top_level_impl_blocks_and_their_kind() -> None:
    text = (
        'const S: &str = "impl A for B { ";\n'  # 0
        "// impl C for D {\n"  # 1
        "fn f() -> impl Iterator<Item = u8> { 0..1 }\n"  # 2
        "/// Doc.\n"  # 3
        "#[derive(Clone)]\n"  # 4
        "impl<T: for<'a> Fn(&'a u8)> Tr for X<T> where T: Copy {\n"  # 5
        "    fn g(&self) { let c = '{'; }\n"  # 6
        "}\n"  # 7
        "impl X<u8> {\n"  # 8
        "    fn h(&self) {}\n"  # 9
        "}\n"  # 10
        "mod m { impl Y for Z {} }\n"  # 11
    )
    assert _impl_blocks(text) == [((5, 7), True), ((8, 10), False)]
    assert _without(text, [(5, 7)]).count("\n") == text.count("\n") - 5
