# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The perspective bar of the Explorer wraps its chips: none is cut off or unreachable."""

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "native/report/assets/explorer/explorer.css"


def _rule(selector: str) -> str:
    """The declarations of every plain rule for `selector` (not inside a media query)."""
    source = CSS.read_text(encoding="utf-8")
    pattern = re.compile(r"^" + re.escape(selector) + r"\s*\{([^}]*)\}", re.MULTILINE)
    return " ".join(match.group(1) for match in pattern.finditer(source))


def test_the_bottom_bar_wraps_its_chips_and_never_scrolls_them_out_of_sight() -> None:
    rule = _rule(".rp-explorer .ak-bottom-center")
    assert "flex-wrap: wrap" in rule
    assert "overflow-x" not in rule, "a sideways scroll hides the last chip with no cue"
    assert "nowrap" not in rule
    # The bar sits on its bottom edge, so a second row grows upward into the canvas.
    assert "bottom:" in rule
