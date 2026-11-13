# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The request of a collector binary, and its reply as JSON data.

Consumer: each test that starts a collector binary directly. The request has the wire form of the
`archkeel-facts` protocol: sorted keys and no space. The reply is a zlib stream of one JSON value.
"""

from __future__ import annotations

import json
import subprocess
import zlib
from pathlib import Path
from typing import Any


def request_bytes(
    root: Path,
    namespace: str,
    tsconfig: str | None = None,
    *,
    roots: tuple[str, ...] = ("src",),
    language: str = "typescript",
    version: str = "8.0.0",
    exclude_test_sources: bool = False,
    bundler: bool = False,
) -> bytes:
    """The request for `root`. Only a 9.0.0 request states `exclude_test_sources`."""
    scope: dict[str, Any] = {"roots": list(roots), "namespace": namespace}
    if version == "9.0.0":
        scope["exclude_test_sources"] = exclude_test_sources
    resolver: dict[str, Any] = {"language": language}
    if tsconfig is not None:
        resolver["tsconfig"] = tsconfig
    if bundler:
        resolver["bundler"] = True
    raw = {
        "protocol_version": version,
        "snapshot": {"root": str(root), "git_head": "a" * 40, "dirty": False},
        "scope": scope,
        "resolver": resolver,
    }
    return json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()


def collect(binary: Path, request: bytes) -> dict[str, Any]:
    """Start the collector with the request and return the facts of its reply."""
    done = subprocess.run([str(binary)], input=request, capture_output=True, check=False)
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    reply: dict[str, Any] = json.loads(zlib.decompress(done.stdout))
    assert "facts" in reply, sorted(reply)
    facts: dict[str, Any] = reply["facts"]
    return facts
