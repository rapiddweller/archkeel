# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The page `showcase/index.html` of the gallery (AD-462): four sections of scenario cards.

Each card shows the intent of its scenario (the verdict it was built for) next to the verdict of
the run. A difference is stated with the issue that blocks it and is never hidden.
The page decides nothing: it copies the envelope facts of each row.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import Any

from tools.report_product import Part, system
from tools.report_product_page import shell

STATUSES = ("PASS", "FAIL", "UNKNOWN")


def _cell(text: object) -> str:
    return f"<td>{html.escape(str(text))}</td>"


def _verdict(row: Mapping[str, Any]) -> str:
    summary = row.get("summary")
    if summary is None:
        return f'<td colspan="5">no result: {html.escape(row["error"])}</td>'
    if summary["refusal"]:
        reason = summary["refusal"]["message"]
        cause = html.escape(f"refused: {reason}")
        return _cell(summary["status"]) + f'<td colspan="4">{cause}</td>'
    counts = summary["counts"]
    gaps = ", ".join(f"{kind}: {number}" for kind, number in summary["gaps"].items()) or "none"
    return (
        _cell(summary["status"]) + "".join(_cell(counts[name]) for name in STATUSES) + _cell(gaps)
    )


def _links(row: Mapping[str, Any]) -> str:
    # The table is one folder below the root of the site.
    anchors = [
        f'<a href="../{html.escape(path, quote=True)}">{label}</a>' for label, path in row["links"]
    ]
    return f"<td>{' '.join(anchors) or 'none'}</td>"


REPOSITORY = "https://github.com/rapiddweller/archkeel"
# The sections of the page, in order: the key of `section` in the matrix, its title and its lede.
SECTIONS = (
    (
        "real",
        "Real projects (PASS earned)",
        "A project that others wrote, checked by a contract. A PASS here is earned by the run. "
        "A card that is not a PASS says so and names what blocks it.",
    ),
    (
        "clean",
        "Clean scenarios (PASS on purpose)",
        "Small projects that follow their contract. Each one is built to show a PASS.",
    ),
    (
        "violation",
        "Violation scenarios (FAIL on purpose)",
        "A clean project with one planted change. Each one is built to show a FAIL and the "
        "import or edge that the contract catches.",
    ),
    (
        "unknown",
        "What UNKNOWN means",
        "ArchKeel names what it cannot decide. UNKNOWN is not a pass and not a failure of the "
        "tool: the card says which cause holds the rule.",
    ),
)
HEAD = "<th>Verdict</th><th>PASS</th><th>FAIL</th><th>UNKNOWN</th><th>Gaps</th><th>Reports</th>"


def _issue(number: int) -> str:
    return f'<a href="{REPOSITORY}/issues/{number}">#{number}</a>'


def intent_line(run: Mapping[str, Any], status: str | None) -> str:
    """The designed verdict next to the real one. A difference is stated, never hidden.

    `status` is the status of the run, or None when the run gave no result.
    """
    intent = run.get("intent")
    if intent not in STATUSES:
        return '<span class="ak-t-fail">no intent stated</span>'
    wanted = "UNKNOWN on purpose" if intent == "UNKNOWN" else f"expected {intent}"
    if status is None:
        return f'{wanted} \u00b7 <span class="ak-t-fail">no result</span>'
    if status == intent:
        return f'<span class="ak-t-{intent.lower()}">{wanted}</span> \u00b7 {status}'
    blockers = ", ".join(_issue(number) for number in run.get("blocked_by", []))
    cause = f"blocked by {blockers}" if blockers else "scenario not met"
    mark = "ak-t-unknown" if blockers else "ak-t-fail"
    return f'{html.escape(wanted)} \u00b7 <span class="{mark}">{status} today \u00b7 {cause}</span>'


def _status_of(row: Mapping[str, Any]) -> str | None:
    summary = row.get("summary")
    return None if summary is None else str(summary["status"])


def _scenario(row: Mapping[str, Any]) -> str:
    run = row["run"]
    about = html.escape(str(run.get("about", "")))
    line = intent_line(run, _status_of(row))
    return f'<td class="body-sm">{about}<br><span class="caption">{line}</span></td>'


def _section(key: str, title: str, lede: str, body: str, count: int) -> str:
    return (
        f'<section class="rp-sec" aria-labelledby="sec-{key}">'
        f'<h2 class="h3" id="sec-{key}">{html.escape(title)}</h2>\n'
        f'<p class="body-sm rp-lede">{html.escape(lede)}</p>\n'
        f'<p class="caption">{count} {"run" if count == 1 else "runs"}</p>\n'
        '<table class="rp-mini"><thead><tr><th>Scenario</th><th>Intent</th>'
        f"{HEAD}</tr></thead>\n<tbody>\n{body}</tbody></table></section>\n"
    )


def _anchor(parts: Sequence[Part]) -> str:
    """The row of the self-check of ArchKeel: its system verdict, linked to the system page."""
    link = '<td><a href="../self/index.html">System</a></td>'
    name = "<td>ArchKeel self-check</td>"
    about = (
        '<td class="body-sm">ArchKeel checks its own Rust core and Python shell.<br>'
        '<span class="caption">{line}</span></td>'
    )
    if not parts or any(not part.decided for part in parts):
        line = intent_line({"intent": "PASS"}, None)
        return f'<tr>{name}{about.format(line=line)}<td colspan="5">no result</td>{link}</tr>\n'
    verdict = system(parts)
    line = intent_line({"intent": "PASS"}, verdict.status)
    cells = "".join(_cell(verdict.counts[status]) for status in STATUSES)
    return (
        f"<tr>{name}{about.format(line=line)}{_cell(verdict.status)}{cells}"
        f"{_cell('none')}{link}</tr>\n"
    )


def index(
    rows: Sequence[Mapping[str, Any]],
    sha: str,
    built_at: str,
    parts: Sequence[Part] | None = None,
) -> str:
    """The showcase page: four sections, each card with its intent next to its verdict.

    The anchor row of the self-check leads the real projects when `parts` is given.
    """
    groups = ""
    for key, title, lede in SECTIONS:
        chosen = [row for row in rows if row["run"].get("section", "unknown") == key]
        lead = _anchor(parts) if key == "real" and parts is not None else ""
        if not chosen and not lead:
            continue
        body = lead + "".join(
            f"<tr>{_cell(row['run']['name'])}{_scenario(row)}{_verdict(row)}{_links(row)}</tr>\n"
            for row in chosen
        )
        groups += _section(key, title, lede, body, len(chosen) + (1 if lead else 0))
    body = (
        '<h1 class="h2">ArchKeel fixture reports</h1>\n'
        '<p class="body-sm"><a href="../index.html">ArchKeel as a product</a></p>\n'
        f'<p class="body-sm">Commit <code>{html.escape(sha)}</code>. '
        f"Built {html.escape(built_at)}.</p>\n"
        '<p class="body-sm">Each row is one run of the core on a project of '
        "<code>fixtures/</code>, with the verdict that the scenario was built for. "
        "Where the run gives another verdict, the row says so and names the blocker. "
        "A refused row shows the exact reason of the core. UNKNOWN is not a pass.</p>\n"
        f"{groups}"
    )
    return shell("ArchKeel fixture reports", "Report \u00b7 fixture reports", body)
