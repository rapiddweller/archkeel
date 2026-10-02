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
from archkeel.analyzer.embedded.violations import (
    _boundary_rule_positions,
    _boundary_type_allowance_fact,
    _boundary_type_violation_records,
    _uncertain_facade_position_records,
    boundary_type_limits,
    rule_violations,
)
from archkeel.check.ratchets import unknown_positions_by_rule
from archkeel.ir.codec import decode_json, parse_observation
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import RULE_KINDS, stable_id


def _captured_analysis(root: Path, arguments: dict[str, Any]) -> tuple[dict, list]:
    targets = {
        function.__code__: function
        for function in (
            rule_violations,
            boundary_type_limits,
            _boundary_type_violation_records,
            _boundary_type_allowance_fact,
            _boundary_rule_positions,
            _uncertain_facade_position_records,
        )
    }
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
        if function not in (rule_violations, boundary_type_limits):
            continue
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


def _boundary_ledgers(model: dict, calls: list) -> dict[str, dict]:
    """Read producer verdicts and population receipts; never re-resolve an annotation."""
    ledgers = {}
    receipts = {}
    allowance_links = {}
    additional_unknown_ids = set()
    violation_ids = {row["id"] for row in model["violations"]}
    published_allowance_ids = {
        row["id"]
        for row in model["typing_signals"] or ()
        if row["kind"] == "boundary_type_allowance"
    }
    opaque_ids = {
        row["id"]
        for row in model["typing_signals"] or ()
        if row["kind"] == "boundary_type_allowance" and row["data"].get("accepted_opacity")
    }
    scopes = {row["id"]: row["data"].get("parent_id", "root") for row in model["declarations"]}
    for function, arguments, result in calls:
        if (
            function is _boundary_type_allowance_fact
            and result is not None
            and result["id"] in published_allowance_ids
        ):
            allowance_links[arguments["record"]["id"]] = result["id"]
        elif function is _boundary_rule_positions:
            receipts.setdefault(arguments["rule"].id, []).append(result)
        elif function is _uncertain_facade_position_records:
            additional_unknown_ids.update(record["id"] for _, record in result)
        elif function is _boundary_type_violation_records:
            identifier = arguments["rule"].id
            positions = ledgers.setdefault(identifier, {"positions": []})["positions"]
            verdict = arguments["verdict"]
            symbol = arguments["item"]["id"]
            suffix = arguments["identity_suffix"]
            occurrence = sum(
                row["symbol_id"] == symbol
                and row["identity_suffix"] == suffix
                and row["qualified_name"] == arguments["qualname"]
                and row["position"] == arguments["position"]
                for row in positions
            )
            positions.append(
                {
                    "id": stable_id(
                        "YIELD-POSITION",
                        identifier,
                        symbol,
                        arguments["facade_module"],
                        arguments["qualname"],
                        arguments["position"],
                        suffix,
                        str(occurrence),
                    ),
                    "rule_id": identifier,
                    "scope": scopes[identifier],
                    "symbol_id": symbol,
                    "identity_suffix": suffix,
                    "occurrence": occurrence,
                    "module": arguments["facade_module"],
                    "qualified_name": arguments["qualname"],
                    "position": arguments["position"],
                    "annotation": arguments["annotation"],
                    "raw_violation_reason": verdict.violation,
                    "raw_undecidable_reason": verdict.undecidable,
                    "produced_ids": [row["id"] for row in result],
                    "unknown_ids": [],
                    "unknown_causes": [verdict.undecidable] if verdict.undecidable else [],
                }
            )
    for identifier in receipts:
        ledgers.setdefault(identifier, {"positions": []})
    for identifier, ledger in ledgers.items():
        populations = receipts.get(identifier, [])
        positions = ledger["positions"]
        reconciled = len(populations) == 1
        if not reconciled:
            ledger["population_reconciled"] = False
            continue
        seen, undecidable, records = populations[0]
        for record in records:
            detail = record["data"]
            candidates = [
                row
                for row in positions
                if row["symbol_id"] in record["fact_ids"]
                and all(
                    row[key] == detail[key]
                    for key in ("module", "qualified_name", "position", "annotation")
                )
            ]
            if len(candidates) > 1:
                reconciled = False
                continue
            if candidates:
                [position] = candidates
            else:
                # Only the captured additional facade receipts intentionally bypass the producer.
                reconciled &= record["id"] in additional_unknown_ids
                position = {
                    "id": record["id"],
                    "rule_id": identifier,
                    "scope": scopes[identifier],
                    "symbol_id": record["fact_ids"][0],
                    "identity_suffix": "",
                    **{
                        key: detail[key]
                        for key in (
                            "module",
                            "qualified_name",
                            "position",
                            "annotation",
                            "occurrence",
                        )
                    },
                    "raw_violation_reason": None,
                    "raw_undecidable_reason": detail["reason"],
                    "produced_ids": [],
                    "unknown_ids": [],
                    "unknown_causes": [],
                }
                positions.append(position)
            position["unknown_ids"].append(record["id"])
            position["unknown_causes"] = [detail["reason"]]
            position["receipt_occurrence"] = detail["occurrence"]
        ledger["population_reconciled"] = (
            reconciled
            and len(positions) == seen
            and sum(bool(row["unknown_ids"]) for row in positions) == len(undecidable)
            and all(bool(row["unknown_causes"]) == bool(row["unknown_ids"]) for row in positions)
        )
        ledger["declared_positions"] = seen
        ledger["decided_positions"] = seen - len(undecidable)
    for ledger in ledgers.values():
        positions = ledger["positions"]
        for position in positions:
            produced = position.pop("produced_ids")
            ledger["population_reconciled"] &= all(
                value in violation_ids or value in allowance_links for value in produced
            )
            position["violation_ids"] = [value for value in produced if value in violation_ids]
            position["allowance_ids"] = [
                allowance_links[value] for value in produced if value in allowance_links
            ]
            position["opaque_allowance_ids"] = [
                value for value in position["allowance_ids"] if value in opaque_ids
            ]
            position["pass"] = (
                position["raw_violation_reason"] is None
                and position["raw_undecidable_reason"] is None
                and not position["unknown_causes"]
            )
    return ledgers


