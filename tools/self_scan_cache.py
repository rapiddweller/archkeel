# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A result cache of the self-scan (AD-1400). It is not a comparison and not a gate.

The result of `archkeel report --config docs/architecture/architecture-system.json` is a pure
function of the files that the scan reads and of the core that reads them. This tool keys a
saved result by a hash of exactly those inputs, so a pull request that changes none of them
reuses the result of main. The gate then judges the reused result as it judges a fresh one
(`tools/self_check_gate.py`).

Run: `python tools/self_scan_cache.py key|save|hit ...`.

- `key`: print the prefix of the cache key, `selfscan-v1-<static hash>-`. The static inputs are
  the directories that the parts scan or build from (`native/`, `src/`, `studio/`, `schema/`,
  `tools/rustc-facts/`, `.archkeel/`), the files that decide the scan (`archkeel.toml`, every
  `*contract*.json`, `rust-toolchain*`, `pyproject.toml`, `uv.lock`, `Makefile`, the system
  document and the shell configuration), every `.cargo` file and every link of the repository
  (the Rust walk reads them wherever they stand). Each file counts with its content, so a
  changed byte changes the key. - `save --result R --dir D`: write `D/entry.json` and
  `D/result.json` for a result that is complete. The entry also lists the documents that the
  scan read: the files that the core bound (`contract_files`) and every path that a contract
  cites. The tool refuses (exit 1, nothing written) when the result does not show that its
  inputs are covered: a scanned file outside the static directories, a topology that does not
  list every module, a part whose configuration is not a static input, or a tree too large to
  hash. - `hit --dir D --out R`: reuse `D/result.json` as `R` when the entry is of this static
  key and every document of the entry has the content that it had. Any other case, and any
  error, exit 1: the caller scans.

A hit needs no scan; a miss is the scan of today. The tool never decides a verdict.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

VERSION = 1
# A part of the system or the build of the core can read everything below these directories.
STATIC_DIRS = ("native/", "src/", "studio/", "schema/", "tools/rustc-facts/", ".archkeel/")
STATIC_FILES = (
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    "docs/architecture/architecture-system.json",
    "docs/architecture/shell.toml",
)
# The tree is hashed file by file: a larger tree is not hashed, so the caller scans.
MAX_FILES = 200_000
MAX_DEPTH = 100


class Uncovered(Exception):
    """The inputs of the scan cannot be named or hashed: the caller scans."""


def tracked(root: Path) -> list[tuple[str, str]]:
    """The files of the work tree as (mode, path): tracked or not yet added, never ignored."""
    cached = subprocess.run(["git", "ls-files", "--stage", "-z"], capture_output=True, cwd=root)
    others = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], capture_output=True, cwd=root
    )
    if cached.returncode != 0 or others.returncode != 0:
        raise Uncovered("git ls-files failed")
    rows: dict[str, str] = {}
    for item in cached.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        meta, _, path = item.partition("\t")
        if path:
            rows[path] = meta.split()[0]
    for path in others.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if path:
            rows.setdefault(path, "120000" if (root / path).is_symlink() else "100644")
    if len(rows) > MAX_FILES:
        raise Uncovered("the tree is larger than the limit")
    if any(len(path.split("/")) > MAX_DEPTH for path in rows):
        raise Uncovered("a path is deeper than the limit")
    return sorted((mode, path) for path, mode in rows.items())


