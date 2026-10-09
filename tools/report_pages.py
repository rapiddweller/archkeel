# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Publish the browser-accepted demo reports beside the current Main report."""

from __future__ import annotations

import contextlib
import io
import json
import re
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import shorten

from archkeel.cli import main as archkeel_main
from fixtures.architecture_demo import CATALOG, PROJECT_REPORT_GROUPS, REPORT_CASES, replay
from fixtures.demo_catalog_typescript import VARIANTS
from fixtures.reproduce_typescript import repository


def build_demos(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    variants = {variant.id: variant for variant in CATALOG}
    rows: list[dict[str, object]] = []
    project_case_ids = {
        case_id
        for group in PROJECT_REPORT_GROUPS
        for case_id in (group["baseline"], *group["variants"])
    }
    cases = {**REPORT_CASES, "dart-clean": ("dart-clean", 0), "dart-tour": ("dart-tour", 2)}
    for name, (variant_id, expected_exit) in cases.items():
        artifact = output / name / "architecture.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            actual = replay(variant_id, artifact)
        if actual != expected_exit:
            raise ValueError(f"{variant_id}: expected exit {expected_exit}, got {actual}")
        results = [
            json.loads(line)
            for line in stdout.getvalue().splitlines()
            if line.startswith("{") and line.endswith("}")
        ]
        report = next(item for item in results if item["command"] == "report")
        rows.append(
            _entry(
                name,
                variants[variant_id].summary,
                report,
                artifact,
                requires_uml=name in project_case_ids,
            )
        )

    variant = next(item for item in VARIANTS if item.id == "typescript-clean")
    artifact = (output / variant.id / "architecture.json").resolve()
    with TemporaryDirectory(prefix="archkeel-pages-") as temporary:
        root = repository(Path(temporary), variant)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            actual = archkeel_main(
                ["report", "--root", str(root), "--output", str(artifact), "--json"]
            )
        result = json.loads(stdout.getvalue().splitlines()[-1])
        if actual != 0 or result["declared_rules"] != variant.expected_declared_rules:
            raise ValueError(f"{variant.id}: unexpected report result")
    rows.append(_entry(variant.id, variant.summary, result, artifact, requires_uml=False))
    _write_index(output, rows)


def _entry(
    name: str,
    summary: str,
    report_summary: dict[str, object],
    artifact: Path,
    *,
    requires_uml: bool,
) -> dict[str, object]:
    report_html = artifact.with_suffix(".report.html")
    detail_html = artifact.with_suffix(".detail.html")
    if not report_html.is_file() or not detail_html.is_file():
        raise ValueError(f"{name}: missing report or detail HTML")
    match = re.search(
        r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>',
        detail_html.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"{name}: detail HTML has no report payload")
    detail = json.loads(match.group(1))
    comparison = detail.get("comparison")
    if comparison is None and requires_uml:
        raise ValueError(f"{name}: detail HTML has no UML comparison status")
    if comparison is not None and (
        not isinstance(comparison, dict)
        or comparison.get("status") not in {"PASS", "FAIL", "UNKNOWN"}
    ):
        raise ValueError(f"{name}: detail HTML has an invalid UML comparison status")
    coverage = report_summary["coverage"]
    if not isinstance(coverage, dict):
        raise ValueError(f"{name}: report summary has no coverage facts")
    return {
        "id": name,
        "case_id": name,
        "summary": summary,
        "observation_complete": report_summary["observation_complete"],
        "coverage": coverage,
        "declared_rules": report_summary["declared_rules"],
        "rule_assessments": report_summary["rule_assessments"] or [],
        "uml_comparison": comparison["status"] if isinstance(comparison, dict) else None,
        "report_href": f"demos/{name}/architecture.report.html?theme=dark",
        "detail_href": f"demos/{name}/architecture.detail.html?theme=dark",
    }


def _write_index(output: Path, rows: list[dict[str, object]]) -> None:
    by_id = {str(row["id"]): row for row in rows}
    project_case_ids = {
        case_id
        for group in PROJECT_REPORT_GROUPS
        for case_id in (group["baseline"], *group["variants"])
    }
    projects = [
        {
            **{
                key: group[key]
                for key in (
                    "id",
                    "title",
                    "repository",
                    "commit",
                    "scope",
                    "feature",
                    "target_depth",
                    "evidence_limits",
                )
            },
            "baseline": by_id[group["baseline"]],
            "variants": [by_id[case_id] for case_id in group["variants"]],
        }
        for group in PROJECT_REPORT_GROUPS
    ]
    controls = [
        {
            **row,
            "kind": "runnable_control" if row["id"] == "uml-flutter-shop" else "rule_fixture",
            "label": (
                "I-flutter-shop · smaller runnable control"
                if row["id"] == "uml-flutter-shop"
                else str(row["id"])
            ),
        }
        for row in rows
        if row["id"] not in project_case_ids
    ]
    index = {"projects": projects, "controls": controls}

    def _entry_card(row: dict[str, object], label: str | None = None) -> str:
        coverage = row["coverage"]
        assert isinstance(coverage, dict)
        failures = coverage.get("failures", [])
        failure_text = ""
        if failures:
            first = failures[0]
            if isinstance(first, dict):
                title = escape(str(first.get("title", "incomplete evidence")))
                failure_text = f'<p class="coverage-reason">Coverage: {title}.</p>'
        facets = (
            ("Observation", row["observation_complete"]),
            ("Coverage", coverage["status"]),
            ("Rules", row["declared_rules"]),
            ("UML", row["uml_comparison"] or "N/A"),
        )
        badges = "".join(
            f'<span class="facet" data-status="{escape(str(status))}">'
            f"{escape(title)}: {escape(str(status))}</span>"
            for title, status in facets
        )
        assessments = "".join(
            f'<li><span data-status="{escape(str(item["status"]))}">'
            f"{escape(str(item['status']))}</span> "
            f"{escape(str(item['id']))} ({escape(str(item['count']))})</li>"
            for item in row["rule_assessments"]
            if isinstance(item, dict)
        )
        rule_failures = [
            item
            for item in row["rule_assessments"]
            if isinstance(item, dict) and item.get("status") == "FAIL"
        ]
        known_failure = ""
        if rule_failures:
            item = rule_failures[0]
            known_failure = (
                '<p class="known-failure">Known rule failure: '
                f"{escape(str(item['id']))} ({escape(str(item['count']))})</p>"
            )
        title = label or str(row["id"])
        return (
            '<article class="demo">'
            f'<h3><a href="{escape(str(row["report_href"]))}">{escape(title)}</a></h3>'
            f"<p>{escape(shorten(str(row['summary']), width=180, placeholder='…'))}</p>"
            f'<p class="facets">{badges}</p>{known_failure}{failure_text}'
            "<details><summary>Per-rule assessments</summary>"
            f"<ul>{assessments}</ul></details>"
            f'<p><a href="{escape(str(row["detail_href"]))}">Open UML detail →</a></p>'
            "</article>"
        )

    project_html = "\n".join(
        '<section class="project" data-project-id="{}">'
        '<h2>{}</h2><p class="source">{}@{} · {}</p>'
        "<p>{}</p><p><strong>Target:</strong> {}</p>"
        "<p><strong>Evidence limits:</strong> {}</p>"
        '<h3>Baseline</h3><div class="grid">{}</div>'
        '<h3>Source-only variants</h3><div class="grid">{}</div></section>'.format(
            escape(str(group["id"])),
            escape(str(group["title"])),
            escape(str(group["repository"])),
            escape(str(group["commit"])),
            escape(str(group["scope"])),
            escape(str(group["feature"])),
            escape(str(group["target_depth"])),
            escape(str(group["evidence_limits"])),
            _entry_card(group["baseline"]),
            "".join(_entry_card(row) for row in group["variants"]),
        )
        for group in projects
    )
    controls_html = "\n".join(_entry_card(row, str(row["label"])) for row in controls)
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="description" content="Explore ArchKeel's current architecture and demo reports.">
<title>ArchKeel · Architecture reports</title>
<style>
:root {{color-scheme:dark;background:#101214;color:#eee;font:16px/1.55 system-ui}}
* {{box-sizing:border-box}} body {{max-width:74rem;margin:auto;padding:1.5rem}}
a {{color:#66e3d0}} a:focus-visible {{outline:3px solid #c5ef44;outline-offset:5px}}
header,footer {{display:flex;justify-content:space-between;gap:1rem;padding:1rem 0}}
.brand {{font-weight:800;letter-spacing:.12em;color:#66e3d0}}
.hero {{padding:3rem 0 2rem;max-width:52rem}}
h1 {{font-size:clamp(2.4rem,6vw,4.4rem);line-height:1.08;
letter-spacing:-.04em;margin:.5rem 0 1.5rem}}
h2 {{font-size:1.6rem;margin:0 0 .5rem}}
h3 {{font-size:1.1rem;margin:.6rem 0;overflow-wrap:anywhere}}
p {{color:#bcc3c7;margin:.4rem 0}} .hero p {{font-size:1.15rem}}
.current {{display:block;border:1px solid #66e3d0;border-radius:16px;padding:2rem;
background:#142522;text-decoration:none;color:#eee}}
.current span {{display:block;color:#66e3d0;font-weight:700;margin-top:1.2rem}}
section {{margin:3rem 0}} .project {{border-top:1px solid #343b3f;padding-top:1.5rem}}
.source {{font: .9rem ui-monospace,monospace;overflow-wrap:anywhere}}
.grid {{display:grid;
grid-template-columns:repeat(auto-fit,minmax(min(100%,20rem),1fr));
gap:1rem;list-style:none;padding:0;margin-top:1.5rem}}
.demo {{height:100%;padding:1.3rem;border:1px solid #343b3f;border-radius:12px;
background:#181c1f;color:#eee}} .demo:hover {{border-color:#66e3d0}}
.demo p {{font-size:.95rem}} .facets {{display:flex;flex-wrap:wrap;gap:.4rem}}
.facet, details {{font:700 .72rem ui-monospace,monospace}}
.facet {{border:1px solid #343b3f;border-radius:999px;padding:.2rem .45rem}}
.known-failure {{color:#ff8589;font-weight:700}}
.coverage-reason {{font-size:.85rem!important}} details {{margin:.7rem 0}}
details ul {{padding-left:1.2rem;font-weight:400;overflow-wrap:anywhere}}
[data-status=PASS] {{color:#66e3d0}} [data-status=FAIL] {{color:#ff8589}}
[data-status=UNKNOWN] {{color:#f2cc70}}
footer {{border-top:1px solid #343b3f;color:#bcc3c7;font-size:.9rem}}
</style></head><body>
<header><span class="brand">ARCHKEEL</span>
<a href="https://github.com/rapiddweller/archkeel">GitHub ↗</a></header>
<main><div class="hero"><h1>See the architecture.<br>Check the evidence.</h1>
<p>ArchKeel compares observed code with declared architecture. Explore dependencies,
findings and explicit gaps in what can be proven.</p></div>
<a class="current" href="architecture.report.html?theme=dark">
<h2>ArchKeel’s current architecture</h2><p>The latest report from Main. Navigate observed code,
declared intent and their differences — down to the source evidence.</p>
<span>Open current report →</span></a>
<section aria-labelledby="projects"><h2 id="projects">Explore full-project journeys</h2>
<p>Each journey links one pinned source project, its independently authored Target and three
source-only changes. Observation, coverage, declared rules and UML comparison remain separate.</p>
{project_html}</section>
<section aria-labelledby="controls"><h2 id="controls">Rule fixtures and smaller control</h2>
<p>These focused examples show individual rules and interactions. I-flutter-shop is a smaller
runnable control, not a full-project demo.</p>
<div class="grid">{controls_html}</div></section></main>
<footer><span>Generated alongside the current Main report.</span>
<a href="https://github.com/rapiddweller/archkeel#start-here">Get started with ArchKeel ↗</a>
</footer>
</body></html>
"""
    (output.parent / "index.html").write_text(html, encoding="utf-8")
    (output / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>ArchKeel demos</title>'
        '<meta http-equiv="refresh" content="0; url=../#projects">'
        '<a href="../#projects">Explore full-project journeys</a></html>',
        encoding="utf-8",
    )
    (output / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build_demos(Path("test-artifacts/pages/demos"))
