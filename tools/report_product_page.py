# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The entry page of the site: ArchKeel as a product, two parts and two runs (AD-462).

It uses the files of the report page (AD-496): the fonts, the tokens, the components, the local
rules and the one theme script, so the two look the same. The page copies the facts of
`report_product.Part`. It joins no verdict: the heading names the worst status of the two runs.
"""

from __future__ import annotations

import base64
import hashlib
import html
from collections.abc import Sequence
from pathlib import Path

from tools.report_product import LISTED_LIMIT, STATUSES, Part, Tile, worst

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "native" / "report" / "assets"
LOCAL = Path(__file__).with_name("report_product.css")
SHOWCASE = "showcase/index.html"

SUN = (
    '<circle cx="8" cy="8" r="2.6"/><path d="M8 1.8v1.6M8 12.6v1.6M1.8 8h1.6M12.6 8h1.6M3.6 '
    '3.6l1.1 1.1M11.3 11.3l1.1 1.1M3.6 12.4l1.1-1.1M11.3 4.7l1.1-1.1"/>'
)
ICONS = {
    "PASS": '<path d="M3 8.5l3.2 3L13 4.5"/>',
    "FAIL": '<path d="M4 4l8 8M12 4l-8 8"/>',
    "UNKNOWN": '<path d="M6 6.2a2.1 2.1 0 1 1 3 1.9c-.7.4-1 .8-1 1.6"/><path d="M8 12.2v.01"/>',
    "part": '<rect x="1.8" y="2.8" width="12.4" height="10.4" rx="1.5"/><path d="M1.8 6h12.4"/>',
    "light": SUN,
    "dark": '<path d="M13.2 9.6A5.4 5.4 0 0 1 6.4 2.8a5.4 5.4 0 1 0 6.8 6.8z"/>',
}
NOTES = {
    "PASS": "No violation. No unknown.",
    "FAIL": "A violation is a fact of this run. An unknown rule is not a pass.",
    "UNKNOWN": "No violation found, but the run cannot decide every rule. UNKNOWN is not a pass.",
}
ARROW = (
    '<svg width="84" height="14" viewBox="0 0 84 14" aria-hidden="true" fill="none" '
    'stroke="currentColor" stroke-width="1.5"><path d="M1 5H73M1 9H73"/>'
    '<path d="M74 1.5L82.5 7L74 12.5"/></svg>'
)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def plural(count: int, one: str) -> str:
    many = f"{one[:-1]}ies" if one.endswith("y") else f"{one}s"
    return f"{count} {one if count == 1 else many}"


def icon(name: str) -> str:
    return f'<svg class="ak-icon" viewBox="0 0 16 16" aria-hidden="true">{ICONS[name]}</svg>'


def badge(status: str, text: str = "") -> str:
    cls = f"ak-badge ak-badge--{status.lower()} tag"
    return f'<span class="{cls}">{icon(status)}{esc(text or status)}</span>'


def _font(family: str, weight: str, name: str) -> str:
    data = base64.b64encode((ASSETS / name).read_bytes()).decode()
    return (
        f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:normal;'
        f'font-display:block;src:url(data:font/woff2;base64,{data}) format("woff2");}}'
    )


def style() -> str:
    """The fonts, the tokens, the components and the local rules of the report page, then ours."""
    light = (ASSETS / "theme-light.css").read_text()
    system = "".join((ASSETS / name).read_text() + "\n" for name in ("tokens.css", "bundle.css"))
    return (
        _font("Geist", "100 900", "Geist-Variable.woff2")
        + _font("JetBrains Mono", "100 800", "JetBrainsMono-Variable.woff2")
        + system
        + (ASSETS / "report.css").read_text()
        + LOCAL.read_text()
        + f"@media (prefers-color-scheme:light){{html:not([data-theme])"
        f"{{{light}color-scheme:light}}}}"
        f"@media print{{:root,[data-theme]{{{light}color-scheme:light}}}}"
    )


def _switch(theme: str, label: str, pressed: bool) -> str:
    return (
        f'<button class="ak-seg__btn ui" type="button" data-ak-theme="{theme}" '
        f'aria-pressed="{str(pressed).lower()}">{icon(theme)}{label}</button>'
    )


def shell(title: str, subject: str, body: str) -> str:
    script = (ASSETS / "archkeel-theme.js").read_text()
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    policy = (
        "default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:; "
        f"script-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'"
    )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{policy}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n<script>{script}</script>\n<style>{style()}</style>\n"
        '</head>\n<body class="ak-root body">\n'
        '<header class="rp-top"><p class="h3 rp-word">ArchKeel<i>.</i></p>'
        f'<p class="body-sm rp-subject">{esc(subject)}</p>'
        '<div class="ak-seg" role="group" aria-label="Theme">'
        f"{_switch('light', 'Light', False)}{_switch('dark', 'Dark', True)}</div></header>\n"
        f'<main class="rp-main">\n{body}\n</main>\n</body></html>\n'
    )


def _link(part: Part, anchor: str, ids: frozenset[str]) -> str:
    """The report of the part, with an anchor only when the written report holds that id."""
    return f"{part.report}#{anchor}" if anchor in ids else part.report


def tile(part: Part, item: Tile, ids: frozenset[str]) -> str:
    cls = f" rp-tile--{item.state.lower()}" if item.state else ""
    cls += " rp-tile--count" if item.count else ""
    mark = f'{icon(item.state)}<span class="rp-vh">{item.state}</span>' if item.state else ""
    anchor = "arch"
    if item.state == "FAIL":
        anchor = "violations" if item.count else f"x{item.place}"
    href = esc(_link(part, anchor, ids))
    return f'<li><a class="rp-tile{cls}" href="{href}">{mark}{esc(item.label)}</a></li>'


def card(part: Part, ids: frozenset[str], commit: str) -> str:
    verdict_badge = badge(part.status) if part.decided else badge("UNKNOWN", "NO RESULT")
    head = (
        f'<div class="rp-part__head">{icon("part")}<h2 class="h3">{esc(part.title)}</h2>'
        f'<span class="ak-badge tag">{esc(part.language)}</span>{verdict_badge}</div>'
    )
    sub = f'<p class="caption rp-part__sub">{esc(part.subject)} &#183; commit {esc(commit[:9])}</p>'
    if not part.decided:
        reason = esc(part.refusal or part.error)
        note = f'<p class="body-sm">No result: {reason}</p>'
        return f'<article class="rp-part">{head}{sub}{note}</article>'
    tiles = "".join(tile(part, item, ids) for item in part.tiles)
    foot = (
        f"{plural(part.components, 'component')}, {plural(part.modules, 'module')} &#183; "
        f"{part.failing} FAIL &#183; {part.unknown} UNKNOWN &#183; "
        f'<a href="{esc(part.report)}">Open the report of this part</a>'
    )
    tiles = f'<ul class="rp-tiles">{tiles}</ul>' if tiles else ""
    return (
        f'<article class="rp-part">{head}{sub}{tiles}<p class="caption rp-part__foot">{foot}</p>'
        "</article>"
    )


def wall(binary: str) -> str:
    runs = "The shell runs the core as a binary"
    if binary:
        runs = f'The shell runs the binary <span class="rp-code">{esc(binary)}</span>'
    return (
        '<div class="rp-wall" role="group" aria-label="Process boundary"><div class="rp-wall__in">'
        '<span class="tag">PROCESS BOUNDARY</span>'
        '<span class="ui rp-wall__word">starts process</span>'
        f'{ARROW}<span class="caption">{runs}: request on stdin, frame on stdout</span>'
        '<span class="caption">Stated, not verified: no frame holds this relation and no frame '
        "checks it.</span></div></div>"
    )


def legend() -> str:
    items = [
        ('<span class="rp-tile">name</span>', "component"),
        (f'<span class="rp-tile rp-tile--fail">{icon("FAIL")}name</span>', "FAIL"),
        (f'<span class="rp-tile rp-tile--unknown">{icon("UNKNOWN")}name</span>', "UNKNOWN"),
    ]
    rows = "".join(f"<li>{sample}{esc(text)}</li>" for sample, text in items)
    return f'<ul class="rp-legend caption">{rows}</ul>'


def headline(part: Part) -> str:
    fail, unknown = part.counts["FAIL"], part.counts["UNKNOWN"]
    if part.status == "PASS":
        return f"All {plural(part.counts['PASS'], 'rule')} hold"
    if fail:
        where = f" in {plural(part.places_total, 'place')}" if part.places_total else ""
        return f"{plural(fail, 'rule')} violated{where}, {unknown} unknown"
    if unknown:
        return f"{plural(unknown, 'rule')} cannot be decided"
    return "The run cannot be decided"


def _exceptions(part: Part, ids: frozenset[str]) -> str:
    rows = ""
    for place in part.places[:LISTED_LIMIT]:
        href = esc(_link(part, f"x{place.number}", ids))
        rows += (
            f'<tr><td><a class="rp-no" href="{href}">{place.number}</a></td>'
            f'<td class="body-sm">{esc(place.text)} &#183; {plural(place.rules, "rule")}</td></tr>'
        )
    more = part.places_total - min(len(part.places), LISTED_LIMIT)
    if more > 0:
        href = esc(_link(part, "violations", ids))
        rows += (
            f'<tr><td></td><td class="body-sm"><a href="{href}">{plural(more, "more place")}</a> '
            "in the report</td></tr>"
        )
    unknown = part.counts["UNKNOWN"]
    if unknown:
        rows += (
            f'<tr><td>{icon("UNKNOWN")}</td><td class="body-sm">{plural(unknown, "rule")} UNKNOWN '
            f"from {plural(part.gaps, 'collection gap')}</td></tr>"
        )
    return f'<table class="rp-mini rp-sum"><tbody>{rows}</tbody></table>' if rows else ""


def verdict(part: Part, ids: frozenset[str]) -> str:
    if not part.decided:
        return f'<div><h3 class="h3">{esc(part.title)}</h3><p class="body-sm">No result.</p></div>'
    stats = "".join(
        f'<div class="ak-verdict__stat"><dt class="caption">{name}</dt>'
        f'<dd class="ak-num h2">{part.counts[name]}</dd></div>'
        for name in STATUSES
    )
    return (
        f'<div><h3 class="h3">{esc(part.title)}</h3>'
        f'<section class="ak-verdict ak-verdict--{part.status.lower()}" '
        f'aria-label="Verdict of {esc(part.title)}">{badge(part.status)}'
        f'<p class="h2 ak-verdict__title">{esc(headline(part))}</p>'
        f'<p class="body-sm ak-verdict__note">{NOTES[part.status]}</p>'
        f'<dl class="ak-verdict__stats">{stats}</dl></section>{_exceptions(part, ids)}</div>'
    )


def footer(parts: Sequence[Part], commit: str, built_at: str) -> str:
    rows = [("Commit", f'<span class="rp-code">{esc(commit)}</span> &#183; built {esc(built_at)}')]
    for part in parts:
        if part.engine:
            engine = f'<span class="rp-code">{esc(part.binary)} {esc(part.engine)}</span>'
            contract = f'<span class="rp-code">{esc(part.contract)}</span>'
            rows.append((f"{part.title} run", f"{engine} &#183; contract {contract}"))
    rows.append(
        (
            "Joined by",
            "this page. The frame has no field for a product of several parts, and no fact "
            "records a process start.",
        )
    )
    link = f'<a href="{SHOWCASE}">One run for each project of fixtures/</a>'
    rows.append(("Fixtures", link))
    body = "".join(f'<dt class="caption">{k}</dt><dd class="body-sm">{v}</dd>' for k, v in rows)
    return f'<footer class="rp-foot"><dl class="rp-kv">{body}</dl></footer>'


def product_page(
    parts: Sequence[Part], ids: dict[str, frozenset[str]], commit: str, built_at: str
) -> str:
    """The product page. `ids` holds, for each part, the ids of the report that the CLI wrote."""
    count = len(parts)
    heading = f"ArchKeel as a product: {count} parts, {count} runs, worst verdict {worst(parts)}"
    binary = next((part.binary for part in parts if part.binary), "")
    cards = wall(binary).join(card(part, ids[part.key], commit) for part in parts)
    verdicts = "".join(verdict(part, ids[part.key]) for part in parts)
    body = (
        '<section class="rp-sec" style="margin-top:0" aria-labelledby="product">'
        f'<h1 class="h2 rp-h1" id="product">{esc(heading)}</h1>'
        '<p class="body-sm rp-lede">Each part is one run with its own contract and its own '
        "verdict. The page puts the two runs side by side. No frame joins them, so the page "
        "gives no joint verdict.</p>"
        f'<div class="rp-parts">{cards}</div>{legend()}</section>'
        '<section class="rp-sec" aria-labelledby="verdicts">'
        '<h2 class="h2" id="verdicts">Verdict of each part</h2>'
        '<p class="body-sm rp-lede">The exceptions of each run. A number opens its evidence in '
        "the report of the part.</p>"
        f'<div class="rp-duo">{verdicts}</div></section>'
        f"{footer(parts, commit, built_at)}"
    )
    return shell("ArchKeel as a product", "Report · ArchKeel as a product", body)
