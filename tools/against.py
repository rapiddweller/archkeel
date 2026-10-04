# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Select the changed amendment and run the existing widening validator."""

import argparse
import subprocess
import sys
from pathlib import Path

from archkeel.check.git import GitError, changed_paths, read_blob
from archkeel.check.snapshot import SnapshotError, resolve_commit


def select_amendment(root: Path, base: str, head: str) -> str | None:
    paths = sorted(
        path
        for path in changed_paths(root, base, head)
        if Path(path).parent.as_posix() == "docs/architecture/decisions"
        and path.endswith("-amendment.json")
    )
    if not paths:
        return None
    if len(paths) != 1:
        raise GitError("exactly one changed amendment is allowed")
    path = paths[0]
    data = read_blob(root, head, path)
    current = root / path
    if current.is_symlink() or not current.is_file() or current.read_bytes() != data:
        raise GitError(f"amendment is not the checked-out regular Git blob: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    root = Path.cwd()
    try:
        base = resolve_commit(root, args.base)
        head = resolve_commit(root, "HEAD")
        amendment = select_amendment(root, base, head)
    except (ValueError, OSError, SnapshotError) as error:
        print(str(error), file=sys.stderr)
        return 2
    command = [
        sys.executable,
        "-m",
        "archkeel.cli",
        "validate",
        "--root",
        ".",
        "--baseline",
        "architecture-baseline.json",
        "--json",
        "--against",
        base,
    ]
    if amendment is not None:
        command += ["--amendment", amendment]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
