# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-590: every Rust module states its responsibility, and no module is named `utils`."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
TRACKED = tuple(
    name
    for name in subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--deduplicate", "-z"],
        cwd=ROOT,
        text=True,
    ).split("\0")
    if name and (ROOT / name).is_file()
)
BANNED = {"util", "utils", "common", "helper", "helpers", "misc", "shared"}
RUST_MOD = re.compile(r"^\s*(?:pub(?:\([a-z]+\))?\s+)?mod\s+(\w+)", re.MULTILINE)
CRATE_NAME = re.compile(r'^name\s*=\s*"([^"]+)"', re.MULTILINE)


def _is_rust_test_file(name: str) -> bool:
    return (
        name.endswith(("_tests.rs", "/tests.rs", "/build.rs"))
        or "/tests/" in name
        or "/testdata/" in name
    )


def _first_content_line(text: str) -> str:
    """The first line that is neither blank nor a plain `//` comment (the licence header)."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not (stripped.startswith("//") and not stripped.startswith("//!")):
            return stripped
        if stripped.startswith("//!"):
            return stripped
    return ""


def test_every_native_module_starts_with_a_responsibility_line() -> None:
    sources = [
        name
        for name in TRACKED
        if name.startswith("native/") and name.endswith(".rs") and not _is_rust_test_file(name)
    ]
    assert sources
    missing = [
        name
        for name in sources
        if not _first_content_line((ROOT / name).read_text(encoding="utf-8")).startswith("//!")
    ]
    assert missing == [], "Start each file below with a `//!` line that names its responsibility."


def test_no_module_or_crate_is_named_like_a_junk_drawer() -> None:
    """A helper lives in the component that owns its meaning (CONTRIBUTING.md, AD-590)."""
    problems: list[str] = []
    for name in TRACKED:
        path = Path(name)
        owned = name.startswith("native/") or (
            name.startswith(("src/", "tests/"))
            and not name.startswith("tests/golden/")
            and path.suffix == ".py"
        )
        if not owned:
            continue
        if path.suffix in {".rs", ".py"}:
            parts = [*path.parent.parts, path.stem]
            problems += [f"{name}: `{p}`" for p in parts if p.lower() in BANNED]
        if path.suffix == ".rs":
            text = (ROOT / name).read_text(encoding="utf-8")
            problems += [
                f"{name}: mod `{m}`" for m in RUST_MOD.findall(text) if m.lower() in BANNED
            ]
        if path.name == "Cargo.toml" and name.startswith("native/"):
            text = (ROOT / name).read_text(encoding="utf-8")
            crate = CRATE_NAME.search(text)
            if crate and crate.group(1).lower().removeprefix("archkeel-") in BANNED:
                problems.append(f"{name}: crate `{crate.group(1)}`")
    assert problems == [], "\n".join(problems)
