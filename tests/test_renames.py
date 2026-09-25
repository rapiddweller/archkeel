# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-105 (#151): a package rename is compared under the new names, never read as widening."""

from __future__ import annotations

import json
import py_compile
import shutil
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
from archkeel.ir.model import (
    ArchitectureContract,
    ComponentRole,
    ContractComponent,
    ForbiddenConstructRule,
    RunResult,
)
from archkeel.ir.renames import (
    rename_candidates,
    rename_holds,
    renamed,
    renamed_baseline,
    renamed_contract,
    renames_since,
)
from archkeel.ir.widening import contract_widenings
from archkeel.render.summary import report_summary
from fixtures.demo_catalog_dart import DART_FIXTURE_DIR
from fixtures.demo_catalog_support import FIXTURE_DIR, apply_overlay, contract_interface_budgets
from fixtures.demo_catalog_widening import renamed_render

_RENDER = {"shop.render": "shop.view"}
# The shop sample's layout: module `shop.view.text` is file `shop/view/text.py`.
_FLAT = frozenset({("", "")})
_SHOP = (FIXTURE_DIR / "architecture-contract.json").read_text()
_DART = (DART_FIXTURE_DIR / "architecture-contract.json").read_text()
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


def _moved_root(text: str, old: str, new: str) -> str:
    """Contract JSON with root package `old` renamed `new` the way a text editor does it."""
    return (
        text.replace(f'"{old}.', f'"{new}.')
        .replace(f'"{old}"', f'"{new}"')
        .replace(f'"{old}/', f'"{new}/')
    )


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
    reordered = _contract(_component("F", "fsm.f.auftrag", "fsm.f.customer"))
    assert rename_candidates(before, reordered) == rename_candidates(before, after)
    assert (
        rename_candidates(before, _contract(_component("F", "wcm.f.kunde", "wcm.f.auftrag"))) == ()
    )


def test_two_moved_packages_without_a_shared_last_segment_pair_in_neither_order() -> None:
    """Review P2: pairing them by position would give each order its own substitution."""
    before = _contract(_component("F", "a.p", "a.q"))

    assert rename_candidates(before, _contract(_component("F", "b.r", "b.s"))) == ()
    assert rename_candidates(before, _contract(_component("F", "b.s", "b.r"))) == ()


def test_disagreeing_moves_fall_back_to_the_packages_themselves() -> None:
    before = _contract(_component("X", "a.x"), _component("Y", "a.y"))
    after = _contract(_component("X", "b.x"), _component("Y", "c.y"))

    assert rename_candidates(before, after) == ({"a.x": "b.x", "a.y": "c.y"},)


def test_two_packages_moved_into_one_propose_no_rename() -> None:
    before = _contract(_component("X", "a"), _component("Y", "b"))
    after = _contract(_component("X", "c"), _component("Y", "c"))

    assert rename_candidates(before, after) == ()


def test_a_name_is_renamed_under_its_longest_prefix() -> None:
    renames = {"shop": "store", "shop.render": "store.view"}

    assert renamed("shop.render.text:render_order", renames) == "store.view.text:render_order"
    assert renamed("shop.model", renames) == "store.model"
    assert renamed("shopping.cart", renames) == "shopping.cart"


def test_a_rename_that_touches_nothing_else_holds() -> None:
    names = frozenset({"shop", "shop.render", "shop.render.text", "shop.model", "json"})

    assert rename_holds(_RENDER, names=names, observed=frozenset({"shop.view.text"}))


def test_two_old_names_that_would_become_one_are_no_rename() -> None:
    """Guard: `features.customer` already existed, so the folder rename would merge into it."""
    renames = {"wcm": "fsm", "wcm.features.kunde": "fsm.features.customer"}
    names = frozenset({"wcm.features.kunde", "wcm.features.customer"})

    assert not rename_holds(renames, names=names, observed=frozenset())


def test_two_unrelated_packages_that_would_nest_are_no_rename() -> None:
    """Guard: `c.x` inside `c` would overlap it, and an overlapped module is owned by nobody."""
    names = frozenset({"a", "b"})

    assert not rename_holds({"a": "c", "b": "c.x"}, names=names, observed=frozenset())


