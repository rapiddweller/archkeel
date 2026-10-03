# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replay TypeScript catalog cases through the configured collector and Core."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from archkeel.ir.codec import decode_canonical_model, parse_observation, result_bytes
from archkeel.ir.model import Observation, RunResult
from archkeel.ir.trace import trace_valid_violations
from fixtures.demo_catalog_support import Variant, apply_overlay
from fixtures.demo_catalog_typescript import VARIANTS

ADAPTER = Path(__file__).resolve().parents[1] / "packages/typescript-adapter/dist/entry.js"


@dataclass(frozen=True)
class Outcome:
    variant: Variant
    validation: RunResult
    report: RunResult
    observation: Observation | None


def repository(workspace: Path, variant: Variant, adapter: Path = ADAPTER) -> Path:
    root = workspace / variant.id
    shutil.copytree(variant.fixture, root)
    apply_overlay(root, variant.files)
    shutil.copytree(root / "resolver-inputs", root / "node_modules")
    config = root / variant.config
    config.write_text(
        "\n".join(
            line
            for line in config.read_text().splitlines()
            if not line.startswith("collector_argv")
        )
        + "\ncollector_argv = "
        + json.dumps(["node", str(adapter.resolve())])
        + "\n"
    )
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


def run_variant(workspace: Path, variant: Variant, adapter: Path = ADAPTER) -> Outcome:
    root = repository(workspace, variant, adapter)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--adapter", type=Path, default=ADAPTER)
    args = parser.parse_args(argv)
    if not args.adapter.is_file():
        parser.error(
            "adapter not built; run make -C packages/typescript-adapter install build first"
        )
    with TemporaryDirectory(prefix="archkeel-typescript-") as temporary:
        output = args.output or Path(temporary)
        output.mkdir(parents=True, exist_ok=True)
        for variant in VARIANTS:
            root = repository(output, variant, args.adapter)
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
        if args.output:
            print(f"Artifacts: {output.resolve()}")
    print("Symbol, call, typing and private-use semantics are unmeasured in this profile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