def _coverage_complete(coverage: dict) -> bool:
    return (
        coverage["status"] == "PASS"
        and coverage["rules"] == "PASS"
        and not coverage["failures"]
        and coverage["files_discovered"] > 0
        and coverage["files_discovered"] == coverage["files_read"] == coverage["files_parsed"]
    )


def _rule_measures(
    model: dict, runtimes: dict[str, dict], ledgers: dict | None = None
) -> list[dict]:
    rows = []
    # The subprocess bridge crosses this JSON boundary before the typed IR parser.
    observation = parse_observation(decode_json(json.dumps(model, sort_keys=True)))
    complete = _coverage_complete(model["coverage"])
    api_limits = any(row["kind"] == "api_surface_limit" for row in model["unknowns"])
    assessments = {
        row.id: row
        for row in rule_assessments(
            observation,
            undecided_by_rule=unknown_positions_by_rule(observation),
            complete=complete,
        )
    }
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
        ledger = (ledgers or {}).get(identifier)
        reconciled = ledger is not None and ledger.get("population_reconciled", False)
        positions = ledger["positions"] if ledger is not None else []
        scope_gaps = [
            row["id"]
            for row in model["unknowns"]
            if (
                identifier in row["rule_ids"]
                and row["kind"] not in {"boundary_type_position", "boundary_type_limit"}
            )
        ]
        gaps = (
            []
            if reconciled
            else ["No reconciled per-position producer/population ledger is available."]
        )
        if rule["kind"] == "boundary_types" and scope_gaps:
            gaps.append(
                "Rule-attributed route/scope evidence prevents proving complete boundary scope."
            )
        if rule["kind"] == "boundary_types" and api_limits:
            gaps.append(
                "Global API scope remains unproven; API limits are not attributed to this rule."
            )
        if runtime is None or not runtime["matches"]:
            gaps.append("Independent evaluator replay is absent or changes observed findings.")
        rows.append(
            {
                "id": identifier,
                "kind": rule["kind"],
                "assessment_status": assessments[identifier].status,
                "assessment_reason": assessments[identifier].reason,
                "assessment_evaluation_proven": assessments[identifier].evaluation_proven,
                "violation_records": sum(
                    identifier in row["rule_ids"] for row in model["violations"]
                ),
                "unknown_by_cause": dict(sorted(causes.items())),
                "declared_positions": ledger["declared_positions"]
                if reconciled
                else limits[0]["positions"]
                if len(limits) == 1
                else None,
                "decided_positions": ledger["decided_positions"]
                if reconciled
                else limits[0]["decided"]
                if len(limits) == 1
                else None,
                "decided_pass_positions": sum(row["pass"] for row in positions)
                if reconciled
                else None,
                "population_reconciled": reconciled,
                "complete_scope": reconciled and not scope_gaps and not api_limits and complete,
                "positions": positions,
                "violation_positions": sum(bool(row["violation_ids"]) for row in positions)
                if reconciled
                else None,
                "unknown_positions": sum(bool(row["unknown_causes"]) for row in positions)
                if reconciled
                else None,
                "violation_unknown_overlap": sum(
                    bool(row["violation_ids"]) and bool(row["unknown_causes"]) for row in positions
                )
                if reconciled
                else None,
                "allowanced_positions": sum(bool(row["allowance_ids"]) for row in positions)
                if reconciled
                else None,
                "opaque_allowanced_positions": sum(
                    bool(row["opaque_allowance_ids"]) for row in positions
                )
                if reconciled
                else None,
                "scope_gap_ids": scope_gaps if rule["kind"] == "boundary_types" else [],
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
    if json.dumps(captured, sort_keys=True) != json.dumps(model, sort_keys=True):
        raise ValueError("profiling changed the canonical observation")
    rows = _rule_measures(model, _replays(calls, repeats), _boundary_ledgers(model, calls))
    boundaries = sum(row["kind"] == "boundary_types" for row in rows)
    model["python_version"] = platform.python_version()
    return {
        "measurement_version": 2,
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
        "canonical_capture_matches": True,
        "runtime_method": "Independent warm cProfile replays; not additive or exclusive wall time.",
        "boundary_rules_measured": boundaries,
        "global_api_scope_complete": _coverage_complete(model["coverage"])
        and not any(row["kind"] == "api_surface_limit" for row in model["unknowns"]),
        "unscoped_api_unknowns": [
            row
            for row in model["unknowns"]
            if row["kind"] == "api_surface_limit" and not row["rule_ids"]
        ],
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
