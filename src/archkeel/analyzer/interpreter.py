# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The interpreter block of a native Python request (AD-334).

One function asks one isolated child (`python -I`) what the interpreter is. The Python collector
runs in such a child, so the block holds what that collector sees, not what the host process sees.
The native collector reads the block and never runs Python.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from functools import cache

from archkeel.ir.protocol import NATIVE_PYTHON_PROTOCOL, CollectionRequest

# The child prints one JSON object. `-I` leaves out the user site, the environment and the
# current directory, as the collector child does.
_PROBE = (
    "import json, platform, sys; print(json.dumps({"
    "'version': platform.python_version(), "
    "'stdlib_module_names': sorted(sys.stdlib_module_names), "
    "'builtin_module_names': sorted(sys.builtin_module_names)}))"
)
_TIMEOUT_SECONDS = 30


@dataclass(frozen=True, slots=True)
class Interpreter:
    """The closed interpreter block: the full version and the two module tables, sorted."""

    version: str
    stdlib_module_names: tuple[str, ...]
    builtin_module_names: tuple[str, ...]


@cache
def interpreter(executable: str = sys.executable) -> Interpreter:
    """Ask one isolated child of `executable`; each later call gives the same block."""
    completed = subprocess.run(
        (executable, "-I", "-c", _PROBE),
        capture_output=True,
        check=True,
        timeout=_TIMEOUT_SECONDS,
        env={**os.environ, "LC_ALL": "C"},  # AD-325
    )
    raw = json.loads(completed.stdout)
    return Interpreter(
        raw["version"],
        tuple(raw["stdlib_module_names"]),
        tuple(raw["builtin_module_names"]),
    )


def python_request(request: CollectionRequest, block: Interpreter) -> bytes:
    """The 10.0.0 request of the native Python collector: the import survey (slice 1)."""
    raw = {
        "protocol_version": NATIVE_PYTHON_PROTOCOL,
        "snapshot": {
            "root": request.snapshot.root,
            "git_head": request.snapshot.git_head,
            "dirty": request.snapshot.dirty,
        },
        # 10.0.0 has the scope of 9.0.0: the test flag is always present.
        "scope": {
            "roots": list(request.scope.roots),
            "namespace": request.scope.namespace,
            "exclude_test_sources": request.scope.exclude_test_sources,
        },
        "resolver": {
            "language": "python",
            "phase": "imports",
            "interpreter": {
                "version": block.version,
                "stdlib_module_names": list(block.stdlib_module_names),
                "builtin_module_names": list(block.builtin_module_names),
            },
        },
    }
    text = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return bytes(text, "utf-8")
