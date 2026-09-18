# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Draw the onboarding loop as a swimlane SVG, from the run that produced its numbers.

The picture is derived, never written by hand: it renders the same `Step` values
`tests/test_onboarding_demo.py` asserts, so a figure that disagrees with the tool is a
failing test rather than a stale drawing. Colours are the report's own (AD-19).
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape

from fixtures.reproduce_onboarding import Step, run_onboarding_demo

LANES = ("agent", "gate", "architect")
LANE_TITLE = {
    "agent": "AGENT",
    "gate": "ARCHKEEL",
    "architect": "ARCHITECT",
}
LANE_NOTE = {
    "agent": "reads and drafts",
    "gate": "refuses or passes",
    "architect": "decides",
}
# docs/report-visual-system.md: teal is candidate evidence, lime accepted, amber not checked.
LANE_COLOR = {"agent": "#5EEAD4", "gate": "#F4C95D", "architect": "#C5F82A"}
FAIL = "#FF6B6B"

WIDTH = 980
LANE_X = {"agent": 40, "gate": 350, "architect": 660}
CARD_W = 280
CARD_H = 128
ROW_Y = 138
ROW_GAP = 184
FOOT = 44
CONNECTOR = "#6E6E66"
CORNER = 12


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _lanes(height: int) -> list[str]:
    """A band per lane, so a reader six rows down still knows whose column this is."""
    return [
        f'<rect x="{LANE_X[lane] - 16}" y="88" width="{CARD_W + 32}" height="{height - 118}" '
        'rx="14" fill="#090909"/>'
        for lane in LANES
    ]


def _header() -> list[str]:
    parts = [
        '<text x="40" y="42" fill="#E8E8E2" font-size="19" font-weight="600">'
        "How an architecture contract comes to exist</text>",
        '<text x="40" y="66" fill="#8A8A84" font-size="12.5">'
        "Every box is one real command. The agent reads and drafts; only the architect "
        "decides; the gate refuses the rest.</text>",
    ]
    for lane in LANES:
        x = LANE_X[lane]
        parts.append(
            f'<text x="{x}" y="102" fill="{LANE_COLOR[lane]}" font-size="11" '
            f'font-weight="700" letter-spacing="1.4">{LANE_TITLE[lane]}</text>'
        )
        parts.append(
            f'<text x="{x}" y="118" fill="#8A8A84" font-size="10.5">{LANE_NOTE[lane]}</text>'
        )
    return parts


def _card(index: int, step: Step, y: int) -> list[str]:
    x = LANE_X[step.actor]
    color = FAIL if step.outcome.startswith("FAIL") else LANE_COLOR[step.actor]
    parts = [
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="10" '
        'fill="#141414" stroke="#2A2A28"/>',
        f'<rect x="{x}" y="{y}" width="3" height="{CARD_H}" rx="1.5" fill="{color}"/>',
        f'<circle cx="{x + 26}" cy="{y + 24}" r="10" fill="none" stroke="{color}" '
        'stroke-width="1.2"/>',
        f'<text x="{x + 26}" y="{y + 28}" fill="{color}" font-size="11" font-weight="700" '
        f'text-anchor="middle">{index}</text>',
    ]
    for offset, line in enumerate(_wrap(step.title, 30)[:2]):
        parts.append(
            f'<text x="{x + 46}" y="{y + 24 + offset * 15}" fill="#E8E8E2" font-size="12.5" '
            f'font-weight="600">{escape(line)}</text>'
        )
    command = _wrap(f"$ {step.command}", 44)[:2]
    for offset, line in enumerate(command):
        parts.append(
            f'<text x="{x + 16}" y="{y + 68 + offset * 13}" fill="#8A8A84" font-size="9.8" '
            f'font-family="ui-monospace, Menlo, monospace">{escape(line)}</text>'
        )
    for offset, line in enumerate(_wrap(step.outcome, 40)[:2]):
        parts.append(
            f'<text x="{x + 16}" y="{y + 102 + offset * 13}" fill="{color}" font-size="10.5">'
            f"{escape(line)}</text>"
        )
    return parts


def _arrow(previous: Step, step: Step, y: int) -> str:
    """An elbow from the card above into this one, so the lane change is the visible thing.

    Orthogonal rather than curved: over 300 horizontal pixels a bezier flattens into a stray
    diagonal, while down-across-down reads as a handoff even at README width.
    """
    start_x = LANE_X[previous.actor] + CARD_W / 2
    end_x = LANE_X[step.actor] + CARD_W / 2
    start_y = y - ROW_GAP + CARD_H
    mid = start_y + (ROW_GAP - CARD_H) / 2
    end_y = y - 10
    if start_x == end_x:
        return (
            f'<path d="M {start_x} {start_y} V {end_y}" fill="none" stroke="{CONNECTOR}" '
            f'stroke-width="1.8" marker-end="url(#tip)"/>'
        )
    step_x = CORNER if end_x > start_x else -CORNER
    path = (
        f"M {start_x} {start_y} V {mid - CORNER} "
        f"Q {start_x} {mid} {start_x + step_x} {mid} "
        f"H {end_x - step_x} "
        f"Q {end_x} {mid} {end_x} {mid + CORNER} "
        f"V {end_y}"
    )
    return (
        f'<path d="{path}" fill="none" stroke="{CONNECTOR}" stroke-width="1.8" '
        f'stroke-linecap="round" marker-end="url(#tip)"/>'
    )


def render(steps: tuple[Step, ...]) -> str:
    height = ROW_Y + len(steps) * ROW_GAP + FOOT
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" font-family="ui-sans-serif, system-ui, '
        'Segoe UI, Roboto, sans-serif">',
        '<defs><marker id="tip" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto"><path d="M 0 0 L 9 5 L 0 10 z" fill="{CONNECTOR}"/>'
        "</marker></defs>",
        '<rect width="100%" height="100%" fill="#000000"/>',
        *_lanes(height),
        *_header(),
    ]
    for index, step in enumerate(steps, start=1):
        y = ROW_Y + (index - 1) * ROW_GAP
        if index > 1:
            parts.append(_arrow(steps[index - 2], step, y))
        parts.extend(_card(index, step, y))
    parts.append(
        f'<text x="40" y="{height - 16}" fill="#8A8A84" font-size="11.5">'
        "The agent never decides a boundary, and the gate never guesses one."
        "</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main(argv: list[str]) -> int:
    """Render the loop from one real run; the temporary repository never outlives it."""
    if len(argv) != 1:
        print("usage: python -m tools.onboarding_svg <output.svg>", file=sys.stderr)
        return 2
    with TemporaryDirectory(prefix="archkeel-onboarding-svg-") as temporary:
        Path(argv[0]).write_text(render(run_onboarding_demo(Path(temporary))))
    print(f"Wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
