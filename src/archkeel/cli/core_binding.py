# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bind a scan frame to its files and request identity. This module reads no rules."""

from __future__ import annotations

import hashlib
import json
import stat
import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from .core_json import RequestMismatch, _object, _text, _texts

_BYTES = 64 << 20


def bind_request(
    frame: Mapping[str, object], request: Mapping[str, object], derived: str, started_ns: int | None
) -> None:
    """Check identity, not verdicts. Only the located core proves the rule rows."""
    root = Path(_text(request["root"], "request.root")).resolve()
    if request.get("discover_root") is True:
        root = next((path for path in (root, *root.parents) if (path / ".git").exists()), root)
    collected = _object(json.loads(derived), "collect.request")
    snapshot = _object(collected.get("snapshot"), "collect.request.snapshot")
    if _text(snapshot.get("root"), "snapshot.root") != str(root):
        raise RequestMismatch("the core frame answers another root")
    head, dirty = request.get("git_head"), request.get("dirty")
    if not isinstance(head, str) or snapshot.get("git_head") != head:
        raise RequestMismatch("the core frame answers another commit than the shell read")
    if not isinstance(dirty, bool) or snapshot.get("dirty") is not dirty:
        raise RequestMismatch("the core frame answers another work tree state than the shell read")
    config = (root / _text(request["config"], "request.config")).resolve(strict=True)
    if not config.is_relative_to(root):
        raise RequestMismatch("the configuration leaves the requested root")
    with config.open("rb") as stream:
        raw = stream.read((1 << 20) + 1)
    if len(raw) > 1 << 20:
        raise RequestMismatch("the configuration exceeds the core byte limit")
    scan = _object(tomllib.loads(raw.decode("utf-8")).get("scan"), "scan")
    reference = _text(scan.get("contract"), "scan.contract")
    contract = (root / reference).resolve(strict=True)
    if not contract.is_relative_to(root):
        raise RequestMismatch("the contract leaves the requested root")
    with contract.open("rb") as stream:
        payload = stream.read(_BYTES + 1)
    if len(payload) > _BYTES:
        raise RequestMismatch("the contract exceeds the core byte limit")
    if frame.get("contract_digest") != hashlib.sha256(payload).hexdigest():
        raise RequestMismatch("the core frame contract digest differs from the requested contract")
    test = _object(frame["self_test"], "self_test")
    collect = _object(test["collect"], "self_test.collect")
    if "contract_files" not in collect:
        raise RequestMismatch("the core frame has no contract file digests")
    files = _texts(collect.get("contract_files"), "self_test.collect.contract_files")
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
        if path.resolve(strict=True) != path:
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
        ) or path.resolve(strict=True) != path:
            raise RequestMismatch(f"the nested contract changed during the binding read: {name}")
    except OSError as error:
        raise RequestMismatch(f"the nested contract cannot be read: {name}: {error}") from error
    if len(payload) > budget or hashlib.sha256(payload).hexdigest() != digest:
        raise RequestMismatch(f"the nested contract digest or byte limit differs: {name}")
    return len(payload)
