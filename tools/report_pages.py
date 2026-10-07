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
        f'<li><a href="{escape(row["id"])}/architecture.report.html?theme=dark">'
        f"{escape(row['id'])}</a> <strong>{escape(row['status'])}</strong>"
        f"<p>{escape(shorten(row['summary'], width=180, placeholder='…'))}</p></li>"
        for row in rows
    )
    html = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>ArchKeel demo reports</title>
<style>
:root {{color-scheme:dark;background:#101214;color:#eee;font:16px/1.5 system-ui}}
body {{max-width:70rem;margin:3rem auto;padding:0 1.5rem}}
a {{color:#66e3d0}} a:focus-visible {{outline:2px solid;outline-offset:4px}}
ul {{list-style:none;padding:0}} li {{padding:1rem 0;border-bottom:1px solid #444}}
strong {{margin-left:1rem}} p {{margin:.3rem 0;color:#bbb}}
</style>
<a href="../architecture.report.html?theme=dark">Current Main report</a>
<h1>Demo reports</h1>
<p>Generated from the same revision as the Main report. Deliberate violations and
incomplete evidence demonstrate FAIL and UNKNOWN alongside PASS.</p>
<ul>{items}</ul></html>
"""
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / "index.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build_demos(Path("test-artifacts/pages/demos"))
