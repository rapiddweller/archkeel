# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The pinned source of a real project, fetched when the gallery builds (AD-462).

A fixture of a third-party project holds only our own files (contract, config, graph) and a
`SOURCE.json` that names the pin: repository, release, commit and licence. The source itself is
never committed. `checkout` fetches that exact commit with a shallow Git fetch into a cache folder.
A fetch that fails is an error and never a half result: the cache holds only a complete checkout
(it is moved into place after the fetch), so a failed build can never publish a page with a
silently missing project. A cached checkout is used only after `verify_checkout` shows that its
bytes are the pinned commit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SOURCE = "SOURCE.json"
ATTEMPTS = 3
# Seconds to wait after the first and the second failed fetch: a short outage of the host or a rate
# limit often ends within seconds. The last failure raises at once, with its reason.
BACKOFF = (5, 15)
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


def _git_env() -> dict[str, str]:
    """The environment of Git here: none of the GIT_* variables that could point it elsewhere."""
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _git_objects(git_dir: Path, *arguments: str) -> bytes:
    """Git on the object store of a cached checkout, with no replacement refs."""
    done = subprocess.run(
        ["git", "--no-replace-objects", "--git-dir", str(git_dir), *arguments],
        capture_output=True,
        timeout=TIMEOUT,
        check=False,
        env=_git_env(),
    )
    if done.returncode:
        raise SourceError(
            f"git {arguments[0]}: {done.stderr.decode(errors='replace').strip()[:200]}"
        )
    return done.stdout


def _records_modes(git_dir: Path) -> bool:
    """True when the checkout can say what Git says of the executable bit: a POSIX file system
    whose checkout recorded `core.filemode` (a file system without the bit sets it false)."""
    if os.name != "posix":
        return False
    done = subprocess.run(
        ["git", "--git-dir", str(git_dir), "config", "--bool", "core.filemode"],
        capture_output=True,
        timeout=TIMEOUT,
        check=False,
        env=_git_env(),
    )
    return done.stdout.strip() != b"false"


def _blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


_LINK, _PLAIN, _RUNS = "120000", "100644", "100755"


