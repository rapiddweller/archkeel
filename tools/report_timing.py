# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record one complete report run, its phase seconds and counters, and enforce its budget."""

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from archkeel.ir.phases import COUNTER_LABELS, Phase, WorkCounter

_BYTE_COUNTERS = frozenset(
    {
        WorkCounter.COLLECTOR_WIRE_BYTES,
        WorkCounter.ARCHITECTURE_BYTES,
        WorkCounter.REPORT_PAGE_BYTES,
    }
)


def _timings(path: Path) -> tuple[dict[str, float], dict[str, int]]:
    """Read the child's timings; a failed child leaves no file, so the receipt gets none."""
    if not path.is_file():
        return {}, {}
    payload = json.loads(path.read_text())
    phase_seconds: dict[str, float] = payload["phases"]
    counters: dict[str, int] = payload["counters"]
    return phase_seconds, counters


def _counter_text(counter: WorkCounter, value: int) -> str:
    if counter in _BYTE_COUNTERS:
        return f"{value / 1_000_000:.1f} MB"
    return f"{value:,}"


def _summary(phase_seconds: dict[str, float], counters: dict[str, int], wall_seconds: float) -> str:
    """Markdown for the step summary: phases in pipeline order, then counters in label order."""
    lines = ["### Report timing", ""]
    if not phase_seconds:
        return "\n".join([*lines, "No timings were written.", ""])
    timed = sum(phase_seconds.values())
    # Process start and exit sit outside every phase; show them so the rows add up to the wall time.
    total = max(wall_seconds, timed)
    lines += [
        "Seconds are wall-clock time on this runner. Counters do not depend on the runner.",
        "",
        "| Phase | Seconds | Share |",
        "| --- | ---: | ---: |",
    ]
    for phase in Phase:
        if phase.value in phase_seconds:
            seconds = phase_seconds[phase.value]
            share = seconds / total * 100 if total > 0 else 0.0
            lines.append(f"| {phase.value} | {seconds:.2f} | {share:.1f} % |")
    if total > timed:
        lines.append(f"| untimed | {total - timed:.2f} | {(total - timed) / total * 100:.1f} % |")
    lines.append(f"| **Total** | {total:.2f} | 100 % |")
    rows = [
        (label, _counter_text(counter, counters[counter.value]))
        for counter, label in COUNTER_LABELS.items()
        if counter.value in counters
    ]
    if rows:
        lines += ["", "| Counter | Value |", "| --- | ---: |"]
        lines += [f"| {label} | {text} |" for label, text in rows]
    return "\n".join(lines) + "\n"


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
    timings = output.parent / f"{output.stem}.phases.json"
    timings.unlink(missing_ok=True)
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
        "--timings",
        str(timings),
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
    phase_seconds, counters = _timings(timings)
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
        "phase_seconds": phase_seconds,
        "counters": counters,
    }
    output.with_suffix(".timing.json").write_text(json.dumps(receipt, indent=2) + "\n")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with Path(step_summary).open("a", encoding="utf-8") as handle:
            handle.write(_summary(phase_seconds, counters, elapsed))
    print(json.dumps(receipt))
    return result.returncode if result.returncode else int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
