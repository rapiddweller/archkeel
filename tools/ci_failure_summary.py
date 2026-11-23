# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Write the first failing test of a failed CI job to the job summary (AD-1060).

The input is the JUnit file of the job. The summary names the first failing test, the command that
repeats the job on a developer machine and where the full result is. The full log stays in the
step; this text only tells a reader where to start.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

MESSAGE_LIMIT = 500


def longest_backtick_run(text: str) -> int:
    return max((len(run) for run in re.findall(r"`+", text)), default=0)


def first_failure(junit: Path) -> tuple[str, str] | None:
    """The name and the first message line of the first failed or errored test case."""
    for case in ET.parse(junit).getroot().iter("testcase"):
        fault = case.find("failure")
        if fault is None:
            fault = case.find("error")
        if fault is not None:
            lines = (fault.get("message") or "").splitlines()
            return f"{case.get('classname')}::{case.get('name')}", lines[0] if lines else ""
    return None


def render(job: str, junit: Path, reproduce: str, artifact: str) -> str:
    try:
        found = first_failure(junit)
    except (OSError, ET.ParseError):
        head = f"**{job}**: no JUnit file. The job ended before pytest wrote it; read the step log."
    else:
        if found is None:
            head = f"**{job}**: the JUnit file has no failed test; read the step log."
        else:
            name, message = found
            # A longer fence than any backtick run in the message keeps the block closed.
            message = message[:MESSAGE_LIMIT]
            fence = "`" * max(3, longest_backtick_run(message) + 1)
            head = f"**{job}**: first failing test `{name}`\n\n{fence}\n{message}\n{fence}"
    return f"{head}\n\nRepeat it locally: `{reproduce}`\n\nFull result: artifact `{artifact}`.\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--job", required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--reproduce", required=True)
    parser.add_argument("--artifact", required=True)
    args = parser.parse_args(argv)
    print(render(args.job, args.junit, args.reproduce, args.artifact), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
