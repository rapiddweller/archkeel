# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-105 (#151): a package rename is compared under the new names, never read as widening."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG as SHOP_CONFIG
from test_architecture_demo import _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.validation import run_validate
from archkeel.ir.baseline import KnownViolation, ViolationFingerprint
from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.model import ArchitectureContract, ComponentRole, ContractComponent, RunResult
from archkeel.ir.renames import (
    contract_names,
    rename_candidates,
    rename_holds,
    renamed,
    renamed_baseline,
    renamed_contract,
)
from archkeel.ir.widening import contract_widenings
from archkeel.render.summary import report_summary
from fixtures.demo_catalog_support import FIXTURE_DIR, apply_overlay, contract_interface_budgets
from fixtures.demo_catalog_widening import renamed_render

_RENDER = {"shop.render": "shop.view"}
_SHOP = (FIXTURE_DIR / "architecture-contract.json").read_text()
_LEFT_BEHIND = (
    '"""Left behind."""\n\n'
    "from shop.store.repository import OrderRepository\n\nX = OrderRepository\n"
)


def _component(cid: str, *packages: str) -> ContractComponent:
    return ContractComponent(cid, cid.lower(), ComponentRole.COMPONENT, packages, (), (), ())


def _contract(*components: ContractComponent) -> ArchitectureContract:
    return ArchitectureContract("2.1.0", components, ())


def _shop_contract(text: str) -> ArchitectureContract:
    return parse_contract(decode_json(text))


def _without_rules(text: str, *ids: str) -> str:
    contract = json.loads(text)
    contract["rules"] = [rule for rule in contract["rules"] if rule["id"] not in ids]
    return json.dumps(contract, indent=2) + "\n"


def test_a_package_and_folder_rename_propose_the_shortest_prefixes() -> None:
    """The issue's Dart case: the package and one feature folder renamed together."""
    before = _contract(
        _component("API", "window_cleaning_mobile.api"),
        _component("KUNDE", "window_cleaning_mobile.features.kunde"),
    )
    after = _contract(
        _component("API", "field_service_mobile.api"),
        _component("KUNDE", "field_service_mobile.features.customer"),
    )

    assert rename_candidates(before, after)[0] == {
        "window_cleaning_mobile": "field_service_mobile",
        "window_cleaning_mobile.features.kunde": "field_service_mobile.features.customer",
    }


def test_a_resorted_package_list_pairs_by_the_last_segment_a_move_keeps() -> None:
    before = _contract(_component("F", "wcm.f.auftrag", "wcm.f.kunde"))
    after = _contract(_component("F", "fsm.f.customer", "fsm.f.auftrag"))

    assert rename_candidates(before, after)[0] == {
        "wcm": "fsm",
        "wcm.f.kunde": "fsm.f.customer",
    }
    assert (
        rename_candidates(before, _contract(_component("F", "wcm.f.kunde", "wcm.f.auftrag"))) == ()
    )


def test_disagreeing_moves_fall_back_to_the_packages_themselves() -> None:
    before = _contract(_component("X", "a.x"), _component("Y", "a.y"))
    after = _contract(_component("X", "b.x"), _component("Y", "c.y"))

    assert rename_candidates(before, after) == ({"a.x": "b.x", "a.y": "c.y"},)


def test_two_packages_moved_into_one_propose_no_rename() -> None:
    before = _contract(_component("X", "a"), _component("Y", "b"))
    after = _contract(_component("X", "c"), _component("Y", "c"))

    assert rename_candidates(before, after) == ()


def test_only_a_dotted_name_is_renamed_under_its_longest_prefix() -> None:
    renames = {"shop": "store", "shop.render": "store.view"}

    assert renamed("shop.render.text:render_order", renames) == "store.view.text:render_order"
    assert renamed("shop.model", renames) == "store.model"
    assert renamed("shopping.cart", renames) == "shopping.cart"
    assert renamed("shop.render renders text.", renames) == "shop.render renders text."
    assert renamed("shop/render/architecture-contract.json", renames) == (
        "shop/render/architecture-contract.json"
    )


def test_a_rename_that_touches_nothing_else_holds() -> None:
    names = frozenset({"shop", "shop.render", "shop.render.text", "shop.model", "json"})

    assert rename_holds(_RENDER, names=names, modules=frozenset({"shop.view.text"}))


def test_two_old_names_that_would_become_one_are_no_rename() -> None:
    """Guard: `features.customer` already existed, so the folder rename would merge into it."""
    renames = {"wcm": "fsm", "wcm.features.kunde": "fsm.features.customer"}
    names = frozenset({"wcm.features.kunde", "wcm.features.customer"})

    assert not rename_holds(renames, names=names, modules=frozenset())


def test_two_unrelated_packages_that_would_nest_are_no_rename() -> None:
    """Guard: `c.x` inside `c` would overlap it, and an overlapped module is owned by nobody."""
    names = frozenset({"a", "b"})

    assert not rename_holds({"a": "c", "b": "c.x"}, names=names, modules=frozenset())


def test_a_new_name_the_old_contract_already_used_is_no_rename() -> None:
    """Guard: a grant the old contract gave `shop.view` would pass to the renamed package."""
    names = frozenset({"shop.render", "shop.view.legacy"})

    assert not rename_holds(_RENDER, names=names, modules=frozenset())


def test_a_rule_prefix_that_covers_only_one_side_is_no_rename() -> None:
    """Guard: a rule on `other` would newly cover the code, one on `shop` would stop covering it."""
    moved_out = {"shop.render": "other.view"}

    assert not rename_holds(
        moved_out, names=frozenset({"shop.render", "other"}), modules=frozenset()
    )
    assert not rename_holds(
        moved_out, names=frozenset({"shop.render", "shop"}), modules=frozenset()
    )


