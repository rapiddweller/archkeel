# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Report and Explorer label token pairs meet WCAG 2.1 AA in both themes."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "native/report/assets/tokens.css"
PAIRS = (
    ("--ink-muted", "--surface-1"),  # report language tags, Explorer chips and table labels
    ("--ink-muted", "--surface-2"),  # Explorer perspective chips and generic badges
    ("--ink", "--surface-1"),  # Explorer language tags, kind markers and SVG chips
    ("--ink", "--surface-2"),  # report code-like chips
    ("--pass", "--surface-1"),  # Explorer status text
    ("--fail", "--surface-1"),
    ("--unknown", "--surface-1"),
    ("--accent-text", "--surface-1"),  # Explorer informational status text
    ("--unknown-text", "--unknown-subtle"),  # status pill
    ("--pass-text", "--pass-subtle"),
    ("--fail-text", "--fail-subtle"),
    ("--fail", "--surface-0"),  # atlas finding label
    ("--accent-text", "--surface-0"),  # atlas deviation label
    ("--fail-text", "--surface-1"),  # diagram status labels
    ("--unknown-text", "--surface-1"),
)
CSS_PAIRS = {
    "native/report/assets/report.css": (
        ("--ink-muted", "--surface-1"),  # .rp-row__box .tag and .rp-kind .tag
    ),
    "native/report/assets/explorer/explorer.css": (
        ("--pass", "--surface-1"),
        ("--fail", "--surface-1"),
        ("--unknown", "--surface-1"),
        ("--accent-text", "--surface-1"),
        ("--ink", "--surface-1"),
        ("--unknown-text", "--unknown-subtle"),
        ("--pass-text", "--pass-subtle"),
        ("--fail-text", "--fail-subtle"),
        ("--ink-muted", "--surface-1"),
    ),
    "native/report/assets/bundle.css": (
        ("--ink-muted", "--surface-2"),
        ("--pass-text", "--pass-subtle"),
        ("--fail-text", "--fail-subtle"),
        ("--unknown-text", "--unknown-subtle"),
        ("--fail-text", "--surface-1"),
        ("--unknown-text", "--surface-1"),
    ),
}


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _theme_tokens(source: str, theme: str) -> dict[str, str]:
    pattern = (
        r":root,\[data-theme=\"dark\"\]\{([^}]*)\}"
        if theme == "dark"
        else r'\[data-theme="light"\]\{([^}]*)\}'
    )
    block = re.search(pattern, source)
    assert block, f"missing {theme} theme tokens"
    return dict(re.findall(r"(--[^:]+):([^;]+)", block.group(1)))


def test_report_and_explorer_label_token_pairs_meet_aa_in_both_themes() -> None:
    source = TOKENS.read_text(encoding="utf-8")
    all_pairs = set(PAIRS)
    for relative, pairs in CSS_PAIRS.items():
        css = (ROOT / relative).read_text(encoding="utf-8")
        all_pairs.update(pairs)
        for foreground, background in pairs:
            assert foreground in css and background in css, (
                f"{relative} must use {foreground} on {background}"
            )
    for theme in ("dark", "light"):
        tokens = _theme_tokens(source, theme)
        for foreground, background in sorted(all_pairs):
            levels = sorted((_luminance(tokens[foreground]), _luminance(tokens[background])))
            ratio = (levels[1] + 0.05) / (levels[0] + 0.05)
            assert ratio >= 4.5, f"{theme}: {foreground} on {background} is {ratio:.2f}:1"
