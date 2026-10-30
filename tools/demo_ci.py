# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run one gallery demo and record its result and report phases."""

import argparse
import contextlib
import io
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from archkeel.cli import main as archkeel_main
from fixtures.architecture_demo import CATALOG, replay
from fixtures.demo_catalog_typescript import VARIANTS
from fixtures.reproduce_typescript import repository
from tools.report_pages import gallery_cases
from tools.report_timing import _summary


def run(name: str, output: Path) -> dict[str, Any]:
    variant, expected = gallery_cases()[name]
    output.mkdir(parents=True, exist_ok=True)
    artifact = (output / "architecture.json").resolve()
    timings = (output / "phases.json").resolve()
    timings.unlink(missing_ok=True)
    captured = io.StringIO()
    started = time.perf_counter()
    with contextlib.redirect_stdout(captured):
        if name == "typescript-clean":
            selected = next(item for item in VARIANTS if item.id == variant)
            with TemporaryDirectory(prefix="archkeel-demo-") as temporary:
                root = repository(Path(temporary), selected)
                exit_code = archkeel_main(
                    [
                        "report",
                        "--root",
                        str(root),
                        "--output",
                        str(artifact),
                        "--timings",
                        str(timings),
                        "--json",
                    ]
                )
        else:
            exit_code = replay(variant, artifact, timings=timings)
    elapsed = time.perf_counter() - started
    reports = [
        json.loads(line)
        for line in captured.getvalue().splitlines()
        if line.startswith("{") and line.endswith("}")
    ]
    report = next(item for item in reports if item["command"] == "report")
    expected_rules = (
        selected.expected_declared_rules
        if name == "typescript-clean"
        else next(item.expected_declared_rules for item in CATALOG if item.id == variant)
    )
    if expected_rules is not None and report["declared_rules"] != expected_rules:
        raise ValueError(f"{name}: expected rules {expected_rules}, got {report['declared_rules']}")
    if exit_code != expected:
        raise ValueError(f"{name}: expected exit {expected}, got {exit_code}")
    if not timings.is_file() or not artifact.is_file():
        raise ValueError(f"{name}: report or phase timings missing")
    data = json.loads(timings.read_text())
    if not data["phases"]:
        raise ValueError(f"{name}: empty phase timings")
    sizes = {
        path.name: path.stat().st_size
        for path in sorted(output.glob("architecture.*"))
        if path.is_file()
    }
    result = {
        "name": name,
        "expected_exit": expected,
        "exit": exit_code,
        "report_exit": report["exit_code"],
        "coverage": report["coverage"],
        "observation_complete": report["observation_complete"],
        "declared_rules": report["declared_rules"],
        "expected_declared_rules": expected_rules,
        "rule_assessments": report["rule_assessments"],
        "output_bytes": sum(sizes.values()),
        "files": sizes,
        "wall_seconds": elapsed,
        "phases": data["phases"],
        "counters": data["counters"],
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as stream:
            stream.write(
                f"## Demo: {name}\n\nCoverage: {result['coverage']['status']}  \n"
                f"Rules: {result['declared_rules']}  \nOutput: {result['output_bytes']:,} bytes\n\n"
            )
            stream.write(_summary(data["phases"], data["counters"], elapsed))
    print(
        f"{name}: exit {exit_code} (expected {expected}), "
        f"coverage {result['coverage']['status']}, rules {result['declared_rules']}, "
        f"{result['output_bytes']:,} bytes; details: {output / 'result.json'}"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--case", choices=gallery_cases())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.list:
        print(json.dumps(list(gallery_cases())))
    elif args.case and args.output:
        run(args.case, args.output)
    else:
        parser.error("use --list or --case with --output")


if __name__ == "__main__":
    main()
