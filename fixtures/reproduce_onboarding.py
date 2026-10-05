# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replay interview-mode onboarding with Archkeel commands and approved decision fixtures.

This is not a live agent or architect interview. The fixture contracts stand in for decisions
already made; command implementations produce the observations and gate results.

Run from the repository root with:

    python -m fixtures.reproduce_onboarding
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from archkeel.check.onboarding import run_init
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    contract_bytes,
    decode_canonical_model,
    decode_json,
    parse_contract,
    parse_observation,
)
from archkeel.ir.decisions import review_claims
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    CompleteRequiresRule,
    ForbiddenDependencyRule,
    RequiredComponent,
    declared_package_pair,
)
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


def _draft(root: Path, source: str, namespace: str) -> tuple[int, int, int, tuple[str, ...]]:
    """Run `init` at one scope and report what it drafted, without writing anything."""
    result, files = run_init(root, source=source, namespace=namespace, force=True, analyzer=observe)
    contract = json.loads(files["architecture-contract.json"])
    labels = tuple(sorted(item["label"] for item in contract["components"]))
    dependency_kinds = {"allowed_dependency", "forbidden_dependency"}
    dependency_rules = sum(rule["kind"] in dependency_kinds for rule in contract["rules"])
    return len(labels), len(result.open_decisions), dependency_rules, labels


