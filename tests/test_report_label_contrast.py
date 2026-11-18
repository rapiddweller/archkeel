# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Report and Explorer label token pairs meet WCAG 2.1 AA in both themes."""

import itertools
import math
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
LANGUAGES = ("python", "rust", "typescript", "dart", "other")
COLOR_VISION_LANGUAGES = ("python", "rust", "typescript", "dart")
STATUS_COLORS = ("--pass", "--fail", "--unknown", "--accent")
MACHADO = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
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


def _rgb(color: str) -> tuple[float, float, float]:
    return tuple(int(color[index : index + 2], 16) / 255 for index in (1, 3, 5))


def _lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in rgb)
    x = (0.4124564 * red + 0.3575761 * green + 0.1804375 * blue) / 0.95047
    y = 0.2126729 * red + 0.7151522 * green + 0.0721750 * blue
    z = (0.0193339 * red + 0.1191920 * green + 0.9503041 * blue) / 1.08883

    def pivot(value: float) -> float:
        return value ** (1 / 3) if value > (6 / 29) ** 3 else value / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = (pivot(value) for value in (x, y, z))
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _delta_e_2000(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    light1, a1, b1 = _lab(first)
    light2, a2, b2 = _lab(second)
    chroma1, chroma2 = math.hypot(a1, b1), math.hypot(a2, b2)
    mean_chroma = (chroma1 + chroma2) / 2
    g = 0.5 * (1 - math.sqrt(mean_chroma**7 / (mean_chroma**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    hue1, hue2 = math.degrees(math.atan2(b1, a1p)) % 360, math.degrees(math.atan2(b2, a2p)) % 360
    delta_hue = hue2 - hue1
    if c1p * c2p == 0:
        delta_hue = 0
    elif delta_hue > 180:
        delta_hue -= 360
    elif delta_hue < -180:
        delta_hue += 360
    delta_l, delta_c = light2 - light1, c2p - c1p
    delta_h = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(delta_hue / 2))
    mean_l, mean_c = (light1 + light2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        mean_h = hue1 + hue2
    elif abs(hue1 - hue2) <= 180:
        mean_h = (hue1 + hue2) / 2
    elif hue1 + hue2 < 360:
        mean_h = (hue1 + hue2 + 360) / 2
    else:
        mean_h = (hue1 + hue2 - 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(mean_h - 30))
        + 0.24 * math.cos(math.radians(2 * mean_h))
        + 0.32 * math.cos(math.radians(3 * mean_h + 6))
        - 0.20 * math.cos(math.radians(4 * mean_h - 63))
    )
    sl = 1 + 0.015 * (mean_l - 50) ** 2 / math.sqrt(20 + (mean_l - 50) ** 2)
    sc, sh = 1 + 0.045 * mean_c, 1 + 0.015 * mean_c * t
    rt = (
        -2
        * math.sqrt(mean_c**7 / (mean_c**7 + 25**7))
        * math.sin(math.radians(60 * math.exp(-(((mean_h - 275) / 25) ** 2))))
    )
    return math.sqrt(
        (delta_l / sl) ** 2
        + (delta_c / sc) ** 2
        + (delta_h / sh) ** 2
        + rt * (delta_c / sc) * (delta_h / sh)
    )


def _simulate_cvd(
    rgb: tuple[float, float, float], matrix: tuple[tuple[float, ...], ...]
) -> tuple[float, float, float]:
    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    def encode(channel: float) -> float:
        channel = max(0, min(1, channel))
        return 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055

    source = tuple(linear(channel) for channel in rgb)
    return tuple(encode(sum(row[index] * source[index] for index in range(3))) for row in matrix)


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

        language_colors = {language: _rgb(tokens[f"--lang-{language}"]) for language in LANGUAGES}
        for language in LANGUAGES:
            text = tokens[f"--lang-{language}-text"]
            background = tokens[f"--lang-{language}-subtle"]
            levels = sorted((_luminance(text), _luminance(background)))
            ratio = (levels[1] + 0.05) / (levels[0] + 0.05)
            assert ratio >= 4.5, f"{theme}: {language} badge text is {ratio:.2f}:1"
            # WCAG 1.4.11: the frame is a UI boundary: 3:1 against its own fill and against each
            # surface that a box or the perspective bar can have.
            border = tokens[f"--lang-{language}"]
            for other in (background, *(tokens[f"--surface-{n}"] for n in (1, 2, 3))):
                levels = sorted((_luminance(border), _luminance(other)))
                ratio = (levels[1] + 0.05) / (levels[0] + 0.05)
                assert ratio >= 3.0, f"{theme}: {language} frame on {other} is {ratio:.2f}:1"
        for first, second in itertools.combinations(LANGUAGES, 2):
            assert _delta_e_2000(language_colors[first], language_colors[second]) > 20
        for language, status in itertools.product(LANGUAGES, STATUS_COLORS):
            assert _delta_e_2000(language_colors[language], _rgb(tokens[status])) > 20
        for matrix in MACHADO.values():
            simulated = {
                name: _simulate_cvd(language_colors[name], matrix)
                for name in COLOR_VISION_LANGUAGES
            }
            for first, second in itertools.combinations(COLOR_VISION_LANGUAGES, 2):
                assert _delta_e_2000(simulated[first], simulated[second]) > 20


def test_language_badges_share_the_token_style_on_nodes_chips_and_legend() -> None:
    css = (ROOT / "native/report/assets/explorer/explorer.css").read_text(encoding="utf-8")
    canvas = (ROOT / "native/report/assets/explorer/report-canvas.js").read_text(encoding="utf-8")
    presentation = (ROOT / "native/report/assets/explorer/report-presentation.js").read_text(
        encoding="utf-8"
    )
    assert "ak-language-badge" in css and "ak-language-legend" in css
    assert "ak-language-badge" in presentation and "languageNames.map(languageBadge)" in canvas
    for language in COLOR_VISION_LANGUAGES:
        assert f'data-language="{language}"' in css
        assert f"--lang-{language}" in css
