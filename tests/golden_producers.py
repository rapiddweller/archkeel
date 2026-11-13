# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run the native TypeScript collector against existing golden inputs."""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from collector_wire import request_bytes

PRODUCER_VARIABLE = "ARCHKEEL_GOLDEN_PRODUCER"
Producer = Callable[[Path], dict[str, Any]]


def materialize(source: Path, workspace: Path) -> Path:
    """Copy one case and its resolver inputs into a fresh folder."""
    root = workspace / "case"
    shutil.copytree(source, root)
    if (root / "resolver-inputs").is_dir():
        shutil.copytree(root / "resolver-inputs", root / "node_modules")
    return root


def _request(root: Path) -> bytes:
    """The 3.0.0 request of the case, from the `[scan]` table of its `archkeel.toml`."""
    scan = tomllib.loads((root / "archkeel.toml").read_text(encoding="utf-8"))["scan"]
    return request_bytes(
        root,
        scan["namespace"],
        scan.get("tsconfig", "tsconfig.json"),
        roots=tuple(scan["roots"]),
        version="3.0.0",
        bundler=scan.get("bundler", False),
    )


def native(binary: Path) -> Producer:
    def run(root: Path) -> dict[str, Any]:
        reply = subprocess.run(
            [str(binary)], input=_request(root), capture_output=True, check=True
        ).stdout
        return json.loads(reply if reply[:1] == b"{" else zlib.decompress(reply))

    return run


def producer(name: str, binary: Path, *, language: str = "typescript") -> Producer:
    if language != "typescript" or name != "native":
        raise ValueError(f"unsupported golden producer {name!r} for {language!r}")
    return native(binary)
