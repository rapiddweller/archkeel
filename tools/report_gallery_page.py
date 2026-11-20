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


def _collection(row: Mapping[str, Any]) -> str:
    frame = row.get("frame") or {}
    gaps = frame.get("collection_gaps")
    return str(len(gaps)) if isinstance(gaps, list) else "unavailable"


def _verdict(row: Mapping[str, Any]) -> str:
    summary = row.get("summary")
    if summary is None:
        return f'<td colspan="7">no result: {html.escape(row["error"])}</td>'
    if summary["refusal"]:
        reason = summary["refusal"]["message"]
        cause = html.escape(f"refused: {reason}")
        return _cell(summary["status"]) + f'<td colspan="6">{cause}</td>'
    counts = summary["counts"]
    measures = (row.get("frame") or {}).get("measures") or {}
    calls = (
        f"{measures['calls_unresolved']:,} / {measures['calls_total']:,}"
        if "calls_total" in measures and "calls_unresolved" in measures
        else "unavailable"
    )
    gaps = ", ".join(f"{kind}: {number}" for kind, number in summary["gaps"].items()) or "none"
    return (
        _cell(summary["status"])
        + "".join(_cell(counts[name]) for name in STATUSES)
        + _cell(gaps)
        + _cell(_collection(row))
        + _cell(calls)
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
HEAD = (
    "<th>Verdict</th><th>PASS</th><th>FAIL</th><th>Unknown rules</th>"
    "<th>Report findings</th><th>Collection gaps</th>"
    "<th>Core calls: unresolved / scanned</th><th>Reports</th>"
)


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
    # An item is an issue number, or a list of numbers that one piece of work closes together.
    blockers = ", ".join(
        "/".join(_issue(number) for number in item) if isinstance(item, list) else _issue(item)
        for item in run.get("blocked_by", [])
    )
    cause = f"blocked by {blockers}" if blockers else "scenario not met"
    if blockers and run.get("held_by"):
        # A named work item that holds the verdict, with its status (an honest UNKNOWN).
        cause = (
            f"held by {html.escape(run['held_by'])} ({blockers}); {html.escape(run['status_note'])}"
        )
    mark = "ak-t-unknown" if blockers else "ak-t-fail"
    return f'{html.escape(wanted)} \u00b7 <span class="{mark}">{status} today \u00b7 {cause}</span>'


def _status_of(row: Mapping[str, Any]) -> str | None:
    summary = row.get("summary")
    return None if summary is None else str(summary["status"])


def _planted(row: Mapping[str, Any]) -> str:
    """The planted change of a violation scenario and the block of the report that shows it.

    The link leads to the violation block of the report (`report.html#x1`). When the report holds
    no such block, the card says so and gives no link.
    """
    plant = row["run"].get("plant")
    if not plant:
        return ""
    where, line = (html.escape(str(plant[key])) for key in ("where", "line"))
    text = f'<br><span class="caption">Planted in <code>{where}</code>: <code>{line}</code>.'
    if "rule" not in plant:
        # A plant that makes a rule UNKNOWN has no violation block to link.
        return text + "</span>"
    rule = html.escape(str(plant["rule"]))
    text += " "
    block = row.get("violation")
    report = dict(row["links"]).get("HTML")
    if not block or not report:
        return (
            text
            + f'<span class="ak-t-fail">No violation block of {rule} in the report.</span></span>'
        )
    target = html.escape(f"../{report}#{block['id']}", quote=True)
    title = html.escape(block["title"])
    return text + f'Caught by <code>{rule}</code>: <a href="{target}">{title}</a></span>'


def _source(row: Mapping[str, Any]) -> str:
    """The pin of a real project: name, release, licence and commit. Only our contract is ours."""
    pin = row.get("source")
    if not pin:
        return ""
    release = f" {html.escape(pin['ref'])}" if pin["ref"] else ""
    repo = html.escape(pin["repo"], quote=True)
    name = f'<a href="{repo}">{html.escape(pin["name"])}</a>'
    return (
        f'<br><span class="caption">Source: {name}{release} ({html.escape(pin["license"])}), '
        f"pinned commit <code>{html.escape(pin['commit'][:12])}</code>, fetched when the page is "
        "built. The contract is ours.</span>"
    )


def _assuming(row: Mapping[str, Any]) -> str:
    """The premise of a PASS that holds only under a premise of the contract. A premise is not a
    proof, so the card states it next to the verdict."""
    premise = row.get("assuming")
    if not premise or _status_of(row) != "PASS":
        return ""
    return f'<br><span class="caption">PASS assuming {html.escape(str(premise))}.</span>'


def _scenario(row: Mapping[str, Any]) -> str:
    run = row["run"]
    about = html.escape(str(run.get("about", "")))
    line = intent_line(run, _status_of(row))
    extra = _planted(row) + _assuming(row) + _source(row)
    return f'<td class="body-sm">{about}<br><span class="caption">{line}</span>{extra}</td>'


def _section(key: str, title: str, lede: str, body: str, count: int) -> str:
    return (
        f'<section class="rp-sec" aria-labelledby="sec-{key}">'
        f'<h2 class="h3" id="sec-{key}">{html.escape(title)}</h2>\n'
        f'<p class="body-sm rp-lede">{html.escape(lede)}</p>\n'
        f'<p class="caption">{count} {"run" if count == 1 else "runs"}</p>\n'
        '<table class="rp-mini"><thead><tr><th>Scenario</th><th>Intent</th>'
        f"{HEAD}</tr></thead>\n<tbody>\n{body}</tbody></table></section>\n"
    )


# The self-check is expected to PASS. Today the Rust collector holds it with sound gaps: a field
# receiver of unproved type (#1571), and a trait dispatch that can reach many impls (#1515/#1516).
# The precision work is open.
ANCHOR = {
    "intent": "PASS",
    "blocked_by": [1571, [1515, 1516]],
    "held_by": "sound gaps of the Rust collector",
    "status_note": "the precision work is in progress",
}


def _anchor(parts: Sequence[Part]) -> str:
    """The row of the self-check of ArchKeel: its system verdict, linked to the system page."""
    link = '<td><a href="../self/index.html">System</a></td>'
    name = "<td>ArchKeel self-check</td>"
    about = (
        '<td class="body-sm">ArchKeel checks its own Rust core and Python shell.<br>'
        '<span class="caption">{line}</span></td>'
    )
    if not parts or any(not part.decided for part in parts):
        line = intent_line(ANCHOR, None)
        return f'<tr>{name}{about.format(line=line)}<td colspan="7">no result</td>{link}</tr>\n'
    verdict = system(parts)
    line = intent_line(ANCHOR, verdict.status)
    cells = "".join(_cell(verdict.counts[status]) for status in STATUSES)
    return (
        f"<tr>{name}{about.format(line=line)}{_cell(verdict.status)}{cells}"
        f"{_cell('See system report')}{_cell(_part_gaps(parts))}"
        f"{_cell('See part reports')}{link}</tr>\n"
    )


def _part_gaps(parts: Sequence[Part]) -> str:
    """The collection gaps of all parts: the total and the count of each part that has some."""
    total = sum(part.gaps for part in parts)
    if not total:
        return "none"
    each = ", ".join(f"{part.title} {part.gaps}" for part in parts if part.gaps)
    return f"{total} collection {'gap' if total == 1 else 'gaps'} ({each})"


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
        '<p class="body-sm"><a href="../index.html">ArchKeel as a product</a> · '
        '<a href="../capabilities.html">Rule capability statistics</a></p>\n'
        f'<p class="body-sm">Commit <code>{html.escape(sha)}</code>. '
        f"Built {html.escape(built_at)}.</p>\n"
        '<p class="body-sm">Each row is one run of the core on a project of '
        "<code>fixtures/</code>, with the verdict that the scenario was built for. "
        "Where the run gives another verdict, the row says so and names the blocker. "
        "A refused row shows the exact reason of the core. UNKNOWN is not a pass.</p>\n"
        f"{groups}"
    )
    return shell("ArchKeel fixture reports", "Report \u00b7 fixture reports", body)
