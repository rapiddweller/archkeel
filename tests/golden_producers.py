# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The producers of a golden reply (AD-343): the Python collectors and the native binary.

The TypeScript Python producer is retired. Its goldens remain read-only.
`producer("python", language="python", phase=...)` runs the Python collector of Python
sources as the host does. `imports` is the import survey of phase `imports`. `providers` is the
survey of phase `providers`, with the provider sources. `full` is the host sequence: `providers`,
then the full collection. `producer("native", binary)` runs the native binary
through its process port. A test or the recorder switches the producer with one value; the
compare does not change.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zlib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.python.collect import PythonProviderCollector
from archkeel.analyzer.python.explore_scope import wire_protocol
from archkeel.cli.config import load_config
from archkeel.ir.facts import GATED_RESOLUTION_FEATURES
from archkeel.ir.facts_codec import encode_request, encode_response
from archkeel.ir.protocol import (
    CollectionError,
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonSettings,
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


def _decode(reply: bytes) -> dict[str, Any]:
    # A V8 reply is zlib data. Plain JSON never starts with the zlib header byte.
    return json.loads(reply if reply[:1] == b"{" else zlib.decompress(reply))


def _python_request(root: Path, features: bool, exclude_tests: bool) -> CollectionRequest:
    config = load_config(root)
    wanted = tuple(sorted(GATED_RESOLUTION_FEATURES)) if features else ()
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(config.roots, config.namespace, exclude_tests),
        PythonSettings(features=wanted),
    )


# The two surveys that the host can ask for: the imports alone, and the imports with the provider
# sources (the host sends this one before the full collection).
_SURVEYS = {"imports": PythonCollectionPhase.IMPORTS, "providers": PythonCollectionPhase.PROVIDERS}


def python_sources(phase: str, features: bool = True, exclude_tests: bool = False) -> Producer:
    """The Python collector of Python sources: the import survey or the whole host sequence."""

    def run(root: Path) -> dict[str, Any]:
        request = _python_request(root, features, exclude_tests)
        child = ProcessCollector(
            (sys.executable, "-I", "-B", "-m", "archkeel.analyzer.python.entry")
        )
        if phase in _SURVEYS:
            survey = replace(
                request,
                resolver=replace(request.resolver, phase=_SURVEYS[phase]),
                protocol_version=wire_protocol(request, ProtocolVersion.V4),
            )
            result = child.collect_response(survey)
        else:
            facts = PythonProviderCollector(child).collect(request)
            result = (
                facts
                if isinstance(facts, CollectionError)
                else CollectionResponse(facts, ProtocolVersion.V8)
            )
        if isinstance(result, CollectionError):
            raise RuntimeError(f"the Python collector failed: {result}")
        return _decode(encode_response(result))

    return run


def native(binary: Path) -> Producer:
    def run(root: Path) -> dict[str, Any]:
        reply = subprocess.run(
            [str(binary)], input=encode_request(_request(root)), capture_output=True, check=True
        ).stdout
        return _decode(reply)

    return run


def producer(
    name: str,
    binary: Path | None = None,
    *,
    language: str = "typescript",
    phase: str = "full",
    features: bool = True,
    exclude_tests: bool = False,
) -> Producer:
    if language == "python" and name == "python":
        return python_sources(phase, features, exclude_tests)
    if language == "python":
        raise ValueError("there is no native producer of Python sources yet")
    if name == "python":
        raise ValueError("typescript_oracle_retired: the Python TypeScript producer was deleted")
    if name == "native" and binary is not None:
        return native(binary)
    raise ValueError(f"unknown golden producer {name!r}, or a native producer without a binary")
