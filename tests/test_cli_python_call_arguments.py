# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The rule binds explicit actuals of live direct calls to observed formals."""

from pathlib import Path

import pytest
from core_support import ROOT
from test_cli_native_python_imports import verdict

from tools.fixture_tree import fixture_tree

SHOP = ROOT / "fixtures/F-architecture"
RULE = "APP-NO-LITERAL-ORDER-ID"


@pytest.mark.parametrize(
    ("actuals", "status"),
    [
        ("root, order_id", "PASS"),
        ("root, ''", "FAIL"),
        ("order_id='a' 'b', root=root", "FAIL"),
        ("root, f'{order_id}'", "PASS"),
        ("root, *[order_id]", "UNKNOWN"),
        ("root, order_id, order_id='duplicate'", "UNKNOWN"),
        ("root", "UNKNOWN"),
    ],
)
def test_call_argument_binds_only_explicit_actuals(
    release_core: Path, actuals: str, status: str
) -> None:
    with fixture_tree(SHOP) as root:
        source = root / "shop/store/lookup.py"
        text = source.read_text(encoding="utf-8")
        source.write_text(
            text.replace("lookup_order(root, order_id)", f"lookup_order({actuals})"),
            encoding="utf-8",
        )
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"][RULE] == ["forbidden_call_argument", status]
    if status == "FAIL":
        [finding] = frame["details"][RULE]
        assert finding["target"] == "shop.store.lookup.lookup_order.order_id"
        assert finding["cause"] == "written string literal passed to restricted parameter"


def test_a_variadic_target_without_selected_calls_stays_open(release_core: Path) -> None:
    with fixture_tree(SHOP) as root:
        source = root / "shop/store/lookup.py"
        text = source.read_text(encoding="utf-8")
        source.write_text(
            text.replace(
                "def lookup_order(root: Path, order_id: str)",
                "def lookup_order(root: Path, order_id: str, *other: str)",
            ).replace("return lookup_order(root, order_id)", "return root"),
            encoding="utf-8",
        )
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"][RULE] == ["forbidden_call_argument", "UNKNOWN"]
