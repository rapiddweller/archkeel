# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Print the verdict of ArchKeel as one system, from the parts of its system document.

`docs/architecture/architecture-system.json` lists the parts (`tools/system_parts.py`). This tool
runs `archkeel validate --config <part config> --json` for each part and prints one line for the
system, then one line for each part. The verdict of the system is the weakest verdict of the parts
(FAIL, then UNKNOWN, then PASS); `tools.report_product.system` joins them. Interim: the system
contract of the core replaces this tool (AD-522). A run that gives no JSON, no status, a refusal
or a contradiction gives a part with no result, which is UNKNOWN, never PASS.

Run: `python -m tools.self_system [--archkeel "uv run --locked archkeel"] [--system FILE]`.
The exit code is 0: the pinned result of each part is the gate (`tools/native_expected.py`).
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.report_product import STATUSES, Contract, contract_of, system_line
from tools.system_parts import DOCUMENT, ROOT, SystemPart, load

TIMEOUT = 900


def run_part(cli: Sequence[str], part: SystemPart) -> Contract:
    """The part of one self run; any fault gives a part with no result."""
    command = [*cli, "validate", "--config", part.config, "--json"]
    try:
        done = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT, check=False
        )
        return contract_of(json.loads(done.stdout), part.title)
    except (OSError, ValueError, subprocess.TimeoutExpired) as err:
        return contract_of(None, part.title, f"no result: {type(err).__name__}: {err}"[:200])


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--archkeel", default="archkeel", help="the CLI command")
    parser.add_argument("--system", type=Path, default=DOCUMENT, help="the system document")
    args = parser.parse_args(argv)
    system = load(args.system)
    cli = shlex.split(args.archkeel)
    parts = [run_part(cli, part) for part in system.parts]
    print(system_line(system.name, parts))
    for part in parts:
        if part.decided:
            words = ", ".join(f"{part.counts[name]} {name}" for name in STATUSES)
            print(f"  {part.title}: {part.status}: {words}")
        else:
            print(f"  {part.title}: UNKNOWN: {part.error}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
