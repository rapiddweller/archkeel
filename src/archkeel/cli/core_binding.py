# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bind a scan frame to its files and request identity. This module reads no rules.

It also names the one project root of a command (`ProjectRoot`, AD-735, AD-776): `init`, the
draft step, the configuration reason, the baseline file and the scan request use the same folder.
"""

from __future__ import annotations

import hashlib
import json
import stat
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from .core_json import RequestMismatch, as_object, as_text, as_texts

_BYTES = 64 << 20


def resolve_root(path: Path, *, strict: bool = False) -> Path:
    """Use one plain disk form for the root and its files; refuse device and network roots."""
    if sys.platform == "win32" and path.drive:
        drive = path.drive.removeprefix("\\\\?\\")
        if len(drive) != 2 or not drive[0].isascii() or not drive[0].isalpha() or drive[1] != ":":
            raise ValueError("the root is not a supported local disk path")
    resolved = path.resolve(strict=strict)
    if (
        sys.platform == "win32"
        and resolved.drive.startswith("\\\\?\\")
        and len(resolved.drive) == 6
    ):
        return Path(str(resolved).removeprefix("\\\\?\\"))
    return resolved


def _work_tree_top(path: Path) -> Path | None:
    """The top of the Git work tree at or above `path`, or `None` outside a work tree."""
    return next((folder for folder in (path, *path.parents) if (folder / ".git").exists()), None)


_CONFIG = "archkeel.toml"


class RootMode(StrEnum):
    """How a command found its project root."""

    # `--root` names the project; a relative `--config` is read below it.
    EXPLICIT = "explicit"
    # A configuration file names the project: the folder of the file, or the folder that its
    # `[scan] root` states; a system document names the top of its work tree (AD-776).
    CONFIG = "config"
    # The top of the Git work tree at or above the current folder.
    WORK_TREE = "work_tree"
    # No work tree: the current folder. The core then refuses the root and names why.
    CURRENT = "current"


@dataclass(frozen=True, slots=True)
class ProjectRoot:
    """The folder that holds the configuration and the baseline files, and that the core scans,
    and the configuration as a POSIX path below it."""

    path: Path
    mode: RootMode
    config: str = _CONFIG
    given_root: Path | None = None

    @classmethod
    def top(cls, root: Path | None) -> ProjectRoot:
        """An explicit `--root`, else the top of the work tree above the current folder."""
        if root is not None:
            return cls(resolve_root(root), RootMode.EXPLICIT)
        here = resolve_root(Path.cwd())
        found = _work_tree_top(here)
        return cls(found, RootMode.WORK_TREE) if found is not None else cls(here, RootMode.CURRENT)

    @classmethod
    def of(cls, root: Path | None, config: str | None) -> ProjectRoot:
        """The root and the configuration of a run (AD-776).

        With `--root`, `config` is below it. Else a `config` that the command line names is read
        from the current folder, as each command line tool reads a path; without one the nearest
        `archkeel.toml` at or above the current folder, inside its work tree, names the project.
        """
        if root is not None:
            return cls(resolve_root(root), RootMode.EXPLICIT, config or _CONFIG, root.absolute())
        here = resolve_root(Path.cwd())
        if config is not None:
            file = resolve_root(here / config)
            if not file.is_file():
                what = "a folder" if file.is_dir() else "no file"
                raise ValueError(
                    f"--config {config}: {file} is {what}; a relative --config is read from the "
                    "current folder, or below --root when the command line names one"
                )
            return cls._named_by(file)
        start = cls.top(None)
        stop = start.path if start.mode is RootMode.WORK_TREE else here
        for folder in (here, *here.parents):
            if (folder / _CONFIG).is_file():
                named = cls._named_by(folder / _CONFIG)
                same = (named.path, named.config) == (start.path, _CONFIG)
                return start if same else named
            if folder == stop:
                break
        return start

    @classmethod
    def _named_by(cls, file: Path) -> ProjectRoot:
        """The root that a configuration file names; a system document names its work tree."""
        if file.suffix == ".json":
            base = _work_tree_top(file.parent) or file.parent
        else:
            base = resolve_root(file.parent / _stated_root(file))
        if not file.is_relative_to(base):
            raise ValueError(f"{file}: the root {base} does not hold the configuration")
        return cls(base, RootMode.CONFIG, file.relative_to(base).as_posix())

    @property
    def discover(self) -> bool:
        """Whether the core looks for the work tree itself: only for a root that no flag and no
        configuration file named."""
        return self.mode in {RootMode.WORK_TREE, RootMode.CURRENT}

    def as_json(self) -> dict[str, object]:
        """The root and the configuration for a JSON result, as absolute paths."""
        return {"root": str(self.path), "config": str(self.path / self.config)}

    def named(self, here: Path) -> tuple[str, str]:
        """Use a relative path inside `here`, or the absolute spelling given for display."""
        root = self.given_root or self.path
        if self.path.is_relative_to(here):
            root = self.path.relative_to(here)
        return str(root), str(root / self.config)


def _stated_root(file: Path) -> str:
    """The `[scan] root` of a configuration: `.` or a path of `..` parts. A file that cannot be
    read states none; the core then names why it cannot read it."""
    try:
        scan = tomllib.loads(file.read_text(encoding="utf-8")).get("scan")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return "."
    stated = scan.get("root", ".") if isinstance(scan, dict) else "."
    parts = stated.split("/") if isinstance(stated, str) else [""]
    if stated != "." and not all(part == ".." for part in parts):
        raise ValueError(f'{file}: scan.root must be "." or a path of ".." parts, such as "../.."')
    return str(stated)


def bind_request(
    frame: Mapping[str, object], request: Mapping[str, object], derived: str, started_ns: int | None
) -> None:
    """Check identity, not verdicts. Only the located core proves the rule rows."""
    root = resolve_root(Path(as_text(request["root"], "request.root")))
    if request.get("discover_root") is True:
        root = _work_tree_top(root) or root
    collected = as_object(json.loads(derived), "collect.request")
    snapshot = as_object(collected.get("snapshot"), "collect.request.snapshot")
    if as_text(snapshot.get("root"), "snapshot.root") != str(root):
        raise RequestMismatch("the core frame answers another root")
    head, dirty = request.get("git_head"), request.get("dirty")
    if not isinstance(head, str) or snapshot.get("git_head") != head:
        raise RequestMismatch("the core frame answers another commit than the shell read")
    if not isinstance(dirty, bool) or snapshot.get("dirty") is not dirty:
        raise RequestMismatch("the core frame answers another work tree state than the shell read")
    config = resolve_root(root / as_text(request["config"], "request.config"), strict=True)
    if not config.is_relative_to(root):
        raise RequestMismatch("the configuration leaves the requested root")
    with config.open("rb") as stream:
        raw = stream.read((1 << 20) + 1)
    if len(raw) > 1 << 20:
        raise RequestMismatch("the configuration exceeds the core byte limit")
    if config.suffix == ".json":
        # AD-616: a system document is the contract of a system run; the core names its digest.
        reference, payload = config.relative_to(root).as_posix(), raw
    else:
        scan = as_object(tomllib.loads(raw.decode("utf-8-sig")).get("scan"), "scan")
        reference = as_text(scan.get("contract"), "scan.contract")
        contract = resolve_root(root / reference, strict=True)
        if not contract.is_relative_to(root):
            raise RequestMismatch("the contract leaves the requested root")
        with contract.open("rb") as stream:
            payload = stream.read(_BYTES + 1)
        if len(payload) > _BYTES:
            raise RequestMismatch("the contract exceeds the core byte limit")
    if frame.get("contract_digest") != hashlib.sha256(payload).hexdigest():
        raise RequestMismatch("the core frame contract digest differs from the requested contract")
    test = as_object(frame["self_test"], "self_test")
    collect = as_object(test["collect"], "self_test.collect")
    if "contract_files" not in collect:
        raise RequestMismatch("the core frame has no contract file digests")
    files = as_texts(collect.get("contract_files"), "self_test.collect.contract_files")
    if files.get(reference) != frame.get("contract_digest") or len(files) > 1025:
        raise RequestMismatch(
            "the core frame contract file list differs from the requested contract"
        )
    total = 0
    for name, digest in files.items():
        if name != reference:
            total += _bind_inside(root, name, digest, _BYTES - total, started_ns)


def _bind_inside(root: Path, name: str, digest: str, budget: int, started_ns: int | None) -> int:
    """A bounded read of the same non-linked file, with no write since the request started."""
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or any(c in name for c in "\\\0:")
    ):
        raise RequestMismatch(f"the core frame names an unsafe contract path: {name}")
    path = root / relative
    try:
        if resolve_root(path, strict=True) != path:
            raise RequestMismatch(f"the nested contract is a link or leaves the root: {name}")
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise RequestMismatch(f"the nested contract is not a regular file: {name}")
        if started_ns is not None and before.st_ctime_ns > started_ns:
            raise RequestMismatch(f"the nested contract changed after the request started: {name}")
        with path.open("rb") as stream:
            payload = stream.read(budget + 1)
        after = path.stat()
        if (after.st_ino, after.st_mtime_ns, after.st_ctime_ns) != (
            before.st_ino,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) or resolve_root(path, strict=True) != path:
            raise RequestMismatch(f"the nested contract changed during the binding read: {name}")
    except OSError as error:
        raise RequestMismatch(f"the nested contract cannot be read: {name}: {error}") from error
    if len(payload) > budget or hashlib.sha256(payload).hexdigest() != digest:
        raise RequestMismatch(f"the nested contract digest or byte limit differs: {name}")
    return len(payload)
