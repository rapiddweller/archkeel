# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replay TypeScript catalog cases through the in-package collector and Core."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from archkeel.check.expectation import EXPECTATION_SCHEMA_VERSION, GUARDRAIL_KEYS, sha256_bytes
from archkeel.check.ratchets import measure_python_ratchets
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from archkeel.ir.codec import (
    canonical_report_bytes,
    decode_canonical_model,
    parse_observation,
    result_bytes,
)
from archkeel.ir.digest import package_digest
from archkeel.ir.lock import LOCK_SCHEMA_VERSION
from archkeel.ir.model import Observation, RunResult
from archkeel.ir.trace import trace_valid_violations
from fixtures.demo_catalog_support import Variant, apply_overlay
from fixtures.demo_catalog_typescript import VARIANTS, appended


@dataclass(frozen=True)
class Outcome:
    variant: Variant
    validation: RunResult
    report: RunResult
    observation: Observation | None


def repository(workspace: Path, variant: Variant) -> Path:
    """Materialize one variant as a Git repository using the in-package collector."""
    root = workspace / variant.id
    shutil.copytree(variant.fixture, root)
    apply_overlay(root, variant.files)
    shutil.copytree(root / "resolver-inputs", root / "node_modules")
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "typescript-demo@example.invalid"),
        ("config", "user.name", "TypeScript demo"),
        ("add", "-A"),
        ("add", "--force", "node_modules"),
        ("-c", "commit.gpgsign=false", "commit", "-q", "-m", variant.id),
    ):
        subprocess.run(
            ("git", *args),
            cwd=root,
            check=True,
            capture_output=True,
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": "2026-10-03T00:00:00+0000",
                "GIT_COMMITTER_DATE": "2026-10-03T00:00:00+0000",
            },
        )
    return root


def run_variant(workspace: Path, variant: Variant) -> Outcome:
    root = repository(workspace, variant)
    config = load_config(root)
    baseline = root / variant.baseline if variant.baseline else None
    observe = observer_for(
        config.language,
        collector_argv=config.collector_argv,
        tsconfig=config.tsconfig or "tsconfig.json",
    )
    validated, _ = run_validate(root, config, observe, baseline=baseline)
    report, artifact = run_report(root, config=config, analyzer=observe, baseline=baseline)
    (root / "validation-result.json").write_bytes(result_bytes(validated))
    (root / "report-result.json").write_bytes(result_bytes(report))
    observation = None
    if artifact is not None:
        (root / "architecture.json").write_bytes(artifact)
        observation = parse_observation(decode_canonical_model(json.loads(artifact)))
    return Outcome(variant, validated, report, observation)


def git(root: Path, *args: str) -> str:
    env = dict(
        os.environ,
        GIT_AUTHOR_DATE="2026-10-03T00:00:00Z",
        GIT_COMMITTER_DATE="2026-10-03T00:00:00Z",
    )
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        env=env,
        stderr=subprocess.PIPE,
        text=True,
    ).strip()


def json_file(path: Path, value: object) -> bytes:
    payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(payload)
    return payload


