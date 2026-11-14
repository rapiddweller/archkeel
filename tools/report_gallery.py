# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build the static fixture gallery: one report pair for each run of the matrix (AD-458).

The runs come from `fixtures/matrix.json`.
The tool decides nothing. It runs `archkeel report --output` for each run, reads the envelope that
the CLI prints, and shows the verdict, the counts and the refusal of the core as they are.
A run that gives no envelope gets a row without links and makes the exit code 1.

Run: `python -m tools.report_gallery --out DIR [--archkeel "uv run --locked archkeel"]`.
"""

from __future__ import annotations

import argparse
import html
import json
import shlex
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "fixtures" / "matrix.json"
STATUSES = ("PASS", "FAIL", "UNKNOWN")
RUN_TIMEOUT = 900


def load_runs(matrix: Path = MATRIX) -> list[dict[str, Any]]:
    """The runs of the matrix in table order, each with the key of its fixture."""
    table = json.loads(matrix.read_text())["fixtures"]
    return [
        {**run, "fixture": name, "language": entry["language"]}
        for name, entry in sorted(table.items())
        for run in entry["runs"]
    ]


def summarize(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """The facts of one CLI envelope that the matrix pins and the index shows."""
    frame = envelope.get("frame") or {}
    counts = dict.fromkeys(STATUSES, 0)
    for entry in frame.get("rules", {}).values():
        counts[entry[1]] += 1
    gaps = Counter(gap["kind"] for gap in envelope.get("gaps", []))
    return {
        "exit": envelope["exit_code"],
        "status": envelope["status"],
        "counts": counts,
        "scope": frame.get("scope"),
        "gaps": dict(sorted(gaps.items())),
        "refusal": envelope.get("refusal"),
    }


def command(cli: Sequence[str], run: Mapping[str, Any], target: Path, form: str) -> list[str]:
    arguments = [*cli, run["command"], "--root", f"fixtures/{run['root']}"]
    if run.get("config"):
        arguments += ["--config", run["config"]]
    return [*arguments, "--output", str(target), "--format", form]


def build_run(cli: Sequence[str], run: Mapping[str, Any], out: Path) -> dict[str, Any]:
    """Write both reports of one run. Return its row: a summary or an error text."""
    folder = out / run["name"]
    folder.mkdir(parents=True)
    row: dict[str, Any] = {"run": run, "links": []}
    try:
        done = subprocess.run(
            [*command(cli, run, folder / "report.json", "json"), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            check=False,
        )
        row["summary"] = summarize(json.loads(done.stdout))
        subprocess.run(
            command(cli, run, folder / "report.html", "html"),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, IndexError) as err:
        row["error"] = f"{type(err).__name__}: {err}"[:300]
    # A link exists only for a file that the CLI wrote.
    for label, name in (("HTML", "report.html"), ("JSON", "report.json")):
        if (folder / name).is_file():
            row["links"].append((label, f"{run['name']}/{name}"))
    return row


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
    anchors = [
        f'<a href="{html.escape(path, quote=True)}">{label}</a>' for label, path in row["links"]
    ]
    return f"<td>{' '.join(anchors) or 'none'}</td>"


def index(rows: Sequence[Mapping[str, Any]], sha: str, built_at: str) -> str:
    """One static page: plain HTML, no script, each dynamic text escaped."""
    body = "".join(
        f"<tr>{_cell(row['run']['name'])}{_cell(row['run']['language'])}{_verdict(row)}{_links(row)}</tr>\n"
        for row in rows
    )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width">\n'
        "<title>ArchKeel fixture reports</title></head><body>\n"
        "<h1>ArchKeel fixture reports</h1>\n"
        "<p>Each row is one run of the core on a project of <code>fixtures/</code>. "
        "A refused row shows the exact reason of the core. UNKNOWN is not a pass.</p>\n"
        f"<p>Commit <code>{html.escape(sha)}</code>. Built {html.escape(built_at)}.</p>\n"
        '<table border="1" cellpadding="4"><thead><tr><th>Fixture</th><th>Language</th>'
        "<th>Verdict</th><th>PASS</th><th>FAIL</th><th>UNKNOWN</th><th>Gaps</th><th>Reports</th></tr></thead>\n"
        f"<tbody>\n{body}</tbody></table>\n</body></html>\n"
    )


def _head_sha() -> str:
    done = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return done.stdout.strip() or "unknown"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, default=MATRIX)
    parser.add_argument(
        "--archkeel", default="archkeel", help="the CLI command, split like a shell"
    )
    parser.add_argument("--sha", default=None)
    parser.add_argument("--built-at", default=None)
    args = parser.parse_args(argv)
    if args.out.exists() and any(args.out.iterdir()):
        print(f"{args.out} is not empty; name a new directory.", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    cli = shlex.split(args.archkeel)
    rows = [build_run(cli, run, args.out) for run in load_runs(args.matrix)]
    built_at = args.built_at or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    page = index(rows, args.sha or _head_sha(), built_at)
    (args.out / "index.html").write_text(page)
    failed = [row["run"]["name"] for row in rows if "error" in row]
    if failed:
        print(f"No result for: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
