# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""Compare the native self-check timing sidecar with the nightly budgets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from archkeel.cli.core_json import CoreError
from archkeel.cli.core_output import read_timings

# Five main CI samples on 2026-11-26; twice the observed maximum, rounded up.
CORE_LIMIT = 1100.0
PHASE_LIMITS = {
    "prepare": 0.1,
    "collect": 200.0,
    "validate": 0.4,
    "evaluate": 4.0,
    "render": 0.3,
    "join": 0.1,
}


def check(timing: bytes, result: bytes) -> str:
    """Check a timing and its result; reject unusable evidence and name each exceeded budget."""
    try:
        frame = json.loads(result)
    except (ValueError, RecursionError) as error:
        raise ValueError("result_unavailable: result is not JSON") from error
    details = frame.get("frame") if isinstance(frame, dict) else None
    test = details.get("self_test") if isinstance(details, dict) else None
    reply = test.get("reply") if isinstance(test, dict) else None
    files = reply.get("files") if isinstance(reply, dict) else None
    if (
        not isinstance(frame, dict)
        or frame.get("outcome") != "verdict"
        or frame.get("status") not in ("PASS", "UNKNOWN")
        or frame.get("refusal") is not None
        or type(frame.get("exit_code")) is not int
        or frame.get("exit_code") != (0 if frame.get("status") == "PASS" else 2)
        or not isinstance(details, dict)
        or not isinstance(details.get("rules"), dict)
        or not details["rules"]
        or type(files) is not int
        or files <= 0
    ):
        raise ValueError("result_unavailable: result is refused or not a usable verdict")
    try:
        line = read_timings(timing, refused=False)
    except CoreError as error:
        raise ValueError(f"timing_unavailable: {error}") from error
    if line is None:
        raise ValueError("timing_unavailable: the core refused the measurement")
    document = json.loads(line)
    values = {"core_seconds": document["core_seconds"], **document["phases"]}
    limits = {"core_seconds": CORE_LIMIT, **PHASE_LIMITS}
    exceeded = [
        f"budget_exceeded: {name} {values[name]:.6f}s > {limit:.6f}s"
        for name, limit in limits.items()
        if values[name] > limit
    ]
    if exceeded:
        raise ValueError("\n".join(exceeded))
    status = frame["status"]
    return f"Within timing budgets; architecture {status}. No performance verdict is implied."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timings", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    try:
        message = check(args.timings.read_bytes(), args.result.read_bytes())
    except (OSError, ValueError) as error:
        message = f"timing_unavailable: {error}" if isinstance(error, OSError) else str(error)
        print(message, file=sys.stderr)
        return 0 if args.report_only else 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