def test_an_unrelated_name_beside_the_new_one_leaves_the_rename_standing() -> None:
    """`store_app.legacy` neither held nor was held by a renamed name, before or after."""
    names = frozenset({"shop.model", "store_app.legacy"})

    assert rename_holds({"shop": "store_app"}, names=names, modules=frozenset())


def test_a_module_left_under_an_old_name_is_no_rename() -> None:
    """Guard: copied rather than moved, the old module would be governed by nothing renamed."""
    modules = frozenset({"shop.view.text", "shop.render.text"})

    assert not rename_holds(_RENDER, names=frozenset({"shop.render"}), modules=modules)


@pytest.mark.parametrize("module", ["shop.render.text-legacy", "shop.render.2fa"])
def test_a_module_under_an_old_prefix_is_no_rename_whatever_its_file_is_called(
    module: str,
) -> None:
    """Guard (QA c5, c6): a file name no identifier spells still lies under the old prefix."""
    modules = frozenset({"shop.view.text", module})

    assert not rename_holds(_RENDER, names=frozenset({"shop.render"}), modules=modules)


def test_the_renamed_contract_equals_the_one_renamed_by_hand() -> None:
    before = _shop_contract((FIXTURE_DIR / "architecture-contract.json").read_text())
    after_text = renamed_render()["architecture-contract.json"]
    assert after_text is not None
    after = _shop_contract(after_text)

    assert contract_widenings(before, after)
    assert renamed_contract(before, _RENDER) == after
    assert "shop.render" in contract_names(before)
    assert "shop.render" not in contract_names(after)


def test_a_renamed_baseline_sorts_its_subjects_the_way_the_analyzer_does() -> None:
    known = KnownViolation(
        ViolationFingerprint(("DEP-X",), ("shop.render.text", "shop.store.codec")),
        2,
        (("shop.render.text", "shop.store.codec"),),
    )

    (moved,) = renamed_baseline((known,), {"shop.render": "shop.view", "shop.store": "shop.db"})

    assert moved.fingerprint.subjects == ("shop.db.codec", "shop.view.text")
    assert moved.roles == (("shop.view.text", "shop.db.codec"),)
    assert moved.count == 2


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=root, stderr=subprocess.PIPE, text=True
    ).strip()


def test_a_renamed_baseline_entry_is_not_a_padded_one(tmp_path: Path) -> None:
    """The known violation moves with its module; compared unrenamed it reads as new debt."""
    text = (FIXTURE_DIR / "shop/render/text.py").read_text()
    violating = text.replace("    return", "    assert order.lines\n    return", 1)
    root = _prepare_repo(tmp_path, {"shop/render/text.py": violating})
    baseline = root / "known-violations.json"
    _, written = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)
    baseline.write_bytes(written[str(baseline)])
    assert b"shop.render.text" in baseline.read_bytes()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "known violation")
    base = _git(root, "rev-parse", "HEAD")

    apply_overlay(root, {**renamed_render(), "shop/view/text.py": violating})
    baseline.write_text(baseline.read_text().replace("shop.render", "shop.view"))
    result, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, against=base)

    assert (result.exit_code, result.failures) == (0, ())
    assert result.renames == (("shop.render", "shop.view"),)


def test_renamed_coupling_names_are_not_a_widened_budget(tmp_path: Path) -> None:
    """The accepted names move with their module; compared unrenamed, one reads as gained."""
    contract = contract_interface_budgets(pairs=(("cli", "render", 1),))
    root = _prepare_repo(tmp_path, {"architecture-contract.json": contract})
    baseline = root / "known-violations.json"
    _, written = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)
    baseline.write_bytes(written[str(baseline)])
    assert b"shop.render.text:render_order" in baseline.read_bytes()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "coupling budget")
    base = _git(root, "rev-parse", "HEAD")

    apply_overlay(root, renamed_render(contract))
    baseline.write_text(baseline.read_text().replace("shop.render", "shop.view"))
    result, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, against=base)

    assert (result.exit_code, result.failures) == (0, ())
    assert result.renames == (("shop.render", "shop.view"),)


@pytest.mark.parametrize("leftover", ["text-legacy.py", "2fa.py"])
def test_a_module_left_behind_under_the_old_package_keeps_the_plain_comparison(
    tmp_path: Path, leftover: str
) -> None:
    """QA c5, c6: without ASSIGNMENT-COMPLETE and ROOT-LAYOUT no rule sees the module left."""
    contract = _without_rules(_SHOP, "ASSIGNMENT-COMPLETE", "ROOT-LAYOUT")
    root = _prepare_repo(tmp_path, {"architecture-contract.json": contract})
    base = _git(root, "rev-parse", "HEAD")

    apply_overlay(root, {**renamed_render(contract), f"shop/render/{leftover}": _LEFT_BEHIND})
    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base)

    assert (result.exit_code, result.renames) == (1, ())
    assert (
        "component 'render'.packages changed from ('shop.render',) to ('shop.view',)"
        in result.failures
    )


def test_validate_without_against_names_no_rename(tmp_path: Path) -> None:
    root = _prepare_repo(tmp_path, renamed_render())

    assert run_validate(root, SHOP_CONFIG, observe)[0].renames is None


def test_the_summary_names_each_rename() -> None:
    result = RunResult("validate", 0, renames=(("shop.render", "shop.view"),))

    assert report_summary(result).sentence.endswith(
        "Renamed since the compared revision, compared under the new names:\n"
        "  shop.render → shop.view"
    )
    assert "Renamed" not in report_summary(replace(result, renames=())).sentence
