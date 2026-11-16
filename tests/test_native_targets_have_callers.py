# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each example, binary and feature of `native/` has a caller (prevention bundle, measure 6).

The compiler cannot see a dead example: an example is a crate of its own, it builds, and it keeps
each public item that it calls alive. Five contract parity probes stayed in `native/contract/
examples/` after their tests were deleted (511 lines, ARCH-HYGIENE-AUDIT section 4). The same holds
for a binary and for a feature that no build enables.

A caller is a file that runs or builds the target: the Makefile and its fragments, a tool, a test,
a workflow, the build hook of the wheel, the shell that starts a binary, or another manifest that
enables the feature. An example or a binary is called when a caller names it; a feature is called
when a caller enables it by name (`--features`, `features = [...]`, or a quoted name).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
NATIVE = ROOT / "native"
CALLER_GLOBS = (
    "Makefile",
    "tools/**/*.mk",
    "tests/**/*.mk",
    "tools/**/*.py",
    "tests/**/*.py",
    ".github/workflows/*.yml",
    "src/**/*.py",
    "native/hatch_build.py",
    "native/*/Cargo.toml",
)
PACKAGE = re.compile(r'^\[package\]\s*\nname\s*=\s*"([^"]+)"', re.MULTILINE)
BIN = re.compile(r'^\[\[bin\]\]\s*\nname\s*=\s*"([^"]+)"', re.MULTILINE)
FEATURES = re.compile(r"^\[features\]\s*\n((?:[^\[\n][^\n]*\n|\n)*)", re.MULTILINE)
FEATURE = re.compile(r"^([A-Za-z0-9_-]+)\s*=", re.MULTILINE)
THIS = Path(__file__).relative_to(ROOT).as_posix()


def tracked(root: Path) -> set[str]:
    listed = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root, text=True
    )
    return {name for name in listed.split("\0") if name}


def targets(root: Path) -> dict[str, list[tuple[str, str]]]:
    """Each example, binary and feature of each crate, by manifest: (kind, name)."""
    found: dict[str, list[tuple[str, str]]] = {}
    for manifest in sorted((root / "native").glob("*/Cargo.toml")):
        text = manifest.read_text(encoding="utf-8")
        crate = manifest.parent
        rows = [("example", path.stem) for path in sorted(crate.glob("examples/*.rs"))]
        package = PACKAGE.search(text)
        if package and (crate / "src/main.rs").is_file():
            rows.append(("binary", package.group(1)))
        rows += [("binary", path.stem) for path in sorted(crate.glob("src/bin/*.rs"))]
        rows += [("binary", name) for name in BIN.findall(text)]
        section = FEATURES.search(text)
        if section:
            rows += [("feature", name) for name in FEATURE.findall(section.group(1))]
        found[manifest.relative_to(root).as_posix()] = sorted(set(rows))
    return found


def callers(root: Path, manifest: str) -> str:
    """The text of each caller file, except the manifest itself and this test."""
    files = tracked(root)
    names = {
        path.relative_to(root).as_posix() for pattern in CALLER_GLOBS for path in root.glob(pattern)
    }
    keep = sorted(name for name in names & files if name not in {manifest, THIS})
    return "\n".join((root / name).read_text(encoding="utf-8") for name in keep)


def called(kind: str, name: str, text: str) -> bool:
    word = re.escape(name)
    if kind == "feature":
        enabled = (
            rf"--features[ =][\w,-]*\b{word}\b|features\s*=\s*\[[^\]]*\"{word}\"|[\"']{word}[\"']"
        )
        return re.search(enabled, text) is not None
    return re.search(rf"(?<![\w-]){word}(?![\w-])", text) is not None


def uncalled(root: Path) -> list[str]:
    return [
        f"{manifest}: {kind} {name} has no caller"
        for manifest, rows in targets(root).items()
        for kind, name in rows
        if not called(kind, name, callers(root, manifest))
    ]


def test_each_example_binary_and_feature_of_native_has_a_caller() -> None:
    assert uncalled(ROOT) == []


def test_the_scan_reads_the_example_the_binaries_and_the_features() -> None:
    rows = {row for found in targets(ROOT).values() for row in found}
    assert ("example", "tree_digest") in rows
    assert ("binary", "archkeel-core") in rows
    assert ("feature", "dump") in rows


def _repository(tmp_path: Path, callers_text: str) -> Path:
    crate = tmp_path / "native/probe"
    (crate / "examples").mkdir(parents=True)
    (crate / "src").mkdir()
    (crate / "Cargo.toml").write_text(
        '[package]\nname = "archkeel-probe"\nversion = "0.0.0"\n\n'
        "[features]\n# A note.\ndump = []\n"
    )
    (crate / "src/lib.rs").write_text("")
    (crate / "src/main.rs").write_text("fn main() {}\n")
    (crate / "examples/contract_dump.rs").write_text("fn main() {}\n")
    (tmp_path / "Makefile").write_text(callers_text)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_a_dead_example_binary_and_feature_fail(tmp_path: Path) -> None:
    root = _repository(tmp_path, "all:\n\techo nothing\n")
    assert uncalled(root) == [
        "native/probe/Cargo.toml: binary archkeel-probe has no caller",
        "native/probe/Cargo.toml: example contract_dump has no caller",
        "native/probe/Cargo.toml: feature dump has no caller",
    ]


def test_a_called_example_binary_and_feature_pass(tmp_path: Path) -> None:
    text = (
        "all:\n\tcargo run --example contract_dump\n\tcargo build --features dump\n"
        "\t./target/debug/archkeel-probe\n"
    )
    assert uncalled(_repository(tmp_path, text)) == []


def test_a_longer_name_or_a_comment_word_is_no_call() -> None:
    assert not called("example", "contract_dump", "contract_dump_v2 and contract-dump-x")
    assert not called("feature", "dump", "a dump of the tree")
    assert called("feature", "dump", 'features = ["dump"]')
    assert called("feature", "dump", "--features dump,harness")