def command(root: Path, output: Path, label: str, *args: str) -> dict:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("CI_")}
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", *args, "--root", str(root), "--json"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    (output / f"{label}.stdout.json").write_text(result.stdout)
    (output / f"{label}.stderr").write_text(result.stderr)
    assert result.stdout, (args, result.returncode, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["exit_code"] == result.returncode
    return payload


def check_revisions(workspace: Path, output: Path) -> dict:
    root = repository(
        workspace,
        replace(
            VARIANTS[0],
            id="typescript-revisions",
            files={
                "src/data/local.ts": appended("src/data/local.ts", "\nimport './runtime.js';\n"),
                "src/data/runtime.ts": "export const value = 1;\n",
                "src/data/runtime.js": (
                    "throw Error('must not execute'); const fs = require('node:fs');\n"
                ),
            },
        ),
    )
    path = output / "accepted.json"
    reported = command(root, output, "accepted-report", "report", "--output", str(path))
    assert reported["declared_rules"] == "PASS", reported
    assert reported["measurements"]["calls_total"] is None
    assert reported["measurements"]["scalars"]["calls_unresolved"] is None
    accepted = parse_observation(decode_canonical_model(json.loads(path.read_bytes())))
    lock_bytes = json_file(
        root / "architecture-accepted.json",
        {
            "schema_version": LOCK_SCHEMA_VERSION,
            "accepted_commit": git(root, "rev-parse", "HEAD"),
            "observation_digest": sha256_bytes(canonical_report_bytes(accepted)),
            "config_digest": sha256_bytes((root / "archkeel.toml").read_bytes()),
            "checker_digest": package_digest(),
            "measurements": asdict(measure_python_ratchets(accepted)),
            "approval_ref": "fixture-only:simulated-approval",
        },
    )
    git(root, "add", "architecture-accepted.json")
    git(root, "commit", "-qm", "accepted lock")
    baseline = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", baseline)
    expected_bytes = json_file(
        root / "expectation.json",
        {
            "schema_version": EXPECTATION_SCHEMA_VERSION,
            "evidence_class": "HYPOTHESIS",
            "accepted_digest": sha256_bytes(lock_bytes),
            "baseline_commit": baseline,
            "checker_digest": package_digest(),
            "analyzer_digest": accepted.analyzer.code_digest,
            "contract_digest": accepted.contract.digest,
            "baseline_digest": sha256_bytes(canonical_report_bytes(accepted)),
            "selected_changes": [],
            "guardrails": dict.fromkeys(GUARDRAIL_KEYS, True),
        },
    )
    git(root, "add", "expectation.json")
    git(root, "commit", "-qm", "declare no architecture change")
    expectation = git(root, "rev-parse", "HEAD")
    runtime = root / "src/data/runtime.js"
    runtime.write_text(runtime.read_text() + "// Runtime input changed; import graph unchanged.\n")
    git(root, "add", "src/data/runtime.js")
    git(root, "commit", "-qm", "change runtime input")
    head = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/candidate", head)
    host = output / "host-records.json"
    json_file(
        host,
        [
            {
                "sha": expectation,
                "event": "expectation_published",
                "timestamp": "2026-10-03T00:00:00Z",
            },
            {"sha": head, "event": "candidate_submitted", "timestamp": "2026-10-03T00:01:00Z"},
        ],
    )
    args = (
        "check",
        "--baseline",
        baseline,
        "--expectation-commit",
        expectation,
        "--head",
        head,
        "--expected",
        "expectation.json",
        "--expected-digest",
        sha256_bytes(expected_bytes),
        "--branch",
        "candidate",
        "--accepted-branch",
        "main",
        "--host-records",
        str(host),
    )
    # Deliberately poison the working tree: the check must use both committed snapshots.
    runtime.write_text("import './not-in-either-revision.js';\n")
    result = command(root, output, "revisions-check", *args, "--output", str(output / "check.json"))
    assert result["exit_code"] == 0, result
    assert result["delta"]["baseline"]["source_digest"] != result["delta"]["head"]["source_digest"]
    repeat = command(root, output, "revisions-repeat", *args)
    assert repeat == result
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    with TemporaryDirectory(prefix="archkeel-typescript-") as temporary:
        output = args.output or Path(temporary)
        output.mkdir(parents=True, exist_ok=True)
        for variant in VARIANTS:
            root = repository(output, variant)
            artifact = root / "architecture.json"
            commands = (
                ("validate",),
                ("report", "--output", str(artifact.resolve())),
            )
            results = []
            for command in commands:
                invocation = subprocess.run(
                    (
                        sys.executable,
                        "-m",
                        "archkeel.cli",
                        *command,
                        "--root",
                        str(root.resolve()),
                        "--json",
                        *(("--baseline", variant.baseline) if variant.baseline else ()),
                    ),
                    cwd=root,
                    env={
                        **os.environ,
                        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                    },
                    capture_output=True,
                    check=False,
                )
                result = json.loads(invocation.stdout)
                if invocation.returncode != result["exit_code"]:
                    raise RuntimeError(invocation.stderr.decode())
                results.append(invocation.stdout)
            (root / "validation-result.json").write_bytes(results[0])
            (root / "report-result.json").write_bytes(results[1])
            observation = (
                parse_observation(decode_canonical_model(json.loads(artifact.read_bytes())))
                if artifact.is_file()
                else None
            )
            diagnostics = sorted({item["kind"] for item in result["diagnostics"]})
            if variant.expected_kinds:
                if result["exit_code"] != 2 or not set(variant.expected_kinds) <= set(diagnostics):
                    raise RuntimeError(f"{variant.id}: expected refusal {variant.expected_kinds}")
            elif result["declared_rules"] != variant.expected_declared_rules:
                raise RuntimeError(f"{variant.id}: unexpected declared-rule verdict")
            validation = json.loads(results[0])
            if not variant.expected_kinds and sorted(
                item["code"] for item in validation["diagnostics"] if item["code"]
            ) != sorted(variant.expected_codes):
                raise RuntimeError(f"{variant.id}: unexpected validation diagnostics")
            print(
                f"{variant.id}: exit {result['exit_code']}, {result['declared_rules']}"
                + (f" ({', '.join(diagnostics)})" if diagnostics else "")
            )
            if observation is not None:
                violations = trace_valid_violations(observation)
                if sorted(rule for record in violations for rule in record.rule_ids) != sorted(
                    variant.expected_violations
                ):
                    raise RuntimeError(f"{variant.id}: unexpected rule violations")
                rules = sorted({rule for record in violations for rule in record.rule_ids})
                if rules:
                    print("  violations: " + ", ".join(rules))
            unknown_rules = sorted(
                assessment["id"]
                for assessment in result["rule_assessments"] or ()
                if assessment["status"] == "UNKNOWN"
            )
            if unknown_rules:
                print("  unknown: " + ", ".join(unknown_rules))
            if result["measurements"] is not None:
                print(
                    "  "
                    + ", ".join(
                        f"{name}={value if value is not None else 'n/a'}"
                        for name, value in result["measurements"]["scalars"].items()
                    )
                )
        checked = check_revisions(output, output)
        print(f"typescript-revisions: {checked['expectation_fulfilled']} (simulated host ordering)")
        if args.output:
            print(f"Artifacts: {output.resolve()}")
    print("Symbol, call, typing and private-use semantics are unmeasured in this profile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
