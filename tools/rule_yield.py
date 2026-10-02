# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Measure declared-rule evidence and independent warm evaluator replays (AD-140)."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import importlib.metadata
import json
import platform
import statistics
import subprocess
import sys
import time
import tomllib
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import FrameType
from typing import Any

from archkeel.analyzer.embedded.report import analyze_snapshot
from archkeel.analyzer.embedded.violations import boundary_type_limits, rule_violations
from archkeel.ir.model import RULE_KINDS


def _captured_analysis(root: Path, arguments: dict[str, Any]) -> tuple[dict, list]:
    targets = {function.__code__: function for function in (rule_violations, boundary_type_limits)}
    pending = {}
    calls = []

    def capture(frame: FrameType, event: str, result: Any) -> None:
        function = targets.get(frame.f_code)
        if function is None:
            return
        if event == "call":
            count = frame.f_code.co_argcount + frame.f_code.co_kwonlyargcount
            arguments = {name: frame.f_locals[name] for name in frame.f_code.co_varnames[:count]}
            pending[id(frame)] = function, arguments
        elif event == "return":
            function, arguments = pending.pop(id(frame))
            calls.append((function, arguments, result))

    previous = sys.getprofile()
    try:
        sys.setprofile(capture)
        model, _ = analyze_snapshot(root, **arguments)
    finally:
        sys.setprofile(previous)
    return model, calls


def _selected_records(result: Any, rule_id: str) -> list[dict]:
    records = [*result[0], *result[1]] if isinstance(result, tuple) else result
    return sorted(
        (record for record in records if rule_id in record["rule_ids"]), key=lambda row: row["id"]
    )


def _replays(calls: list, repeats: int) -> dict[str, dict]:
    measurements = {}
    for function, arguments, observed in calls:
        contract = arguments["contract"]
        for rule in contract.rules:
            entry = measurements.setdefault(rule.id, {"seconds": 0.0, "matches": True})
            scoped = {**arguments, "contract": replace(contract, rules=(rule,))}
            if "assessment_facts" in scoped:
                scoped["assessment_facts"] = []
            seconds = []
            for _ in range(repeats):
                profiler = cProfile.Profile()
                start = time.perf_counter()
                result = profiler.runcall(function, **scoped)
                seconds.append(time.perf_counter() - start)
                entry["matches"] &= _selected_records(result, rule.id) == _selected_records(
                    observed, rule.id
                )
            entry["seconds"] += statistics.median(seconds)
    return measurements


def _rule_measures(model: dict, runtimes: dict[str, dict]) -> list[dict]:
    rows = []
    for rule in model["declarations"]:
        if rule["kind"] not in RULE_KINDS:
            continue
        identifier = rule["id"]
        unknowns = [row for row in model["unknowns"] if identifier in row["rule_ids"]]
        limits = [row["data"] for row in unknowns if row["kind"] == "boundary_type_limit"]
        causes = Counter(
            row["data"].get("reason", row["kind"])
            for row in unknowns
            if row["kind"] != "boundary_type_limit"
        )
        for limit in limits:
            aggregate = Counter(detail["reason"] for detail in limit["undecidable_positions"])
            for cause, count in aggregate.items():
                causes[cause] = max(causes[cause], count)
        runtime = runtimes.get(identifier)
        gaps = ["No complete per-position pass/violation/UNKNOWN ledger is published."]
        if runtime is None or not runtime["matches"]:
            gaps.append("Independent evaluator replay is absent or changes observed findings.")
        rows.append(
            {
                "id": identifier,
                "kind": rule["kind"],
                "violation_records": sum(
                    identifier in row["rule_ids"] for row in model["violations"]
                ),
                "unknown_by_cause": dict(sorted(causes.items())),
                "declared_positions": limits[0]["positions"] if len(limits) == 1 else None,
                "decided_positions": limits[0]["decided"] if len(limits) == 1 else None,
                "decided_pass_positions": None,
                "allowance_records": sum(
                    identifier in row["rule_ids"] and row["kind"] == "boundary_type_allowance"
                    for row in model["typing_signals"] or ()
                ),
                "runtime_seconds": runtime["seconds"]
                if runtime is not None and runtime["matches"]
                else None,
                "replay_matches": runtime["matches"] if runtime is not None else None,
                "evidence_gaps": gaps,
            }
        )
    return sorted(rows, key=lambda row: row["id"])


def measure(root: Path, *, repeats: int = 3) -> tuple[dict, dict]:
    """Read a clean pinned Git snapshot; leave canonical analyzer output unchanged."""
    if repeats < 1:
        raise ValueError("repeats must be positive")
    root = root.resolve()
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True)
    if dirty:
        raise ValueError("measurement requires a clean Git snapshot")
    config = tomllib.loads((root / "archkeel.toml").read_text())["scan"]
    if config.get("language", "python") != "python":
        raise ValueError("this measurement supports Python snapshots")
    arguments = {
        "git_head": head,
        "dirty": False,
        "contract_root": root,
        "contract_path": root / config["contract"],
        "roots": tuple(config["roots"]),
        "namespace": config["namespace"],
        "language": "python",
    }
    seconds = []
    for _ in range(repeats):
        start = time.perf_counter()
        model, code = analyze_snapshot(root, **arguments)
        seconds.append(time.perf_counter() - start)
    start = time.perf_counter()
    captured, calls = _captured_analysis(root, arguments)
    captured_seconds = time.perf_counter() - start
    if captured != model:
        raise ValueError("profiling changed the canonical observation")
    rows = _rule_measures(model, _replays(calls, repeats))
    boundaries = sum(row["kind"] == "boundary_types" for row in rows)
    model["python_version"] = platform.python_version()
    return {
        "measurement_version": 1,
        "tool_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "package_version": importlib.metadata.version("archkeel"),
        "python_version": platform.python_version(),
        "analyzer": model["analyzer"],
        "source": model["source"],
        "contract": model["contract"],
        "coverage": model["coverage"],
        "scan_exit_code": code,
        "scan_seconds": seconds,
        "scan_median_seconds": statistics.median(seconds),
        "capture_scan_seconds": captured_seconds,
        "runtime_method": "Independent warm cProfile replays; not additive or exclusive wall time.",
        "boundary_rules_measured": boundaries,
        "rules": rows,
        "evidence_gaps": []
        if boundaries
        else ["No boundary_types rule declares an EE/CE boundary."],
    }, model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.root.resolve()):
        parser.error("output must be outside the measured repository")
    try:
        metrics, observation = measure(args.root, repeats=args.repeats)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    args.output.with_suffix(".architecture.json").write_text(
        json.dumps(observation, sort_keys=True)
    )
    print(json.dumps(metrics, sort_keys=True))
    raise SystemExit(metrics["scan_exit_code"])


if __name__ == "__main__":
    main()
