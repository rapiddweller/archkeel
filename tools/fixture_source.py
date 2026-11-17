# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The pinned source of a real project, fetched when the gallery builds (AD-462).

A fixture of a third-party project holds only our own files (contract, config, graph) and a
`SOURCE.json` that names the pin: repository, release, commit and licence. The source itself is
never committed. `checkout` fetches that exact commit with a shallow Git fetch into a cache folder.
A fetch that fails is an error and never a half result: the cache holds only a complete checkout
(it is moved into place after the fetch), so a failed build can never publish a page with a
silently missing project.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SOURCE = "SOURCE.json"
ATTEMPTS = 3
TIMEOUT = 300


class SourceError(RuntimeError):
    """The pinned source could not be fetched. The build must fail; it never skips the project."""


def load(fixture: Path) -> dict[str, Any] | None:
    """The pin of a fixture, or None when the fixture holds its own source."""
    path = fixture / SOURCE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def pin_facts(spec: Mapping[str, Any]) -> dict[str, str]:
    """The facts that a card states: name, repository, release, licence and the short commit."""
    return {
        "name": spec["name"],
        "repo": spec["repo"],
        "ref": spec.get("ref") or "",
        "license": spec["license"],
        "commit": spec["commit"],
    }


def _run(arguments: list[str], cwd: Path) -> None:
    done = subprocess.run(
        arguments, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT, check=False
    )
    if done.returncode:
        raise SourceError(f"{' '.join(arguments[:3])}: {done.stderr.strip()[:200]}")


def _fetch(spec: Mapping[str, Any], target: Path) -> None:
    """One shallow fetch of the exact commit into `target`, which is checked out detached."""
    target.mkdir(parents=True)
    _run(["git", "init", "-q"], target)
    _run(["git", "remote", "add", "origin", spec["repo"]], target)
    _run(["git", "fetch", "-q", "--depth", "1", "origin", spec["commit"]], target)
    _run(["git", "checkout", "-q", "--detach", "FETCH_HEAD"], target)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=target, capture_output=True, text=True, check=False
    )
    if head.stdout.strip() != spec["commit"]:
        raise SourceError(f"fetched {head.stdout.strip()}, the pin is {spec['commit']}")


@contextmanager
def checkout(spec: Mapping[str, Any], cache: Path | None = None) -> Iterator[Path]:
    """The pinned commit as a folder. A cache folder keeps the checkout for the next build."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", spec["repo"].split("//", 1)[-1]).strip("-")
    with tempfile.TemporaryDirectory(prefix="archkeel-source-") as scratch:
        if cache is not None:
            cache.mkdir(parents=True, exist_ok=True)
        home = cache if cache is not None else Path(scratch)
        ready = home / f"{slug}-{spec['commit']}"
        if not ready.is_dir():
            error: SourceError | None = None
            for _ in range(ATTEMPTS):
                partial = Path(scratch) / "partial"
                shutil.rmtree(partial, ignore_errors=True)
                try:
                    _fetch(spec, partial)
                except (SourceError, OSError, subprocess.TimeoutExpired) as err:
                    error = SourceError(str(err))
                    continue
                shutil.move(str(partial), ready)
                error = None
                break
            if error is not None:
                raise error
        yield ready


def copy_source(checked: Path, spec: Mapping[str, Any], root: Path) -> None:
    """Copy the parts of the checkout that the scan reads into the copy of the fixture."""
    for item in spec["copy"]:
        source = checked / item["from"]
        target = root / item["to"]
        if not source.exists():
            raise SourceError(f"the pinned commit has no {item['from']}")
        ignore = shutil.ignore_patterns(".git", *item.get("exclude", []))
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True, ignore=ignore)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
