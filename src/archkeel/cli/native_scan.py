# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-406: the scan request of `archkeel-core`: the core runs the collector in its own process.

With the switch of the core and a TypeScript scan with the bundled collector, the shell sends the
core the scan identity only: the repository root, the configuration file, and the Git head and
dirty state of the request that the shell sent to its own collector. It sends no reply bytes.
The core reads the configuration and the contract, derives the collection request and runs the
linked collector. The shell compares the derived request with its own, field by field: a
difference is a named gap, never a guess.

Stage 1 stays on: the Python engine still decides the same run, and `native_core.stage_one`
compares the two (a difference is exit 2). A frame that names a part (a refusal of the scan, a
rule that the core does not decide) sends the run back to the check request of stage 1.

A dead core (an abort, a stack overflow, an allocation failure) has an exit code that
`read_frame` refuses, so the run has no verdict (exit 2), never a PASS. The shell stops the core
after `TIMEOUT_SECONDS`.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Final

from archkeel.ir.codec import RawJson

from .core_frame import CoreError, CoreFrame, Gap, GapKind, read_frame

SCAN_PROTOCOL: Final = "archkeel-core-scan-1"
TIMEOUT_SECONDS: Final = 600
# The exit code of a request that the core cannot read: it writes no frame.
_REFUSED_EXIT: Final = 2


@dataclass(frozen=True, slots=True)
class Scanned:
    """The frame of a scan request whose derived request is the request of the shell."""

    frame: CoreFrame


def scan_request(shell_request: bytes, config_path: str) -> dict[str, RawJson] | Gap:
    """The scan request of the identity in the request that the shell sent to its collector."""
    try:
        snapshot = json.loads(shell_request)["snapshot"]
        root, head, dirty = snapshot["root"], snapshot["git_head"], snapshot["dirty"]
    except (KeyError, TypeError) as error:
        reason = f"the request of the shell has no snapshot field {error}"
        return Gap(GapKind.REQUEST_DIFFERS, "collect", reason)
    if not isinstance(dirty, bool):
        reason = "the request of the shell has no Boolean dirty state"
        return Gap(GapKind.REQUEST_DIFFERS, "collect", reason)
    return {
        "protocol": SCAN_PROTOCOL,
        "root": root,
        "config": config_path,
        "git_head": head,
        "dirty": dirty,
    }


def differences(derived: RawJson, sent: RawJson, path: str = "") -> list[str]:
    """Each field where the request of the core and the request of the shell differ."""
    if isinstance(derived, dict) and isinstance(sent, dict):
        found: list[str] = []
        for key in sorted(set(derived) | set(sent)):
            where = f"{path}.{key}" if path else key
            if key not in derived or key not in sent:
                found += [f"{where} is in one request only"]
            else:
                found += differences(derived[key], sent[key], where)
        return found
    if type(derived) is not type(sent) or derived != sent:
        return [f"{path}: core {json.dumps(derived)}, shell {json.dumps(sent)}"]
    return []


def scan(binary: str, shell_request: bytes, config_path: str) -> Scanned | tuple[Gap, ...]:
    """The decided frame of the scan request, or the gaps that send the run back to stage 1."""
    request = scan_request(shell_request, config_path)
    if isinstance(request, Gap):
        return (request,)
    stdout, exit_code = exchange(binary, "scan", bytes(json.dumps(request), "utf-8"))
    frame = read_frame(stdout, exit_code, scan=True)
    found = (
        differences(json.loads(frame.derived), json.loads(shell_request))
        if frame.derived is not None
        else []
    )
    if found:
        reason = "the core derived another collection request: " + "; ".join(found)
        return (Gap(GapKind.REQUEST_DIFFERS, "collect", reason),)
    if not frame.decided:
        return frame.gaps
    return Scanned(frame)


def exchange(binary: str, kind: str, request: bytes) -> tuple[bytes, int]:
    """Run the core with one encoded request and a time limit, and give its standard output and exit
    code. Exit 2 (no frame) is a `CoreError`."""
    try:
        done = subprocess.run(
            [binary, kind],
            input=request,
            capture_output=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise CoreError(f"the core did not answer in {TIMEOUT_SECONDS} s") from error
    except OSError as error:
        raise CoreError(f"the core could not execute: {error}") from error
    if done.returncode == _REFUSED_EXIT:
        message = done.stderr.decode("utf-8", errors="replace").strip()[-2000:]
        raise CoreError(f"the core refused the request (exit 2): {message}")
    return done.stdout, done.returncode