def _drafts_the_top_level(root: Path) -> Step:
    components, open_decisions, dependency_rules, labels = _draft(root, "shop", "shop")
    return Step(
        "The agent drafts the structure",
        "archkeel init --source shop --namespace shop --force",
        f"{components} components, {open_decisions} open decisions, "
        f"{dependency_rules} dependency rules",
        (
            f"components: {', '.join(labels)}",
            "INTERVIEW-MODE REPLAY: approved answers below come from committed fixtures.",
            "`init` derives open pairs from the draft; it writes no dependency rules.",
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
    result, _ = run_validate(drafted, SHOP, observe)
    open_decisions = [item for item in result.diagnostics if item.code == "decision.open"]
    return Step(
        "Archkeel refuses the draft",
        "archkeel validate",
        f"exit {result.exit_code}, {len(result.open_decisions)} open decisions, "
        f"{len(open_decisions)} decision.open panel",
        (
            "In this interview-mode replay, a drafted contract is not the approved target.",
            "Its 20 pairs remain open until the pre-approved fixture is applied.",
        ),
        "gate",
    )


def _requires_contract() -> ArchitectureContract:
    """Translate approved pair decisions; observations never grant permissions."""
    contract = parse_contract(
        decode_json((FIXTURE_DIR / "architecture-contract.json").read_bytes())
    )
    ownership = tuple(
        (item.label, item.packages, item.exact_modules or ()) for item in contract.components
    )
    requires: dict[str, list[RequiredComponent]] = {item.label: [] for item in contract.components}
    rules: list[ArchitectureRule] = []
    for rule in contract.rules:
        if isinstance(rule, AllowedDependencyRule):
            pair = declared_package_pair(rule.source, rule.target, None, ownership)
            assert pair is not None
            requires[pair[0]].append(
                RequiredComponent(pair[1], rule.rationale, decided_by=rule.decided_by)
            )
        elif (
            isinstance(rule, ForbiddenDependencyRule)
            and declared_package_pair(rule.source, rule.target, rule.target_symbol, ownership)
            is not None
        ):
            assert rule.include_type_checking and not rule.allowed_sources
        else:
            rules.append(rule)
    approved = next(item for item in CATALOG if item.id == "class-a-complete-requires")
    closed = parse_contract(decode_json(approved.files["architecture-contract.json"].encode()))
    rules.extend(item for item in closed.rules if isinstance(item, CompleteRequiresRule))
    return replace(
        contract,
        components=tuple(
            replace(item, requires=tuple(requires[item.label])) for item in contract.components
        ),
        rules=tuple(rules),
    )


def _write_approved_contracts(root: Path) -> ArchitectureContract:
    contract = _requires_contract()
    (root / "architecture-contract.json").write_bytes(contract_bytes(contract))
    inner_path = root / "shop/store/architecture-contract.json"
    inner = parse_contract(decode_json(inner_path.read_bytes()))
    # The namespace reexports OrderRepository; it belongs to the repository interface.
    inner = replace(
        inner,
        components=tuple(
            replace(item, exact_modules=("shop.store",)) if item.label == "repository" else item
            for item in inner.components
        ),
    )
    inner_path.write_bytes(contract_bytes(inner))
    document = root / "docs/architecture/shop.md"
    document.write_text(
        document.read_text()
        + "\nThe repository component owns the namespace facade `shop.store` via `exact_modules`; "
        "it reexports that component's OrderRepository.\n"
    )
    return contract


def _architect_decides(root: Path) -> Step:
    """Replay the pre-approved top-level contract fixture through the validator."""
    contract = _write_approved_contracts(root)
    entries = sum(len(item.requires or ()) for item in contract.components)
    result, _ = run_validate(root, SHOP, observe)
    return Step(
        "The approved top-level target enters the replay",
        "archkeel validate",
        f"exit {result.exit_code}, declared_rules {result.declared_rules}, "
        f"{entries} requires entries",
        (
            f"{entries} approved requires entries retain their original reasons.",
            "One complete_requires closes absent pairs; narrow exclusions remain.",
            "INTERVIEW-MODE REPLAY: these committed fixture decisions are attributed to",
            "the architect; no live person or agent approved them during this run.",
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
    components, open_decisions, _, labels = _draft(root, "shop/store", "shop.store")
    return Step(
        "The agent drafts the inside",
        "archkeel init --source shop/store --namespace shop.store --force",
        f"{components} sub-components, {open_decisions} open decisions",
        (
            f"drafted: {', '.join(labels)}",
            "The draft is shown separately from the approved nested target in the next step.",
        ),
        "agent",
    )


def _architect_decides_inside(root: Path) -> Step:
    """Replay the approved nested fixture and validate it with the real command implementation."""
    inner = json.loads((root / "shop/store/architecture-contract.json").read_bytes())
    components = {item["label"]: item for item in inner["components"]}
    pairs = tuple(
        f"{component['label']} -> {entry['component']}"
        for component in inner["components"]
        for entry in component.get("requires", ())
    )
    result, _ = run_validate(root, SHOP, observe)
    return Step(
        "The approved nested target enters the replay",
        "archkeel validate",
        f"exit {result.exit_code}, declared_rules {result.declared_rules}, "
        f"{len(pairs)} requires entries",
        (
            f"INTERVIEW-MODE REPLAY: approved fixture maps `sqlite` / "
            f"`{components['api']['packages'][0]}` to `api`.",
            f"approved target: {', '.join(pairs)}",
            "`complete_requires` makes every absent pair forbidden; "
            "fixture attribution is architect.",
            "The namespace facade belongs to repository via exact_modules: [shop.store].",
        ),
        "architect",
    )


def _catches_the_agent(workspace: Path) -> Step:
    """The payoff: an edit inside the level the architect just closed is rejected."""
    variant = next(item for item in CATALOG if item.id == BREAKING_VARIANT)
    root = _repository(workspace / "broken")
    apply_overlay(root, dict(variant.files))
    _write_approved_contracts(root)
    result, artifact = run_report(root, config=SHOP, analyzer=observe)
    assert artifact is not None
    observation = parse_observation(decode_canonical_model(json.loads(artifact)))
    violations = trace_valid_violations(observation)
    rules = sorted({item.rule_ids[0] for item in violations if item.rule_ids})
    return Step(
        "An agent crosses a closed boundary",
        "archkeel report",
        f"{result.declared_rules}, {len(violations)} violations: {', '.join(rules)}",
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
        _architect_decides_inside(root),
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
    print(
        "\nINTERVIEW-MODE REPLAY: command implementations run against "
        "pre-approved decision fixtures."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