def _tracked(git_dir: Path, commit: str) -> dict[str, tuple[str, str]]:
    """Each file of the commit, by path, with its Git mode and blob id: read from the verified
    objects. A mode other than a file, an executable or a link is an error."""
    found: dict[str, tuple[str, str]] = {}
    for entry in _git_objects(git_dir, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        mode, kind, blob = meta.decode().split()
        if kind != "blob" or mode not in (_LINK, _PLAIN, _RUNS):
            raise SourceError(f"the pinned commit holds {mode} {path.decode(errors='replace')}")
        found[path.decode()] = (mode, blob)
    return found


def _on_disk(path: Path) -> tuple[str, bytes]:
    """The kind of a file in the folder and its bytes, without following a link: `_LINK` and the
    bytes of the link target, `_PLAIN` or `_RUNS` and the bytes of a regular file, or `other`."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return _LINK, os.fsencode(os.readlink(path))
    if not stat.S_ISREG(info.st_mode):
        return "other", b""
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        data = stream.read()
    return (_RUNS if info.st_mode & stat.S_IXUSR else _PLAIN), data


def verify_checkout(ready: Path, commit: str) -> None:
    """Refuse a cached checkout whose bytes are not the pinned commit (#659 review).

    The folder name and `HEAD` prove nothing: a working file can be changed, added or ignored. So
    the object store is checked (`git fsck` hashes each object; no alternates, no replacement refs),
    the commit must be the pin, and the files of the folder must be exactly the files of that
    commit, each with the content hash of its blob. A damaged or changed cache is an error: it is
    not repaired, deleted or fetched again here."""
    git_dir = ready / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        raise SourceError(f"{ready.name} is not a git checkout: no folder .git")
    if (git_dir / "objects" / "info" / "alternates").exists():
        raise SourceError(f"{ready.name} borrows objects from another store")
    _git_objects(git_dir, "fsck", "--no-dangling", "--no-progress")
    head = _git_objects(git_dir, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if head != commit:
        raise SourceError(f"{ready.name} is at {head}, the pin is {commit}")
    expected = _tracked(git_dir, commit)
    modes = _records_modes(git_dir)
    found: dict[str, tuple[str, bytes]] = {}
    for folder, names, files in os.walk(ready):
        if Path(folder) == ready:
            names[:] = [name for name in names if name != ".git"]
        # A link to a folder is listed with the folders; it is a file of the commit.
        for name in [*files, *(name for name in names if (Path(folder) / name).is_symlink())]:
            path = Path(folder) / name
            found[path.relative_to(ready).as_posix()] = _on_disk(path)
    odd = sorted(set(found) ^ set(expected))
    changed = sorted(
        name for name in set(found) & set(expected) if not _same(expected[name], found[name], modes)
    )
    if odd or changed:
        names = [*odd, *changed][:5]
        raise SourceError(
            f"{ready.name} differs from the pinned commit ({len(odd)} added or missing, "
            f"{len(changed)} changed in bytes, type or mode), for example {', '.join(names)}"
        )


def _same(expected: tuple[str, str], found: tuple[str, bytes], modes: bool) -> bool:
    """A file of the folder is the file of the commit: the same type (a link only for a link, a
    regular file only for a file), the same bytes, and the same executable bit where the checkout
    records it."""
    (mode, blob), (kind, data) = expected, found
    if (mode == _LINK) != (kind == _LINK) or kind == "other":
        return False
    if modes and mode != _LINK and mode != kind:
        return False
    return _blob_id(data) == blob


@contextmanager
def checkout(spec: Mapping[str, Any], cache: Path | None = None) -> Iterator[Path]:
    """The pinned commit as a folder. A cache folder keeps the checkout for the next build. A
    cached checkout is verified against the pin before use (`verify_checkout`), never silently
    fixed."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", spec["repo"].split("//", 1)[-1]).strip("-")
    with tempfile.TemporaryDirectory(prefix="archkeel-source-") as scratch:
        if cache is not None:
            cache.mkdir(parents=True, exist_ok=True)
        home = cache if cache is not None else Path(scratch)
        ready = home / f"{slug}-{spec['commit']}"
        if not ready.is_dir():
            error: SourceError | None = None
            for attempt in range(ATTEMPTS):
                if attempt:
                    time.sleep(BACKOFF[min(attempt, len(BACKOFF)) - 1])
                partial = Path(scratch) / "partial"
                shutil.rmtree(partial, ignore_errors=True)
                try:
                    _fetch(spec, partial)
                except (SourceError, OSError, subprocess.TimeoutExpired) as err:
                    error = SourceError(str(err))
                    continue
                # A new name in the cache folder, then one rename: two builds that fetch the same
                # pin never put one folder into the other.
                staging = home / f".{ready.name}.{uuid.uuid4().hex}"
                shutil.move(str(partial), staging)
                try:
                    os.rename(staging, ready)
                except OSError:
                    shutil.rmtree(staging, ignore_errors=True)
                    if not ready.is_dir():
                        raise
                error = None
                break
            if error is not None:
                raise error
        verify_checkout(ready, spec["commit"])
        yield ready


def _through_a_link(checked: Path, path: Path) -> bool:
    """Whether a part of `path` below `checked` is a link: a link in the way would take the copy
    to bytes that the verified tree does not hold."""
    parts = path.relative_to(checked).parts
    return any(checked.joinpath(*parts[: i + 1]).is_symlink() for i in range(len(parts)))


def _refuse_links_out(root: Path, target: Path) -> None:
    """A link that the copy brought into the fixture must point inside the fixture. An absolute
    target, or a relative one that leaves `root`, would let the scan read what the pin does not
    hold. The link itself is copied as a link, never followed."""
    for folder, names, files in os.walk(target):
        for name in [*files, *names]:
            path = Path(folder) / name
            if not path.is_symlink():
                continue
            link = os.readlink(path)
            inside = os.path.normpath(os.path.join(path.parent.relative_to(root), link))
            if os.path.isabs(link) or inside == ".." or inside.startswith(".." + os.sep):
                raise SourceError(f"the link {path.relative_to(root)} -> {link} leaves the source")


def copy_source(checked: Path, spec: Mapping[str, Any], root: Path) -> None:
    """Copy the parts of the checkout that the scan reads into the copy of the fixture. A copied
    path must not be or go through a link, and a link inside it must point inside the fixture."""
    for item in spec["copy"]:
        source = checked / item["from"]
        target = root / item["to"]
        if not os.path.lexists(source):
            raise SourceError(f"the pinned commit has no {item['from']}")
        if _through_a_link(checked, source):
            raise SourceError(f"{item['from']} is or goes through a link: it is not copied")
        ignore = shutil.ignore_patterns(".git", *item.get("exclude", []))
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True, ignore=ignore)
            _refuse_links_out(root, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