def test_a_new_name_the_old_contract_already_used_is_no_rename() -> None:
    """Guard: a grant the old contract gave `shop.view` would pass to the renamed package."""
    names = frozenset({"shop.render", "shop.view.legacy"})

    assert not rename_holds(_RENDER, names=names, observed=frozenset())


def test_a_rule_prefix_that_covers_only_one_side_is_no_rename() -> None:
    """Guard: a rule on `other` would newly cover the code, one on `shop` would stop covering it."""
    moved_out = {"shop.render": "other.view"}

    assert not rename_holds(
        moved_out, names=frozenset({"shop.render", "other"}), observed=frozenset()
    )
    assert not rename_holds(
        moved_out, names=frozenset({"shop.render", "shop"}), observed=frozenset()
    )


def test_a_name_already_under_a_new_prefix_is_no_rename() -> None:
    """The renamed prefix `shop` would come to hold `store_app.legacy`, which it did not."""
    names = frozenset({"shop.model", "store_app.legacy"})

    assert not rename_holds({"shop": "store_app"}, names=names, observed=frozenset())


def test_a_module_left_under_an_old_name_is_no_rename() -> None:
    """Guard: copied rather than moved, the old module would be governed by nothing renamed."""
    modules = frozenset({"shop.view.text", "shop.render.text"})

    assert not rename_holds(_RENDER, names=frozenset({"shop.render"}), observed=modules)


@pytest.mark.parametrize("module", ["shop.render.text-legacy", "shop.render.2fa"])
def test_a_module_under_an_old_prefix_is_no_rename_whatever_its_file_is_called(
    module: str,
) -> None:
    """Guard (QA c5, c6): a file name no identifier spells still lies under the old prefix."""
    modules = frozenset({"shop.view.text", module})

    assert not rename_holds(_RENDER, names=frozenset({"shop.render"}), observed=modules)


def test_a_candidate_that_turns_nesting_inside_out_is_no_rename() -> None:
    """Guard (review P1): `a.s.t -> q` would lift a renamed prefix above the `a.s` holding it."""
    before = _contract(_component("C1", "a.c"), _component("C2", "a.s.t.r.s.w"))
    after = _contract(_component("C1", "q.r.c"), _component("C2", "q.r.s.w"))
    candidate = rename_candidates(before, after)[0]
    names = frozenset({"a.c", "a.s.t.r.s.w", "a.s"})

    assert candidate == {"a": "q.r", "a.s.t": "q"}
    assert not rename_holds(candidate, names=names, observed=frozenset({"q.r.c.m", "q.r.s.w.m"}))


def test_a_rename_places_its_old_prefixes_where_the_layout_reads_them() -> None:
    before = _shop_contract(_SHOP)
    after = _shop_contract(_SHOP.replace('"shop.render', '"shop.view'))
    common = {"violations": (), "budgets": (), "observed": frozenset({"shop.view.text"})}

    (flat, *_) = renames_since(before, after, **common, layouts=_FLAT)
    (source,) = renames_since(before, after, **common, layouts=frozenset({("", "src")}))

    assert flat.directories == ("shop/render",)
    assert source.directories == ("src/shop/render",)


def test_the_renamed_contract_equals_the_one_renamed_by_hand() -> None:
    before = _shop_contract((FIXTURE_DIR / "architecture-contract.json").read_text())
    after_text = renamed_render()["architecture-contract.json"]
    assert after_text is not None
    after = _shop_contract(after_text)

    assert contract_widenings(before, after)
    assert renamed_contract(before, _RENDER) == after


def test_a_rename_leaves_every_value_that_names_no_module_alone() -> None:
    """QA h2b: root `agent` renamed `architect` must not turn each `decided_by` with it."""
    before_text = _moved_root(_SHOP, "shop", "agent").replace(
        '"decided_by": "architect"', '"decided_by": "agent"'
    )
    before = _shop_contract(before_text)
    after = _shop_contract(_moved_root(before_text, "agent", "architect"))

    (moved, *_) = renames_since(
        before,
        after,
        violations=(),
        budgets=(),
        observed=frozenset({"architect.model.entities"}),
        layouts=_FLAT,
    )

    assert moved.prefixes == (("agent", "architect"),)
    findings = contract_widenings(moved.contract, after)
    assert "component 'model'.decided_by changed from 'agent' to 'architect'" in findings
    assert "rule DEP-MODEL-NO-STORE.decided_by changed from 'agent' to 'architect'" in findings
    # One line per decision, the moved inside path besides.
    assert len(findings) == len(before.components) + len(before.rules) + 1