def is_static(path: str, mode: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (
        path.startswith(STATIC_DIRS)
        or path in STATIC_FILES
        or mode == "120000"
        or ".cargo" in parts
        or name == "archkeel.toml"
        or (name.endswith(".json") and "contract" in name)
        or name.startswith("rust-toolchain")
    )


def content(root: Path, path: str, mode: str) -> str:
    """The identity of a file: its bytes or its link target; a missing file has its own word."""
    target = root / path
    try:
        if mode == "120000" or target.is_symlink():
            return "link:" + os.readlink(target)
        if target.is_dir():
            # A cited directory counts by the names in it: the core asks whether the path exists.
            names = "\0".join(sorted(os.listdir(target)))
            return (
                "dir:" + hashlib.sha256(names.encode("utf-8", errors="surrogateescape")).hexdigest()
            )
        return "file:" + hashlib.sha256(target.read_bytes()).hexdigest()
    except (FileNotFoundError, NotADirectoryError):
        return "absent"
    except OSError as error:
        if error.errno in (errno.ENAMETOOLONG, errno.ELOOP):
            return "absent"
        raise Uncovered(f"cannot read {path}: {error.strerror}") from error


def digest(pairs: list[tuple[str, str]]) -> str:
    text = "\n".join(f"{path}\t{ident}" for path, ident in pairs)
    return hashlib.sha256(text.encode("utf-8", errors="surrogateescape")).hexdigest()


def static_hash(root: Path) -> str:
    files = tracked(root)
    pairs = [(path, content(root, path, mode)) for mode, path in files if is_static(path, mode)]
    if not pairs:
        raise Uncovered("no static input found")
    # The count of the files below the Rust walk counts too: a new file elsewhere changes no key.
    return digest(pairs)


def cited(root: Path, contracts: list[str]) -> set[str]:
    """Every string of the given contracts that the core could read as a repository path."""

    def walk(value: Any) -> set[str]:
        if isinstance(value, str):
            return {value} if normal(value) else set()
        items = (
            value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
        )
        return set().union(*(walk(item) for item in items)) if items else set()

    found: set[str] = set()
    for name in contracts:
        try:
            found |= walk(json.loads((root / name).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return found


def normal(text: str) -> bool:
    """A mirror of `normal()` in `native/core/src/provenance.rs`; a wider rule reads more files."""
    return (
        bool(text)
        and not any(char in text for char in "\\:\0")
        and all(part not in ("", ".", "..") for part in text.split("/"))
    )


def documents(root: Path, result: dict[str, Any], files: list[tuple[str, str]]) -> dict[str, str]:
    """The documents that the scan read and that are no static input, with their content."""
    modes = {path: mode for mode, path in files}
    bound = (result.get("self_test") or {}).get("collect", {}).get("contract_files")
    if not isinstance(bound, dict) or not bound:
        raise Uncovered("the result names no bound contract file")
    contracts = [
        path for path, mode in modes.items() if is_static(path, mode) and path.endswith(".json")
    ]
    names = {path for path in bound if isinstance(path, str)} | cited(root, contracts)
    return {
        path: content(root, path, modes.get(path, "100644"))
        for path in sorted(names)
        if not is_static(path, modes.get(path, "100644"))
    }


def covered(result: dict[str, Any], files: list[tuple[str, str]]) -> None:
    """Refuse a result whose inputs the key does not cover: the proof of what a part reads."""
    modes = {path: mode for mode, path in files}
    topology = result.get("topology")
    if not isinstance(topology, dict) or not topology.get("modules"):
        raise Uncovered("the topology is missing")
    total = (topology.get("total") or {}).get("modules")
    if total != len(topology["modules"]):
        raise Uncovered("the topology does not list every module")
    for module in topology["modules"]:
        path = module.get("path")
        if not isinstance(path, str) or not is_static(path, modes.get(path, "100644")):
            raise Uncovered(f"a scanned file is no static input: {path}")
    system = result.get("system")
    if not isinstance(system, dict) or not system.get("parts"):
        raise Uncovered("the result is no system run")
    for part in system["parts"]:
        config = part.get("config")
        if not isinstance(config, str) or not is_static(config, modes.get(config, "100644")):
            raise Uncovered(f"the configuration of a part is no static input: {config}")
    document = system.get("document")
    if not isinstance(document, str) or not is_static(document, modes.get(document, "100644")):
        raise Uncovered("the system document is no static input")
    if not result.get("rules"):
        raise Uncovered("the result has no rules")


def prefix(root: Path) -> str:
    return f"selfscan-v{VERSION}-{static_hash(root)}-"


def save(root: Path, result_path: Path, directory: Path) -> str:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or result.get("refusal"):
        raise Uncovered("the result is missing or a refusal")
    files = tracked(root)
    covered(result, files)
    docs = documents(root, result, files)
    entry = {
        "version": VERSION,
        "static": static_hash(root),
        "documents": docs,
    }
    entry["key"] = f"selfscan-v{VERSION}-{entry['static']}-{digest(sorted(docs.items()))}"
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(result_path, directory / "result.json")
    (directory / "entry.json").write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")
    return str(entry["key"])


def hit(root: Path, directory: Path, out: Path) -> str:
    entry = json.loads((directory / "entry.json").read_text(encoding="utf-8"))
    if entry.get("version") != VERSION or entry.get("static") != static_hash(root):
        raise Uncovered("the saved inputs are not these inputs")
    files = {path: mode for mode, path in tracked(root)}
    saved = entry.get("documents")
    if not isinstance(saved, dict):
        raise Uncovered("the entry lists no documents")
    for path, ident in saved.items():
        if not isinstance(path, str) or content(root, path, files.get(path, "100644")) != ident:
            raise Uncovered(f"a document differs: {path}")
    result = directory / "result.json"
    if not result.is_file():
        raise Uncovered("the entry has no result")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(result, out)
    return str(entry.get("key"))


def option(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1] if name in argv else ""


def main(argv: list[str]) -> int:
    root = Path(option(argv, "--root") or ".").resolve()
    try:
        if argv[:1] == ["key"]:
            print(prefix(root))
        elif argv[:1] == ["save"]:
            print(save(root, Path(option(argv, "--result")), Path(option(argv, "--dir"))))
        elif argv[:1] == ["hit"]:
            key = hit(root, Path(option(argv, "--dir")), Path(option(argv, "--out")))
            print(f"self-scan: reused the result of {key}")
        else:
            print("usage: self_scan_cache.py key|save|hit", file=sys.stderr)
            return 2
    except (Uncovered, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"self-scan cache: {argv[:1]}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
