# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run the native TypeScript collector against existing golden inputs."""

from __future__ import annotations

import json
import shutil
import subprocess
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from archkeel.cli.config import load_config
from archkeel.cli.observe import TYPESCRIPT_COLLECTOR, verified_binary
from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import CollectionRequest, SnapshotInput, SourceScope, TypeScriptSettings

PRODUCER_VARIABLE = "ARCHKEEL_GOLDEN_PRODUCER"
Producer = Callable[[Path], dict[str, Any]]


def materialize(source: Path, workspace: Path) -> Path:
    """Copy one case and its resolver inputs into a fresh folder."""
    root = workspace / "case"
    shutil.copytree(source, root)
    if (root / "resolver-inputs").is_dir():
        shutil.copytree(root / "resolver-inputs", root / "node_modules")
    return root


def _request(root: Path) -> CollectionRequest:
    config = load_config(root)
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(config.roots, config.namespace),
        TypeScriptSettings(config.tsconfig or "tsconfig.json", bundler=config.bundler),
    )


def native(binary: Path) -> Producer:
    def run(root: Path) -> dict[str, Any]:
        reply = subprocess.run(
            [str(binary)], input=encode_request(_request(root)), capture_output=True, check=True
        ).stdout
        return json.loads(reply if reply[:1] == b"{" else zlib.decompress(reply))

    return run


def producer(name: str, binary: Path | None = None, *, language: str = "typescript") -> Producer:
    if language != "typescript" or name != "native":
        raise ValueError(f"unsupported golden producer {name!r} for {language!r}")
    return native(binary or Path(verified_binary(TYPESCRIPT_COLLECTOR).path))
