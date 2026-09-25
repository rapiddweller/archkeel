# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 `--against` rows: two Git revisions of the shop sample, run through `run_validate`.

A widening comparison needs a prior commit to read with `check/git.py`'s `read_blob`, the same
problem `fixtures/demo_catalog_check.py` solves for the M -> B -> E -> H protocol; this module
follows the same shape - build a real, minimal Git history, then call the typed entry point
directly - without that protocol's bare origin, CI lock or host records, since `--against` reads
one local revision, not a fetched branch.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

from archkeel.analyzer import observe
from archkeel.check.validation import run_validate
from archkeel.cli.config import load_config
from archkeel.ir.model import RunResult
from fixtures.demo_catalog_dart import DART_FIXTURE_DIR
from fixtures.demo_catalog_dependencies import module_cycle_rule
from fixtures.demo_catalog_support import (
    FIXTURE_DIR,
    AgainstExpectation,
    Variant,
    apply_overlay,
    contract_interface_budgets,
    contract_rule_field,
    contract_with_rule,
    contract_without_rule,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=root, stderr=subprocess.PIPE, text=True
    ).strip()


def build_and_run_against(
    tmp_path: Path, files: Mapping[str, str | None], scenario: AgainstExpectation
) -> RunResult:
    """Commit the clean shop sample on main, apply the scenario's overlay, then run
    `--against main` from the scenario's root."""
    root = tmp_path / "root"
    shutil.copytree(FIXTURE_DIR, root)
    apply_overlay(root, scenario.base_files)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "demo@example.invalid")
    _git(root, "config", "user.name", "Demo")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base contract")

    apply_overlay(root, files)
    run_root = root / scenario.root
    config = load_config(run_root)

    if scenario.scenario not in ("widened_amended", "introduced_amended"):
        return run_validate(run_root, config, observe, against="main")[0]
    # AD-103: the amendment lives inside the root it is validated under.
    amendment = run_root / "widening-amendment.json"
    _, write_files = run_validate(
        run_root,
        config,
        observe,
        against="main",
        amendment=amendment,
        write_amendment=True,
        decided_by="Demo architect",
        rationale="Recorded for the AD-11 demo catalog (#11).",
    )
    amendment.write_bytes(write_files[str(amendment)])
    return run_validate(run_root, config, observe, against="main", amendment=amendment)[0]


# Each scenario widens or narrows DEP-APP-NO-STORE-SQLITE's allowed_sources, an exemption list
# already used by the clean sample (AD-49), so only that one rule's field changes either way.
_WIDENED = AgainstExpectation(
    "widened_unamended",
    1,
    ("rule DEP-APP-NO-STORE-SQLITE.allowed_sources gained 'shop.app.orders'",),
)
_WIDEN_FILES = {
    "architecture-contract.json": contract_rule_field(
        "DEP-APP-NO-STORE-SQLITE", allowed_sources=["shop.app.maintenance", "shop.app.orders"]
    )
}
_WIDENED_AMENDED = AgainstExpectation("widened_amended", 0, ())
_CLEAN_CONTRACT = (FIXTURE_DIR / "architecture-contract.json").read_text()
# The narrowing row's base already carries the extra exemption no code actually needs, so
# dropping it back to the clean sample's list is a real narrowing, not a new violation.
_NARROWED = AgainstExpectation("narrowed_only", 0, (), base_files=_WIDEN_FILES)
_NARROW_FILES = {"architecture-contract.json": _CLEAN_CONTRACT}
_BOUNDARY_TYPES_ID = "APP-TYPES-NOT-DICT"
_SYMBOL_PLACEMENT_ID = "MODEL-TYPES-IN-ENTITIES"
_BOUNDARY_TYPES_ADDED = AgainstExpectation(
    "boundary_types_added",
    0,
    (),
    base_files={"architecture-contract.json": contract_without_rule(_BOUNDARY_TYPES_ID)},
)
_SYMBOL_PLACEMENT_ADDED = AgainstExpectation(
    "symbol_placement_added",
    0,
    (),
    base_files={"architecture-contract.json": contract_without_rule(_SYMBOL_PLACEMENT_ID)},
)
_BOUNDARY_TYPES_REMOVED = AgainstExpectation(
    "boundary_types_removed", 1, (f"rule {_BOUNDARY_TYPES_ID} (boundary_types) removed",)
)
_BUDGET_RAISED = AgainstExpectation(
    "budget_raised",
    1,
    ("facade budget model raised from 5 to 6",),
    base_files={"architecture-contract.json": contract_interface_budgets((("model", 5),))},
)
_SYMBOL_PLACEMENT_REMOVED = AgainstExpectation(
    "symbol_placement_removed", 1, (f"rule {_SYMBOL_PLACEMENT_ID} (symbol_placement) removed",)
)
# AD-98: scoping a module-level cycle rule to one component stops judging every other cycle.
_CYCLE_RULE_SCOPED = AgainstExpectation(
    "cycle_rule_scoped",
    1,
    ("rule MODEL-MODULES-ACYCLIC.components scoped to ['model']",),
    base_files={"architecture-contract.json": contract_with_rule(module_cycle_rule())},
)
# AD-104 (#150): the merge request that adds a Flutter-style app under mobile/ with its own
# archkeel.toml and contract; main holds neither, and the run's --root is mobile.
_MOBILE_FILES = {
    f"mobile/{path.relative_to(DART_FIXTURE_DIR).as_posix()}": path.read_text()
    for path in sorted(DART_FIXTURE_DIR.rglob("*"))
    if path.is_file()
}
_INTRODUCED = AgainstExpectation(
    "introduced_unamended",
    1,
    ("contract introduced: mobile/architecture-contract.json does not exist at main",),
    root="mobile",
)
_INTRODUCED_AMENDED = AgainstExpectation("introduced_amended", 0, (), root="mobile")

VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="against-widened-unamended",
        section="validation",
        item="against:widened_unamended",
        summary="DEP-APP-NO-STORE-SQLITE gains an allowed_sources entry since the compared "
        "revision, with no amendment: the widening fails, naming the field it found.",
        files=_WIDEN_FILES,
        expected_violations=(),
        expected_codes=(),
        against=_WIDENED,
    ),
    Variant(
        id="against-widened-amended",
        section="validation",
        item="against:widened_amended",
        summary="The same widening, with a --write-amendment record binding its exact "
        "before/after contract digests: the run passes.",
        files=_WIDEN_FILES,
        expected_violations=(),
        expected_codes=(),
        against=_WIDENED_AMENDED,
    ),
    Variant(
        id="against-narrowed-only",
        section="validation",
        item="against:narrowed_only",
        summary="DEP-APP-NO-STORE-SQLITE's allowed_sources is emptied instead: a narrowing, "
        "the reverse case, passes without any amendment.",
        files=_NARROW_FILES,
        expected_violations=(),
        expected_codes=(),
        against=_NARROWED,
    ),
    Variant(
        id="against-boundary-types-added",
        section="validation",
        item="against:boundary_types_added",
        summary="Adding the boundary_types restriction is a narrowing and passes without an "
        "amendment.",
        files={"architecture-contract.json": _CLEAN_CONTRACT},
        expected_violations=(),
        expected_codes=(),
        against=_BOUNDARY_TYPES_ADDED,
    ),
    Variant(
        id="against-symbol-placement-added",
        section="validation",
        item="against:symbol_placement_added",
        summary="Adding the symbol_placement restriction is a narrowing and passes without an "
        "amendment.",
        files={"architecture-contract.json": _CLEAN_CONTRACT},
        expected_violations=(),
        expected_codes=(),
        against=_SYMBOL_PLACEMENT_ADDED,
    ),
    Variant(
        id="against-boundary-types-removed",
        section="validation",
        item="against:boundary_types_removed",
        summary="Removing the boundary_types restriction is a widening and fails without an "
        "amendment.",
        files={"architecture-contract.json": contract_without_rule(_BOUNDARY_TYPES_ID)},
        expected_violations=(),
        expected_codes=(),
        against=_BOUNDARY_TYPES_REMOVED,
    ),
    Variant(
        id="against-symbol-placement-removed",
        section="validation",
        item="against:symbol_placement_removed",
        summary="Removing the symbol_placement restriction is a widening and fails without an "
        "amendment.",
        files={"architecture-contract.json": contract_without_rule(_SYMBOL_PLACEMENT_ID)},
        expected_violations=(),
        expected_codes=(),
        against=_SYMBOL_PLACEMENT_REMOVED,
    ),
    Variant(
        id="against-facade-budget-raised",
        section="validation",
        item="against:budget_raised",
        summary="The model facade budget rises from five to six names to make room for one "
        "more export: a widening that fails without an amendment (AD-99).",
        files={"architecture-contract.json": contract_interface_budgets((("model", 6),))},
        expected_violations=(),
        expected_codes=(),
        against=_BUDGET_RAISED,
    ),
    Variant(
        id="against-cycle-rule-scoped",
        section="validation",
        item="against:cycle_rule_scoped",
        summary="A module-level no_component_cycles rule gains a components scope since the "
        "compared revision: it now judges fewer cycles, a widening that fails without an "
        "amendment.",
        files={
            "architecture-contract.json": contract_with_rule(
                module_cycle_rule(components=["model"])
            )
        },
        expected_violations=(),
        expected_codes=(),
        against=_CYCLE_RULE_SCOPED,
    ),
    Variant(
        id="against-contract-introduced",
        section="validation",
        item="against:introduced_unamended",
        summary="A second contract arrives under mobile/ with its own archkeel.toml, and main "
        "holds neither: one widening names the contract by its repository path, where main "
        "exited 2 naming it without mobile/.",
        files=_MOBILE_FILES,
        expected_violations=(),
        expected_codes=(),
        against=_INTRODUCED,
    ),
    Variant(
        id="against-contract-introduced-amended",
        section="validation",
        item="against:introduced_amended",
        summary="The same introduction with the architect's --write-amendment record, bound to "
        "no contract before and this one after: the run passes.",
        files=_MOBILE_FILES,
        expected_violations=(),
        expected_codes=(),
        against=_INTRODUCED_AMENDED,
    ),
)
