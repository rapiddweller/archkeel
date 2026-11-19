# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Show the rule results of the gallery runs without inferring checked item counts."""

from __future__ import annotations

import html
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from tools.report_product_page import shell


def _violation(frame: Mapping[str, Any], rule: str) -> str:
    count = frame.get("violations", {}).get(rule)
    parts = [] if count is None else [f"{count} violation{'s' if count != 1 else ''}"]
    for finding in frame.get("details", {}).get(rule, [])[:1]:
        cause = finding["cause"]
        locations = frame.get("locations", {})
        site = next(
            (locations[key] for key in finding.get("evidence", []) if key in locations), None
        )
        parts.append(f"{cause} ({site['path']}:{site['line']})" if site else cause)
    return ". ".join(parts)


def page(own: Sequence[Mapping[str, Any]], demos: Sequence[Mapping[str, Any]]) -> str:
    """Count rule results by kind and list their run, scope and verdict."""
    kinds: dict[str, dict[str, Counter[str]]] = {
        "ArchKeel self": defaultdict(Counter),
        "Regular demos": defaultdict(Counter),
        "Intentional counterexamples": defaultdict(Counter),
    }
    missing_counts: Counter[str] = Counter()
    details = []
    missing = []
    groups = [("ArchKeel self", row) for row in own] + [
        (
            "Intentional counterexamples"
            if row["run"].get("plant") or row["run"].get("counterexample")
            else "Regular demos",
            row,
        )
        for row in demos
    ]
    for group, row in groups:
        name = html.escape(row["run"]["name"])
        summary = row.get("summary")
        if not summary or summary["refusal"]:
            reason = row.get("error") or (summary or {}).get("refusal", {}).get(
                "message", "no result"
            )
            missing.append(f"<li>{name}: {html.escape(str(reason))}</li>")
            missing_counts[group] += 1
            continue
        link = dict(row["links"]).get("HTML")
        run = f'<a href="{html.escape(link, quote=True)}">{name}</a>' if link else name
        frame = row.get("frame", {})
        rules = frame.get("rules", {})
        declared = frame.get("self_test", {}).get("contract", {}).get("rules", {})
        unsupported = frame.get("unsupported", {}).get("rules", {})
        for rule in sorted(rules.keys() | declared.keys()):
            kind, verdict = rules.get(rule, (declared.get(rule, "unknown"), "NO ROW"))
            kinds[group][kind][verdict] += 1
            shape = frame.get("explain", {}).get("rules", {}).get(rule, {})
            source = ", ".join(shape.get("source", []))
            target = ", ".join(shape.get("target", []))
            scope = f"{source} → {target}" if source or target else "not stated"
            cause = frame.get("unknown_kinds", {}).get(rule, "")
            explanation = frame.get("explained", {}).get(rule, "")
            if explanation:
                cause = f"{cause}: {explanation}" if cause else explanation
            if verdict == "NO ROW":
                cause = unsupported.get(rule, "") if isinstance(unsupported, dict) else unsupported
            elif verdict == "FAIL":
                cause = _violation(frame, rule) or cause
            premises = ", ".join(
                f"{item['kind']} ({item['subject']})"
                for item in frame.get("premises", {}).get(rule, [])
            )
            cells = [group, rule, kind, scope, verdict, cause, premises]
            details.append(
                "<tr><td>"
                + run
                + "</td>"
                + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in cells)
                + "</tr>"
            )
    counts = "".join(
        f"<tr><td>{group}</td><td>{html.escape(kind)}</td>"
        + "".join(
            f"<td>{counts[status]}</td>"
            for status in ("PASS", "FAIL", "UNKNOWN", "DECLARATION", "NO ROW")
        )
        + "</tr>"
        for group, grouped in kinds.items()
        for kind, counts in sorted(grouped.items())
    )
    statuses = ("PASS", "FAIL", "UNKNOWN", "DECLARATION", "NO ROW")
    totals = "".join(
        f"<tr><td>{group}</td>"
        + "".join(
            f"<td>{sum(counts[status] for counts in grouped.values())}</td>" for status in statuses
        )
        + f"<td>{missing_counts[group]}</td></tr>"
        for group, grouped in kinds.items()
    )
    no_rows = sum(counts["NO ROW"] for grouped in kinds.values() for counts in grouped.values())
    total = len(details) - no_rows
    body = (
        '<h1 class="h2">Rule capability statistics</h1>'
        '<p class="body-sm"><a href="showcase/index.html">Fixture reports</a> · '
        '<a href="self/index.html">Self report</a></p>'
        f'<p class="body-sm">{total} rule results and {no_rows} declared rules without a row '
        "from the system self-check, Report Explorer and showcase demos. "
        "Each count represents one rule in one run. "
        "PASS and FAIL are decisions. UNKNOWN marks an open question. "
        "DECLARATION records a permission. NO ROW marks a missing decision."
        "</p>"
        '<h2 class="h3">Totals by group</h2><table class="rp-mini"><thead><tr>'
        "<th>Group</th><th>PASS</th><th>FAIL</th><th>UNKNOWN</th><th>DECLARATION</th>"
        "<th>NO ROW</th><th>Runs without a result</th></tr></thead><tbody>"
        + totals
        + "</tbody></table>"
        '<h2 class="h3">Results by rule kind</h2>'
        '<table class="rp-mini"><thead><tr><th>Group</th><th>Rule kind</th>'
        "<th>PASS</th><th>FAIL</th>"
        "<th>UNKNOWN</th><th>DECLARATION</th><th>NO ROW</th></tr></thead><tbody>"
        + counts
        + "</tbody></table>"
        '<h2 class="h3">Rule results</h2><table class="rp-mini"><thead><tr><th>Run</th>'
        "<th>Group</th><th>Rule</th><th>Kind</th><th>Scope</th><th>Verdict</th>"
        "<th>Explanation</th><th>Premises</th>"
        "</tr></thead><tbody>"
        + "".join(details)
        + "</tbody></table>"
        + (
            '<h2 class="h3">Runs without a result</h2><ul>' + "".join(missing) + "</ul>"
            if missing
            else ""
        )
    )
    return shell("Rule capability statistics", "Report · capabilities", body)
