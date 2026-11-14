# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build the static fixture gallery: one report pair for each run of the matrix (AD-462).

The runs come from `fixtures/matrix.json`.
The tool decides nothing. It runs `archkeel report --output` for each run, reads the envelope that
the CLI prints, and shows the verdict, the counts and the refusal of the core as they are.
A run that gives no envelope gets a row without links and makes the exit code 1.
The first section of the index shows two self runs: ArchKeel on its Rust core and on its Python
shell. They have stable paths (`self/core.html`, `self/core.json`, `self/shell.html`,
`self/shell.json`) and one shield endpoint file each (`self/core-badge.json`,
`self/shell-badge.json`), so a README can link them for good. The badge colour comes from the
status of the envelope. A written file names the repository as `<repo>`: the path of the runner
is not published.

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
# The self runs: the stable name, the title, the configuration and the label of the badge.
SELF_RUNS: tuple[dict[str, str], ...] = (
    {
        "name": "core",
        "title": "Rust core (native/)",
        "config": "native/archkeel.toml",
        "label": "core self-check",
    },
    {
        "name": "shell",
        "title": "Python shell (src/archkeel)",
        "config": "docs/architecture/shell.toml",
        "label": "shell self-check",
    },
)
# Shields endpoint colours: green, red and amber. A run without a result is grey.
COLORS = {"PASS": "brightgreen", "FAIL": "red", "UNKNOWN": "f0a500"}


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
        # A DECLARATION row (an `allowed_dependency` rule) is no verdict; it gets its own count.
        counts[entry[1]] = counts.get(entry[1], 0) + 1
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
    root = run["root_path"] if "root_path" in run else f"fixtures/{run['root']}"
    arguments = [*cli, run["command"], "--root", root]
    if run.get("config"):
        arguments += ["--config", run["config"]]
    return [*arguments, "--output", str(target), "--format", form]


def _redact(path: Path) -> None:
    """Name the repository `<repo>` in a written report: the path of the runner is not published."""
    if not path.is_file():
        return
    data = path.read_bytes()
    for known in {str(ROOT), str(ROOT.resolve())}:
        data = data.replace(known.encode(), b"<repo>")
    path.write_bytes(data)


def _reports(
    cli: Sequence[str], run: Mapping[str, Any], folder: Path, stem: str, prefix: str
) -> dict[str, Any]:
    """Write both reports of one run as `<stem>.json` and `<stem>.html`. Return its row."""
    row: dict[str, Any] = {"run": run, "links": []}
    try:
        done = subprocess.run(
            [*command(cli, run, folder / f"{stem}.json", "json"), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            check=False,
        )
        row["summary"] = summarize(json.loads(done.stdout))
        subprocess.run(
            command(cli, run, folder / f"{stem}.html", "html"),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, IndexError) as err:
        row["error"] = f"{type(err).__name__}: {err}"[:300]
    # A link exists only for a file that the CLI wrote.
    for label, name in (("HTML", f"{stem}.html"), ("JSON", f"{stem}.json")):
        _redact(folder / name)
        if (folder / name).is_file():
            row["links"].append((label, f"{prefix}{name}"))
    return row


def build_run(cli: Sequence[str], run: Mapping[str, Any], out: Path) -> dict[str, Any]:
    """Write both reports of one matrix run into its folder. Return its row."""
    folder = out / run["name"]
    folder.mkdir(parents=True)
    return _reports(cli, run, folder, "report", f"{run['name']}/")


def badge(row: Mapping[str, Any], label: str) -> dict[str, Any]:
    """The shields endpoint document of a self run: the counts and the colour of its envelope."""
    summary = row.get("summary")
    if summary is None or summary["refusal"]:
        return {"schemaVersion": 1, "label": label, "message": "no result", "color": "lightgrey"}
    counts = summary["counts"]
    message = " · ".join(f"{counts[name]} {name}" for name in STATUSES)
    return {
        "schemaVersion": 1,
        "label": label,
        "message": message,
        "color": COLORS.get(summary["status"], "lightgrey"),
    }


def build_self(cli: Sequence[str], entry: Mapping[str, str], out: Path) -> dict[str, Any]:
    """Write the reports and the badge file of one self run at their stable paths."""
    folder = out / "self"
    folder.mkdir(exist_ok=True)
    run = {
        "name": entry["name"],
        "command": "report",
        "root_path": ".",
        "config": entry["config"],
        "language": entry["title"],
    }
    row = _reports(cli, run, folder, entry["name"], "self/")
    (folder / f"{entry['name']}-badge.json").write_text(
        json.dumps(badge(row, entry["label"]), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    row["title"] = entry["title"]
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


def _self_row(row: Mapping[str, Any]) -> str:
    return f"<tr>{_cell(row['title'])}{_verdict(row)}{_links(row)}</tr>\n"


def index(
    rows: Sequence[Mapping[str, Any]],
    sha: str,
    built_at: str,
    self_rows: Sequence[Mapping[str, Any]] = (),
) -> str:
    """One static page: plain HTML, no script, each dynamic text escaped."""
    body = "".join(
        f"<tr>{_cell(row['run']['name'])}{_cell(row['run']['language'])}{_verdict(row)}{_links(row)}</tr>\n"
        for row in rows
    )
    head = "<th>Verdict</th><th>PASS</th><th>FAIL</th><th>UNKNOWN</th><th>Gaps</th><th>Reports</th>"
    selves = ""
    if self_rows:
        selves = (
            "<h2>ArchKeel checks itself</h2>\n"
            "<p>ArchKeel runs on its own Rust core and on its own Python shell, with the "
            "contract of each. The table shows the result as the CLI prints it. "
            "A FAIL or an UNKNOWN stays visible.</p>\n"
            f'<table border="1" cellpadding="4"><thead><tr><th>Part</th>{head}</tr></thead>\n'
            f"<tbody>\n{''.join(map(_self_row, self_rows))}</tbody></table>\n"
            "<h2>Fixture reports</h2>\n"
        )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width">\n'
        "<title>ArchKeel reports</title></head><body>\n"
        "<h1>ArchKeel reports</h1>\n"
        f"<p>Commit <code>{html.escape(sha)}</code>. Built {html.escape(built_at)}.</p>\n"
        f"{selves}"
        "<p>Each row is one run of the core on a project of <code>fixtures/</code>. "
        "A refused row shows the exact reason of the core. UNKNOWN is not a pass.</p>\n"
        '<table border="1" cellpadding="4"><thead><tr><th>Fixture</th><th>Language</th>'
        f"{head}</tr></thead>\n"
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
    self_rows = [build_self(cli, entry, args.out) for entry in SELF_RUNS]
    rows = [build_run(cli, run, args.out) for run in load_runs(args.matrix)]
    built_at = args.built_at or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    page = index(rows, args.sha or _head_sha(), built_at, self_rows)
    (args.out / "index.html").write_text(page)
    failed = [row["run"]["name"] for row in [*self_rows, *rows] if "error" in row]
    if failed:
        print(f"No result for: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