def test_a_root_package_named_like_a_construct_keeps_the_construct() -> None:
    """QA h3: `eval` is the root package and a forbidden construct; only the package moves."""
    before = _shop_contract(_moved_root(_SHOP, "shop", "eval"))

    moved = renamed_contract(before, {"eval": "evals"})

    # A path is no module name, so the inside contract's path stays where it was.
    expected = _moved_root(_SHOP, "shop", "evals").replace('"evals/', '"eval/')
    assert contract_widenings(moved, _shop_contract(expected)) == ()
    assert any(
        "eval" in rule.constructs
        for rule in moved.rules
        if isinstance(rule, ForbiddenConstructRule)
    )


def test_a_package_named_like_a_label_is_renamed_without_the_label() -> None:
    """QA g3b: the Dart package `app` shares its name with the component label `app`."""
    before_text = _moved_root(_DART, "shop", "app")
    after_text = (
        before_text.replace('"app.', '"field_app.')
        .replace('"source": "app"', '"source": "field_app"')
        .replace('"root": "app"', '"root": "field_app"')
    )
    before, after = _shop_contract(before_text), _shop_contract(after_text)

    (moved, *_) = renames_since(
        before,
        after,
        violations=(),
        budgets=(),
        observed=frozenset({"field_app.main"}),
        layouts=frozenset({("field_app", "lib")}),
    )

    assert moved.prefixes == (("app", "field_app"),)
    assert contract_widenings(moved.contract, after) == ()
    # The package renamed in its pubspec reads its old names from the same `lib`.
    assert moved.directories == ("lib",)
    assert (
        renames_since(
            before,
            after,
            violations=(),
            budgets=(),
            observed=frozenset({"field_app.main"}),
            layouts=frozenset({("other", "lib")}),
        )
        == ()
    )


def test_a_root_renamed_like_a_label_is_a_rename_with_its_label_cycle_entries() -> None:
    """QA c9: root `shop` becomes `app`, the label of one component, which a cycle entry names."""
    cycle = KnownViolation(ViolationFingerprint(("COMPONENT-NO-CYCLES",), ("app", "render")), 1)
    before = _shop_contract(_SHOP)
    after = _shop_contract(_moved_root(_SHOP, "shop", "app"))

    (moved, *_) = renames_since(
        before,
        after,
        violations=(cycle,),
        budgets=(),
        observed=frozenset({"app.model.entities"}),
        layouts=_FLAT,
    )

    assert moved.prefixes == (("shop", "app"),)
    assert moved.violations == (cycle,)
    assert contract_widenings(moved.contract, after) == (
        "component 'store'.inside changed from 'shop/store/architecture-contract.json' "
        "to 'app/store/architecture-contract.json'",
    )


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


def _import_from_app(root: Path, statement: str) -> None:
    orders = root / "shop/app/orders.py"
    orders.write_text(orders.read_text() + f"\n{statement}\n")


def test_an_import_of_a_module_left_unread_under_the_old_name_is_no_rename(tmp_path: Path) -> None:
    """QA k1: a compiled `shop/render/legacy.pyc` the scan never reads, imported by shop.app."""
    root = _prepare_repo(tmp_path, {})
    base = _git(root, "rev-parse", "HEAD")
    apply_overlay(root, renamed_render())
    source = root / "shop/render/legacy.py"
    source.parent.mkdir(exist_ok=True)
    source.write_text("from shop.store.sqlite import vacuum\n\nV = vacuum\n")
    py_compile.compile(str(source), cfile=str(root / "shop/render/legacy.pyc"), doraise=True)
    source.unlink()
    _import_from_app(root, "from shop.render.legacy import V as _leak")

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base)

    assert (result.exit_code, result.renames) == (1, ())
    assert (
        "component 'render'.packages changed from ('shop.render',) to ('shop.view',)"
        in result.failures
    )


