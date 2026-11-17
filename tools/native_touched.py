# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name the Rust crates that a change touches, for the lint of the PR gate (AD-756).

`python tools/native_touched.py <base-ref>` reads `git diff --name-only --no-renames
<base-ref>...HEAD` and prints one line for `make pr-native-lint`:

- nothing: the change does not touch `native/`, so no Rust lint runs;
- `-`: `native/` changed but no crate (a pin or a data file): only `cargo fmt --check` runs;
- `--workspace`: `Cargo.toml`, `Cargo.lock`, the toolchain or `clippy.toml` changed;
- `-p <name> -p <name>`: the crates whose directory holds a changed file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

WORKSPACE_FILES = {
    "native/Cargo.toml",
    "native/Cargo.lock",
    "native/rust-toolchain.toml",
    "native/clippy.toml",
}


def crate_dirs(metadata: dict) -> dict[str, str]:
    """Directory (relative to the repository, with a trailing slash) -> package name."""
    root = Path(metadata["workspace_root"]).parent
    found = {}
    for package in metadata["packages"]:
        directory = Path(package["manifest_path"]).parent.relative_to(root).as_posix()
        found[directory + "/"] = package["name"]
    return found


def selection(changed: list[str], crates: dict[str, str]) -> str:
    """The line to print for the changed paths."""
    native = [path for path in changed if path.startswith("native/")]
    if not native:
        return ""
    if any(path in WORKSPACE_FILES for path in native):
        return "--workspace"
    names = set()
    for path in native:
        owner = next(
            (name for directory, name in crates.items() if path.startswith(directory)), None
        )
        if owner is not None:
            names.add(owner)
    if not names:
        return "-"
    return " ".join(f"-p {name}" for name in sorted(names))


def main(argv: list[str]) -> int:
    diff = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{argv[0]}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    changed = [line for line in diff.stdout.splitlines() if line]
    if not any(path.startswith("native/") for path in changed):
        print("")
        return 0
    metadata = json.loads(
        subprocess.run(
            ["cargo", "metadata", "--format-version", "1", "--no-deps", "--locked"],
            cwd="native",
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    print(selection(changed, crate_dirs(metadata)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
