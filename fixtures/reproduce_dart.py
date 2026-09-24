# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replay the Dart catalog rows as one story: decided, not measurable, refused (AD-97).

Every line is a real `validate` and `report` on a committed copy of `fixtures/G-dart` with one
row's overlay applied; nothing here decides an outcome, it only groups what the runs answered.
The grouping is the product's promise for a profile that reads directives only: what it can
decide reads PASS or FAIL, what it cannot decide reads UNKNOWN, and what it cannot read or
evaluate at all is refused, never passed.

Run from the repository root with:

    python -m fixtures.reproduce_dart
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli.config import load_config
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.trace import trace_valid_violations
from fixtures.demo_catalog_dart import VARIANTS
from fixtures.demo_catalog_support import Variant, apply_overlay

# In story order; an outcome's verdict, or "refused" for exit 2, picks its chapter.
CHAPTERS = (
    ("PASS", "clean: every rule decided every import"),
    ("FAIL", "measured violations"),
    ("UNKNOWN", "not measurable -> UNKNOWN, counted, never PASS"),
    ("refused", "unsupported or unreadable -> refused with exit 2"),
)


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one row's real run answered."""

    variant: str
    verdict: str
    rule_ids: tuple[str, ...] = ()
    unknown_kinds: tuple[str, ...] = ()


def _repository(workspace: Path, variant: Variant) -> Path:
    root = workspace / variant.id
    shutil.copytree(variant.fixture, root)
    apply_overlay(root, dict(variant.files))
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "dart-demo@example.invalid"],
        ["git", "config", "user.name", "Dart demo"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", variant.id],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return root


def run_variant(workspace: Path, variant: Variant) -> Outcome:
    root = _repository(workspace, variant)
    config = load_config(root)
    baseline = root / variant.baseline if variant.baseline is not None else None
    validated, _ = run_validate(root, config, observe, baseline=baseline)
    refused = sorted(item.kind for item in validated.diagnostics if item.code is None)
    if refused:
        return Outcome(variant.id, f"exit {validated.exit_code} {', '.join(refused)}")
    report, artifact = run_report(root, config=config, analyzer=observe)
    if artifact is None:
        raise ValueError(f"{variant.id}: report produced no architecture artifact")
    observation = parse_observation(decode_canonical_model(json.loads(artifact)))
    rule_ids = sorted({item.rule_ids[0] for item in trace_valid_violations(observation)})
    # An unknown bound to a rule is a position that rule could not decide; the analyzer's
    # standing disclaimers name no rule and would repeat on every line.
    unknown_kinds = sorted(
        {record.kind for record in observation.records("unknowns") or () if record.rule_ids}
    )
    return Outcome(variant.id, report.declared_rules, tuple(rule_ids), tuple(unknown_kinds))


def run_dart_demo(workspace: Path) -> tuple[Outcome, ...]:
    return tuple(run_variant(workspace, variant) for variant in VARIANTS)


def _chapter(outcome: Outcome) -> str:
    return "refused" if outcome.verdict.startswith("exit ") else outcome.verdict


def story(outcomes: tuple[Outcome, ...]) -> tuple[str, ...]:
    """The printed lines: one chapter heading, then one line per row it holds."""
    lines: list[str] = []
    for key, heading in CHAPTERS:
        rows = [outcome for outcome in outcomes if _chapter(outcome) == key]
        if not rows:
            continue
        lines.append(heading)
        for outcome in rows:
            parts = [f"  {outcome.variant:<24} {outcome.verdict}"]
            if outcome.rule_ids:
                parts.append(f"rules: {', '.join(outcome.rule_ids)}")
            if outcome.unknown_kinds:
                parts.append(f"unknown: {', '.join(outcome.unknown_kinds)}")
            lines.append("  ".join(parts))
    return tuple(lines)


def main() -> int:
    with TemporaryDirectory(prefix="archkeel-dart-") as temporary:
        for line in story(run_dart_demo(Path(temporary))):
            print(line)
    print("\nWhat the directives decide is PASS or FAIL. The rest is UNKNOWN or refused.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