def test_an_import_of_the_copy_left_outside_narrowed_roots_is_no_rename(tmp_path: Path) -> None:
    """QA j1: shop/render copied rather than moved, left outside the roots, and imported."""
    root = _prepare_repo(tmp_path, {})
    base = _git(root, "rev-parse", "HEAD")
    shutil.copytree(root / "shop/render", root / "shop/view")
    overlay = renamed_render()
    del overlay["shop/render/text.py"], overlay["shop/view/text.py"]
    apply_overlay(root, overlay)
    _import_from_app(root, "from shop.render.text import render_order as _leak")
    config = replace(
        SHOP_CONFIG, roots=("shop/app", "shop/cli", "shop/model", "shop/store", "shop/view")
    )

    result, _ = run_validate(root, config, observe, against=base)

    assert (result.exit_code, result.renames) == (1, ())


_NARROWED = ("shop/app", "shop/cli", "shop/model", "shop/store", "shop/view")


def test_a_copy_left_outside_narrowed_roots_is_no_rename(tmp_path: Path) -> None:
    """QA j2: nothing imports the copy; it is left where the narrowed roots no longer read."""
    root = _prepare_repo(tmp_path, {})
    base = _git(root, "rev-parse", "HEAD")
    shutil.copytree(root / "shop/render", root / "shop/view")
    overlay = renamed_render()
    del overlay["shop/render/text.py"], overlay["shop/view/text.py"]
    apply_overlay(root, overlay)

    result, _ = run_validate(root, replace(SHOP_CONFIG, roots=_NARROWED), observe, against=base)

    assert (result.exit_code, result.renames) == (1, ())


def test_a_move_with_narrowed_roots_is_still_a_rename(tmp_path: Path) -> None:
    """QA j3: the same roots with the package really moved leave nothing behind to read."""
    root = _prepare_repo(tmp_path, {})
    base = _git(root, "rev-parse", "HEAD")
    apply_overlay(root, renamed_render())
    (root / "shop/render").rmdir()

    result, _ = run_validate(root, replace(SHOP_CONFIG, roots=_NARROWED), observe, against=base)

    assert (result.exit_code, result.failures) == (0, ())
    assert result.renames == (("shop.render", "shop.view"),)


def test_a_rename_the_old_contract_cannot_parse_under_stays_amendable(tmp_path: Path) -> None:
    """QA b3b: one level down, `shop.ui.render` is no immediate child for ROOT-LAYOUT."""
    root = _prepare_repo(tmp_path, {})
    base = _git(root, "rev-parse", "HEAD")
    contract = json.loads(_SHOP.replace('"shop.render', '"shop.ui.render'))
    layout = next(rule for rule in contract["rules"] if rule["id"] == "ROOT-LAYOUT")
    layout["allowed_children"] = ["shop.app", "shop.cli", "shop.model", "shop.store", "shop.ui"]
    main = (FIXTURE_DIR / "shop/cli/main.py").read_text()
    apply_overlay(
        root,
        {
            "shop/render/text.py": None,
            "shop/ui/render/text.py": (FIXTURE_DIR / "shop/render/text.py").read_text(),
            "shop/cli/main.py": main.replace("shop.render", "shop.ui.render"),
            "architecture-contract.json": json.dumps(contract, indent=2) + "\n",
        },
    )

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base)
    amendment = root / "amendment.json"
    amended, files = run_validate(
        root,
        SHOP_CONFIG,
        observe,
        against=base,
        amendment=amendment,
        write_amendment=True,
        decided_by="Demo architect",
        rationale="shop.render moved below shop.ui.",
    )

    assert (result.exit_code, result.renames) == (1, ())
    assert (
        "component 'render'.packages changed from ('shop.render',) to ('shop.ui.render',)"
        in result.failures
    )
    assert (amended.exit_code, amended.artifact) == (0, str(amendment))
    assert str(amendment) in files


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
