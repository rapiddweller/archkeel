# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The showcase checks a TypeScript boundary even when the import has no runtime effect."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import pytest
from core_support import run

from archkeel.cli import core_only
from tools.fixture_tree import fixture_tree
from tools.report_gallery import ROOT, showcase_runs, violation_block


@pytest.mark.parametrize(
    ("name", "status", "exit_code"),
    [
        ("H-typescript-checkout", "PASS", 0),
        ("H-typescript-checkout-plant-http-type", "FAIL", 1),
    ],
)
def test_checkout_keeps_http_types_out_of_the_domain(
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    status: str,
    exit_code: int,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    entry = {entry["name"]: entry for entry in showcase_runs()}[name]
    source = ROOT / "fixtures" / entry["root"]
    plant = entry.get("plant")
    page = tmp_path / "report.html"
    with fixture_tree(source, plant["edits"]) if plant else nullcontext(source) as root:
        code, envelope = run(
            "report", "--root", str(root), "--output", str(page), "--format", "html", "--topology"
        )
    frame = envelope["frame"]
    rule = "CHECKOUT-DOMAIN-NO-HTTP"
    assert code == exit_code and envelope["status"] == status
    assert frame["scope"] == "complete"
    assert frame["rules"] == {
        rule: ["forbidden_dependency", status],
        "CHECKOUT-HTTP-USES-DOMAIN": ["allowed_dependency", "DECLARATION"],
    }
    if plant:
        [detail] = frame["details"][rule]
        assert (detail["source"], detail["target"]) == (
            "checkout.src.domain.order_x2e_ts",
            "checkout.src.http.order_x2e_ts",
        )
        assert {"path": "src/domain/order.ts", "line": 1} in [
            frame["locations"][key] for key in detail["evidence"]
        ]
        assert violation_block(page, plant) is not None
    else:
        [edge] = frame["topology"]["edges"]
        assert (edge["source"], edge["target"], edge["resolution"]) == (
            "checkout.src.http.order_x2e_ts",
            "checkout.src.domain.order_x2e_ts",
            "resolved",
        )
        assert edge["evidence"] == [{"path": "src/http/order.ts", "line": 1}]
