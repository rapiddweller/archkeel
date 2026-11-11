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
from typing import Final

from archkeel.ir.protocol import (
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
)

# The child prints one JSON object. `-I` leaves out the user site, the environment and the
# current directory, as the collector child does.
_PROBE = (
    "import json, platform, sys; print(json.dumps({"
    "'version': platform.python_version(), "
    "'stdlib_module_names': sorted(sys.stdlib_module_names), "
    "'builtin_module_names': sorted(sys.builtin_module_names)}))"
)
_TIMEOUT_SECONDS = 30
# The request of the native Python collector only. The Python codec of `ir/` does not read it, so
# the Python collector refuses it and the host cannot decode a 10.0.0 reply (AD-334).
NATIVE_PYTHON_PROTOCOL: Final = "10.0.0"


@dataclass(frozen=True, slots=True)
class Interpreter:
    """The closed interpreter block: the full version and the two module tables, sorted."""

    version: str
    stdlib_module_names: tuple[str, ...]
    builtin_module_names: tuple[str, ...]


_KNOWN: dict[str, Interpreter] = {}


def interpreter(
    executable: str = sys.executable, timeout_seconds: float = _TIMEOUT_SECONDS
) -> Interpreter | CollectionError:
    """Ask one isolated child of `executable`. A good answer is kept for the process; a failure
    is a named collection error, never an exception."""
    known = _KNOWN.get(executable)
    if known is not None:
        return known
    try:
        completed = subprocess.run(
            (executable, "-I", "-c", _PROBE),
            capture_output=True,
            check=True,
            timeout=timeout_seconds,
            env={**os.environ, "LC_ALL": "C"},  # AD-325
        )
    except FileNotFoundError:
        return _error(CollectionErrorKind.MISSING_TOOL, executable, "Python interpreter not found")
    except subprocess.TimeoutExpired:
        message = f"Python interpreter exceeded {timeout_seconds:g} seconds"
        return _error(CollectionErrorKind.TIMEOUT, executable, message)
    except (subprocess.CalledProcessError, OSError) as error:
        message = f"Python interpreter probe failed: {error}"
        return _error(CollectionErrorKind.EXECUTION_ERROR, executable, message)
    block = _block(completed.stdout)
    if block is None:
        message = "Python interpreter probe gave no valid interpreter block"
        return _error(CollectionErrorKind.PROTOCOL_ERROR, executable, message)
    _KNOWN[executable] = block
    return block


def _error(kind: CollectionErrorKind, executable: str, message: str) -> CollectionError:
    return CollectionError(kind, executable, message)


def _block(output: bytes) -> Interpreter | None:
    try:
        raw = json.loads(output)
    except ValueError:
        return None
    if not isinstance(raw, dict) or set(raw) != {
        "version",
        "stdlib_module_names",
        "builtin_module_names",
    }:
        return None
    version, stdlib, builtin = (
        raw["version"],
        raw["stdlib_module_names"],
        raw["builtin_module_names"],
    )
    names = (stdlib, builtin)
    if not isinstance(version, str) or not all(
        isinstance(table, list) and all(isinstance(name, str) for name in table) for table in names
    ):
        return None
    return Interpreter(version, tuple(stdlib), tuple(builtin))


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
