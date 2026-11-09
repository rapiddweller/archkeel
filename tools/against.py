# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Select the changed amendment and run the existing widening validator.

With `--refresh` it instead rewrites the digests of the amendments a branch adds or changes
(epic #880). Each merge on main makes those digests stale. The refresh asks the validator to
write the binding again (`--write-amendment`) with the `decided_by` and `rationale` the record
already holds, so one owner computes the digests.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from archkeel.check.git import GitError, changed_paths, git_bytes, read_blob
from archkeel.check.snapshot import SnapshotError, resolve_commit


def changed_amendments(root: Path, base: str, head: str) -> list[str]:
    """The amendment records that `head` adds, changes or deletes relative to `base`."""
    return sorted(
        path
        for path in changed_paths(root, base, head)
        if Path(path).parent.as_posix() == "docs/architecture/decisions"
        and path.endswith("-amendment.json")
    )


def validate_command(base: str, amendment: str | None) -> list[str]:
    """The validate command of `make against`; the refresh tool adds its write flags."""
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
    return command


def select_amendment(root: Path, base: str, head: str) -> str | None:
    paths = changed_amendments(root, base, head)
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


def _text_field(record: object, key: str, path: str) -> str:
    value = record.get(key) if isinstance(record, dict) else None
    if not isinstance(value, str) or not value:
        raise GitError(f"amendment has no {key} to keep: {path}")
    return value


def refresh(root: Path, base: str, head: str = "HEAD") -> list[str]:
    """Rewrite the changed amendments in `root`; return the paths whose bytes changed."""
    if git_bytes(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise GitError("the working tree is not clean: commit or remove the changes first")
    base = resolve_commit(root, base)
    head = resolve_commit(root, head)
    changed: list[str] = []
    for path in changed_amendments(root, base, head):
        target = root / path
        if not target.is_file():
            continue  # The branch deletes this record: nothing to bind.
        before = target.read_bytes()
        try:
            record = json.loads(before)
        except ValueError as error:
            raise GitError(f"amendment is not valid JSON: {path}: {error}") from error
        command = validate_command(base, path) + [
            "--write-amendment",
            "--decided-by",
            _text_field(record, "decided_by", path),
            "--rationale",
            _text_field(record, "rationale", path),
        ]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)
        if result.returncode == 2:
            raise GitError(f"the validator could not bind {path}:\n{result.stdout}{result.stderr}")
        if target.read_bytes() != before:
            changed.append(path)
    return changed


def _refresh_command(root: Path, base: str) -> int:
    try:
        changed = refresh(root, base)
    except (ValueError, OSError, SnapshotError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for path in changed:
        print(f"rewrote the digests of {path}")
    if not changed:
        print("no amendment digest changed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--refresh", action="store_true", help="rewrite stale amendment digests")
    args = parser.parse_args()
    root = Path.cwd()
    if args.refresh:
        return _refresh_command(root, args.base)
    try:
        base = resolve_commit(root, args.base)
        head = resolve_commit(root, "HEAD")
        amendment = select_amendment(root, base, head)
    except (ValueError, OSError, SnapshotError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return subprocess.call(validate_command(base, amendment))


if __name__ == "__main__":
    raise SystemExit(main())
