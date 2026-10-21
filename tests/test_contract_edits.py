# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#601: three representative contract edits on the shared fixture, reviewed with --against."""

import json
import subprocess
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_review_workflow_fixture import CONFIG, FIXTURE

from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.model import ContractChangeDirection

_WIDENED = ContractChangeDirection.WIDENED
_NARROWED = ContractChangeDirection.NARROWED


def _edit_json(path: Path, change) -> None:
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document, indent=2) + "\n")


def _component(document: dict, component_id: str) -> dict:
    return next(item for item in document["components"] if item["id"] == component_id)


def _tighten_checkout_to_save(root: Path) -> None:
    def change(document: dict) -> None:
        for entry in _component(document, "checkout")["requires"]:
            if entry["component"] == "storage":
                entry["through"] = ["orders.storage:save"]

    _edit_json(root / "architecture-contract.json", change)


def _checkout_owns_quote(root: Path) -> None:
    service = root / "orders/checkout/service.py"
    service.write_text(
        service.read_text().replace(
            "\n\ndef place(",
            "\n\ndef quote(sku: str, quantity: int, region: str, coupon: str | None = None)"
            " -> int:\n"
            '    if quantity <= 0:\n        raise ValueError("quantity must be positive")\n'
            "    return round_cents(price(sku, quantity, region, coupon))\n\n\ndef place(",
        )
    )
    package = root / "orders/checkout/__init__.py"
    package.write_text(
        package.read_text()
        .replace("import place\n", "import place, quote\n")
        .replace('["Receipt", "place"]', '["Receipt", "place", "quote"]')
    )
    api = root / "orders/api.py"
    api.write_text(
        api.read_text()
        .replace(
            "from orders.checkout.rounding import round_cents\n",
            "from orders.checkout import quote as checkout_quote\n",
        )
        .replace("from orders.pricing import price\n", "")
        .replace(
            "    return round_cents(price(slugify(sku), quantity, region, coupon))",
            "    return checkout_quote(slugify(sku), quantity, region, coupon)",
        )
    )

    def root_change(document: dict) -> None:
        _component(document, "checkout")["public"] = ["orders.checkout"]
        entry = _component(document, "entry")
        entry["requires"] = [
            item
            for item in entry["requires"]
            if item["component"] != "pricing"
            and item["through"] != ["orders.checkout.rounding:round_cents"]
        ]

    def inside_change(document: dict) -> None:
        document["components"][0]["public"] = [
            "orders.checkout.service:place",
            "orders.checkout.service:quote",
        ]

    _edit_json(root / "architecture-contract.json", root_change)
    _edit_json(root / "contracts/checkout.json", inside_change)
    target = root / "docs/target.md"
    target.write_text(target.read_text().replace("    entry --> pricing\n", ""))


def _changes(tmp_path: Path, edit) -> set[tuple[ContractChangeDirection, str]]:
    root = _prepare_repo(tmp_path, {}, fixture=FIXTURE)
    edit(root)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "edit"], cwd=root, check=True
    )
    result, _ = run_validate(root, CONFIG, observe, against="HEAD~1")
    assert {row.status for row in result.rule_assessments or ()} == {"PASS"}
    return {(change.direction, change.message) for change in result.contract_changes or ()}


def test_tightening_a_dependency_narrows_without_an_amendment(tmp_path: Path) -> None:
    changes = _changes(tmp_path, _tighten_checkout_to_save)

    assert changes == {
        (
            _NARROWED,
            "component 'checkout'.requires['storage'] narrowed from [['orders.storage']] "
            "to [['orders.storage:save']]",
        )
    }


def test_moving_an_operation_shows_what_widened_and_what_narrowed(tmp_path: Path) -> None:
    changes = _changes(tmp_path, _checkout_owns_quote)

    assert (
        _WIDENED,
        "component 'Checkout operation'.public gained 'orders.checkout.service:quote'",
    ) in changes
    assert (
        _NARROWED,
        "component 'checkout'.public lost 'orders.checkout.rounding:round_cents'",
    ) in changes
    assert any(
        direction is _NARROWED and "'entry'.requires['pricing'] dropped" in message
        for direction, message in changes
    )


@pytest.mark.parametrize("edit", [_tighten_checkout_to_save, _checkout_owns_quote])
def test_contract_changes_are_absent_without_against(tmp_path: Path, edit) -> None:
    root = _prepare_repo(tmp_path, {}, fixture=FIXTURE)
    edit(root)
    result, _ = run_validate(root, CONFIG, observe)
    assert result.contract_changes is None
