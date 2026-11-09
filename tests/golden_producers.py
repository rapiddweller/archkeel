# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The producers of a golden reply (AD-343): the Python collector and the native binary.

`producer("python")` runs the full Python TypeScript collector, not the legacy oracle mode.
`producer("native", binary)` runs the native binary through its process port. A test or the
recorder switches the producer with one value; the compare does not change.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from archkeel.analyzer.typescript.collect import collect
from archkeel.cli.config import load_config
from archkeel.ir.facts_codec import encode_request, encode_response
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

# The name of the environment variable that picks the producer of the golden test.
PRODUCER_VARIABLE = "ARCHKEEL_GOLDEN_PRODUCER"
Producer = Callable[[Path], dict[str, Any]]


def materialize(source: Path, workspace: Path) -> Path:
    """A copy of a case in a fresh folder, with its resolver inputs as `node_modules`."""
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


def _python(root: Path) -> dict[str, Any]:
    request = _request(root)
    reply = encode_response(CollectionResponse(collect(request), request.protocol_version))
    return json.loads(reply)


def native(binary: Path) -> Producer:
    def run(root: Path) -> dict[str, Any]:
        reply = subprocess.run(
            [str(binary)], input=encode_request(_request(root)), capture_output=True, check=True
        ).stdout
        # Plain JSON never starts with the zlib header byte; a compressed reply does.
        return json.loads(reply if reply[:1] == b"{" else zlib.decompress(reply))

    return run


def producer(name: str, binary: Path | None = None) -> Producer:
    if name == "python":
        return _python
    if name == "native" and binary is not None:
        return native(binary)
    raise ValueError(f"unknown golden producer {name!r}, or a native producer without a binary")
