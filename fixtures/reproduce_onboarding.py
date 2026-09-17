# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replay the onboarding loop on the shop sample, one step per command an agent runs.

No agent runs here and none is simulated: every step is a real Archkeel command, and the
decisions the architect makes between them are the ones this repository committed, replayed
so the numbers cannot drift from the tool. What the loop shows is where an agent does the
work and where it must stop and ask, which is the whole of AD-15.

Run from the repository root with:

    python -m fixtures.reproduce_onboarding
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from archkeel.analyzer import observe
from archkeel.check.onboarding import run_init
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import review_claims
from archkeel.ir.trace import trace_valid_violations
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import FIXTURE_DIR, apply_overlay

SHOP = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)
BREAKING_VARIANT = "class-a-complete-requires-inside"


@dataclass(frozen=True, slots=True)
class Step:
    """One step of the loop: what was run, what came back, and who acts next."""

    title: str
    command: str
    outcome: str
    detail: tuple[str, ...]
    actor: str


def _repository(workspace: Path) -> Path:
    """A committed copy of the clean shop sample; `init` needs a resolvable HEAD."""
    root = workspace / "shop-sample"
    shutil.copytree(FIXTURE_DIR, root)
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "onboarding@example.invalid"],
        ["git", "config", "user.name", "Onboarding demo"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "shop sample"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return root


def _draft(root: Path, source: str, namespace: str) -> tuple[int, int, tuple[str, ...]]:
    """Run `init` at one scope and report what it drafted, without writing anything."""
    result, files = run_init(root, source=source, namespace=namespace, force=True, analyzer=observe)
    contract = json.loads(files["architecture-contract.json"])
    labels = tuple(sorted(item["label"] for item in contract["components"]))
    return len(labels), len(result.open_decisions), labels


def _drafts_the_top_level(root: Path) -> Step:
    components, open_decisions, labels = _draft(root, "shop", "shop")
    return Step(
        "The agent drafts the structure",
        "archkeel init --source shop --namespace shop",
        f"{components} components, {open_decisions} open decisions, 0 dependency rules",
        (
            f"components: {', '.join(labels)}",
            "`init` reads the packages and the imports it can see, and decides no pair.",
            "Every ordered pair is listed heaviest first, with the rule to choose from.",
        ),
        "agent",
    )


def _refuses_the_draft(root: Path) -> Step:
    """`validate` on the draft: an undecided pair is a finding, not a blank to fill in."""
    drafted = root / "drafted"
    drafted.mkdir()
    _, files = run_init(root, source="shop", namespace="shop", force=True, analyzer=observe)
    shutil.copytree(root / "shop", drafted / "shop")
    shutil.copyfile(root / "pyproject.toml", drafted / "pyproject.toml")
    (drafted / "architecture-contract.json").write_bytes(files["architecture-contract.json"])
    (drafted / "docs/architecture").mkdir(parents=True)
    (drafted / "docs/architecture/architecture.md").write_bytes(
        files["docs/architecture/architecture.md"]
    )
    result = run_validate(drafted, SHOP, observe)
    open_decisions = [item for item in result.diagnostics if item.code == "decision.open"]
    return Step(
        "Archkeel refuses the draft",
        "archkeel validate",
        f"exit {result.exit_code}, {len(open_decisions)} x decision.open",
        (
            "A drafted contract is not a target. Nothing an agent observed becomes a",
            "decision on its own, so the gate stays shut until the architect decides.",
        ),
        "gate",
    )


def _architect_decides(root: Path) -> Step:
    """The committed contract, replayed: what the architect answered to those 20 questions."""
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_bytes())
    kinds = [rule["kind"] for rule in contract["rules"]]
    result = run_validate(root, SHOP, observe)
    return Step(
        "The architect decides every pair",
        "archkeel validate",
        f"exit {result.exit_code}, no diagnostics",
        (
            f"{kinds.count('forbidden_dependency')} forbidden, "
            f"{kinds.count('allowed_dependency')} allowed, each with a reason.",
            "Every rule records `decided_by`, so a later report can count what the",
            "architect has not reviewed yet.",
        ),
        "architect",
    )


def _names_the_large_component(root: Path) -> Step:
    _, artifact = run_report(root, config=SHOP, analyzer=observe)
    assert artifact is not None
    observation = parse_observation(decode_canonical_model(json.loads(artifact)))
    claims = review_claims(observation)
    return Step(
        "The report names an oversized component",
        "archkeel report",
        f"{claims.oversized_components} component larger than its own level",
        (
            "store holds 7 modules where the whole level has 5 components.",
            "A claim, never a verdict: it is a reason to ask, not permission to split.",
        ),
        "gate",
    )


def _drafts_the_inside(root: Path) -> Step:
    components, open_decisions, labels = _draft(root, "shop/store", "shop.store")
    inner = json.loads((FIXTURE_DIR / "shop/store/architecture-contract.json").read_bytes())
    requires = sum(len(item.get("requires", ())) for item in inner["components"])
    return Step(
        "The agent drafts the inside",
        "archkeel init --source shop/store --namespace shop.store",
        f"{components} sub-components, {open_decisions} open decisions",
        (
            f"drafted: {', '.join(labels)}",
            f"settled: {', '.join(sorted(item['label'] for item in inner['components']))}",
            "`sqlite` was drafted from the module name; the architect calls it `api`,",
            "because the target says what the part is for, not what the file is called.",
            f"{requires} `requires` entries settle it, where the draft asked "
            f"{open_decisions} pair questions:",
            "under `complete_requires` absence forbids, so the list is the whole decision.",
        ),
        "agent",
    )


def _catches_the_agent(workspace: Path) -> Step:
    """The payoff: an edit inside the level the architect just closed is rejected."""
    variant = next(item for item in CATALOG if item.id == BREAKING_VARIANT)
    root = _repository(workspace / "broken")
    apply_overlay(root, dict(variant.files))
    _, artifact = run_report(root, config=SHOP, analyzer=observe)
    assert artifact is not None
    observation = parse_observation(decode_canonical_model(json.loads(artifact)))
    violations = trace_valid_violations(observation)
    rules = sorted({item.rule_ids[0] for item in violations if item.rule_ids})
    return Step(
        "An agent crosses a closed boundary",
        "archkeel report",
        f"FAIL, {len(violations)} violations: {', '.join(rules)}",
        (
            "repository imports backend without requiring it.",
            "The rule is named for the level that holds it, so the agent knows which",
            "contract to read and that the fix belongs there, not one level up.",
        ),
        "gate",
    )


def run_onboarding_demo(workspace: Path) -> tuple[Step, ...]:
    """Replay the whole loop and return one Step per command."""
    root = _repository(workspace)
    return (
        _drafts_the_top_level(root),
        _refuses_the_draft(root),
        _architect_decides(root),
        _names_the_large_component(root),
        _drafts_the_inside(root),
        _catches_the_agent(workspace),
    )


def main() -> int:
    with TemporaryDirectory(prefix="archkeel-onboarding-") as temporary:
        for index, step in enumerate(run_onboarding_demo(Path(temporary)), start=1):
            print(f"\n{index}. {step.title}  [{step.actor}]")
            print(f"   $ {step.command}")
            print(f"   => {step.outcome}")
            for line in step.detail:
                print(f"      {line}")
    print("\nThe agent drafts and observes. The architect decides. The gate refuses the rest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
