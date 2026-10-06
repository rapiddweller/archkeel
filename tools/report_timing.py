# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record one complete report run and enforce its wall-clock budget."""

import argparse
import json
import math
import platform
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output", type=Path, default=Path("test-artifacts/report-timing/architecture.json")
    )
    parser.add_argument("--max-seconds", type=float, required=True)
    args = parser.parse_args(argv)
    if not math.isfinite(args.max_seconds) or args.max_seconds <= 0:
        parser.error("--max-seconds must be finite and positive")
    root = args.root.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "archkeel.cli",
        "report",
        "--root",
        str(root),
        "--output",
        str(output),
        "--json",
    ]
    started = time.perf_counter()
    result = subprocess.run(command, check=False)
    elapsed = time.perf_counter() - started
    generated = (
        output,
        output.parent / f"{output.stem}.report.html",
        *output.parent.glob(f"{output.stem}.detail*.html"),
    )
    report_bytes = sum(path.stat().st_size for path in set(generated) if path.is_file())
    canonical_bytes = output.stat().st_size if output.is_file() else 0
    output_budget_passed = canonical_bytes > 0 and report_bytes <= canonical_bytes * 3
    passed = result.returncode == 0 and elapsed <= args.max_seconds
    passed = passed and output_budget_passed
    receipt = {
        "command": command,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "wall_seconds": elapsed,
        "max_seconds": args.max_seconds,
        "report_exit": result.returncode,
        "budget_passed": passed,
        "output_bytes": report_bytes,
        "canonical_bytes": canonical_bytes,
        "max_output_bytes": canonical_bytes * 3,
        "output_budget_passed": output_budget_passed,
    }
    output.with_suffix(".timing.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    return result.returncode if result.returncode else int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
