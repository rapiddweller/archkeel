# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Publish the browser-accepted demo reports beside the current Main report."""

from __future__ import annotations

import contextlib
import io
import json
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import shorten

from archkeel.cli import main as archkeel_main
from fixtures.architecture_demo import CATALOG, REPORT_CASES, replay
from fixtures.demo_catalog_typescript import VARIANTS
from fixtures.reproduce_typescript import repository


def build_demos(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    variants = {variant.id: variant for variant in CATALOG}
    rows: list[dict[str, str]] = []
    cases = {**REPORT_CASES, "dart-clean": ("dart-clean", 0), "dart-tour": ("dart-tour", 2)}
    for name, (variant_id, expected_exit) in cases.items():
        artifact = output / name / "architecture.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            actual = replay(variant_id, artifact)
        if actual != expected_exit:
            raise ValueError(f"{variant_id}: expected exit {expected_exit}, got {actual}")
        result = json.loads(stdout.getvalue().splitlines()[-1])
        rows.append(_entry(name, variants[variant_id].summary, result["declared_rules"], artifact))

    variant = next(item for item in VARIANTS if item.id == "typescript-clean")
    artifact = (output / variant.id / "architecture.json").resolve()
    with TemporaryDirectory(prefix="archkeel-pages-") as temporary:
        root = repository(Path(temporary), variant)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            actual = archkeel_main(
                ["report", "--root", str(root), "--output", str(artifact), "--json"]
            )
        result = json.loads(stdout.getvalue())
        if actual != 0 or result["declared_rules"] != variant.expected_declared_rules:
            raise ValueError(f"{variant.id}: unexpected report result")
    rows.append(_entry(variant.id, variant.summary, result["declared_rules"], artifact))
    _write_index(output, rows)


def _entry(name: str, summary: str, status: str, artifact: Path) -> dict[str, str]:
    for suffix in (".report.html", ".detail.html"):
        if not artifact.with_suffix(suffix).is_file():
            raise ValueError(f"{name}: missing {suffix}")
    return {"id": name, "summary": summary, "status": status}


def _write_index(output: Path, rows: list[dict[str, str]]) -> None:
    items = "\n".join(
        f'<li><a class="demo" href="demos/{escape(row["id"])}/architecture.report.html?theme=dark">'
        f'<span class="status" data-status="{escape(row["status"])}">{escape(row["status"])}</span>'
        f"<h3>{escape(row['id'])}</h3>"
        f"<p>{escape(shorten(row['summary'], width=180, placeholder='…'))}</p></a></li>"
        for row in rows
    )
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
section {{margin:3rem 0}} .grid {{display:grid;
grid-template-columns:repeat(auto-fit,minmax(min(100%,20rem),1fr));
gap:1rem;list-style:none;padding:0;margin-top:1.5rem}}
.demo {{display:block;height:100%;padding:1.3rem;border:1px solid #343b3f;border-radius:12px;
background:#181c1f;color:#eee;text-decoration:none}} .demo:hover {{border-color:#66e3d0}}
.demo p {{font-size:.95rem}} .status {{font:700 .75rem ui-monospace,monospace;letter-spacing:.06em}}
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
<section aria-labelledby="demos"><h2 id="demos">Explore the demos</h2>
<p>Python, Dart and TypeScript examples. PASS shows established results; FAIL shows violations;
UNKNOWN keeps missing evidence visible. Deliberate failures are part of these examples.</p>
<ul class="grid">{items}</ul></section></main>
<footer><span>Generated alongside the current Main report.</span>
<a href="https://github.com/rapiddweller/archkeel#start-here">Get started with ArchKeel ↗</a>
</footer>
</body></html>
"""
    (output.parent / "index.html").write_text(html, encoding="utf-8")
    (output / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>ArchKeel demos</title>'
        '<meta http-equiv="refresh" content="0; url=../#demos">'
        '<a href="../#demos">Explore the demos</a></html>',
        encoding="utf-8",
    )
    (output / "index.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build_demos(Path("test-artifacts/pages/demos"))
