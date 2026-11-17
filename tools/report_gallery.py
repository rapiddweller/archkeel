# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build the static fixture gallery: one report pair for each run of the matrix (AD-462).

The runs come from `fixtures/matrix.json`. A run with `"showcase": false` has no scenario to show
(an empty contract, a collector golden); the tests keep it and the gallery skips it.
The tool decides nothing. It runs `archkeel report --output` for each run, reads the envelope that
the CLI prints, and shows the verdict, the counts and the refusal of the core as they are.
A run that gives no envelope gets a row without links and makes the exit code 1.
The entry page `index.html` is the report of the system: the core runs
`docs/architecture/architecture-system.json` in one run and draws one page with the Explorer, which
starts at the system view and opens each part inside the same page. A link bar leads to the
fixture table and to the page of each part; the page of a part links back to the system page. The
fixture table is at
`showcase/index.html`. The self runs have stable paths (`self/core.html`, `self/core.json`,
`self/shell.html`, `self/shell.json`) and one shield endpoint file each (`self/core-badge.json`,
`self/shell-badge.json`). The system of all parts has `self/index.html` and `self/badge.json`, so a
README can link them for good. The badge colour comes from the status of the envelope. A
written file names the repository as `<repo>`: the path of the runner is not published.

Run: `python -m tools.report_gallery --out DIR [--archkeel "uv run --locked archkeel"]`.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shlex
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools import fixture_source
from tools.fixture_source import SourceError
from tools.fixture_tree import fixture_tree, needs_copy
from tools.report_gallery_page import STATUSES, index
from tools.report_product import (
    Contract,
    Part,
    contract_of,
    part_of,
    system,
)
from tools.system_parts import DOCUMENT, System, load

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "fixtures" / "matrix.json"
RUN_TIMEOUT = 900


# The self runs, one for each part of the system document (`tools/system_parts.py`).
def self_runs(system: System) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "name": part.id,
            "title": part.subject,
            "part": part.title,
            "language": part.language,
            "config": part.config,
            "label": part.label,
        }
        for part in system.parts
    )


SELF_RUNS = self_runs(load())
# The other own contracts: one line on the product page each, no report file of their own. None
# today: the browser assets and the Studio UI returned to history (AD-582).
OTHER_RUNS: tuple[dict[str, str], ...] = ()
# Shields endpoint colours (design-system palette): pass, fail and unknown. No result is grey.
COLORS = {"PASS": "46bfd0", "FAIL": "f2606b", "UNKNOWN": "ecb64a"}


def load_runs(matrix: Path = MATRIX) -> list[dict[str, Any]]:
    """The runs of the matrix in table order, each with the key of its fixture."""
    table = json.loads(matrix.read_text())["fixtures"]
    return [
        {**run, "fixture": name, "language": entry["language"]}
        for name, entry in sorted(table.items())
        for run in entry["runs"]
    ]


def showcase_runs(matrix: Path = MATRIX) -> list[dict[str, Any]]:
    """The runs that the gallery shows. A run with `"showcase": false` is a test fixture only."""
    return [run for run in load_runs(matrix) if run.get("showcase", True)]


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


def _redact(path: Path, copies: Mapping[str, str] | None = None) -> None:
    """Name the repository `<repo>` in a written report: the path of the runner is not published.

    `copies` maps the path of a temporary copy of a fixture to the name that the report shows.
    """
    if not path.is_file():
        return
    data = path.read_bytes()
    for known in {str(ROOT), str(ROOT.resolve())}:
        data = data.replace(known.encode(), b"<repo>")
    for known, name in (copies or {}).items():
        data = data.replace(known.encode(), name.encode())
    path.write_bytes(data)


def _reports(
    cli: Sequence[str],
    run: Mapping[str, Any],
    folder: Path,
    stem: str,
    prefix: str,
    copies: Mapping[str, str] | None = None,
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
        _redact(folder / name, copies)
        if (folder / name).is_file():
            row["links"].append((label, f"{prefix}{name}"))
    return row


def build_run(
    cli: Sequence[str], run: Mapping[str, Any], out: Path, cache: Path | None = None
) -> dict[str, Any]:
    """Write both reports of one matrix run into its folder. Return its row."""
    folder = out / run["name"]
    folder.mkdir(parents=True)
    source = ROOT / "fixtures" / run["root"]
    plant = run.get("plant") or {}
    edits = plant.get("edits")
    prefix = f"{run['name']}/"
    if not needs_copy(source, edits):
        return _reports(cli, run, folder, "report", prefix)
    # A fixture with resolver inputs, or with a planted change, runs in a copy (AD-462).
    try:
        with fixture_tree(source, edits, cache) as tree:
            shown = f"<repo>/fixtures/{run['root']}"
            copies = {str(tree): shown, str(tree.resolve()): shown}
            prepared = {**run, "root_path": str(tree)}
            row = _reports(cli, prepared, folder, "report", prefix, copies)
    except (SourceError, OSError, subprocess.SubprocessError) as err:
        # A pinned source that cannot be fetched is no result: the build fails, it never skips.
        return {"run": run, "links": [], "error": f"{type(err).__name__}: {err}"[:300]}
    spec = fixture_source.load(source)
    if spec is not None:
        row["source"] = fixture_source.pin_facts(spec)
    if plant.get("rule"):
        row["violation"] = violation_block(folder / "report.html", plant)
    return row


def _token(word: str) -> re.Pattern[str]:
    """`word` as a whole name: no name character before or after it."""
    return re.compile(rf"(?<![\w.:-]){re.escape(word)}(?![\w.:-])")


def violation_block(page: Path, plant: Mapping[str, Any]) -> dict[str, str] | None:
    """The block of the report page that shows the exact finding of a plant.

    The finding is the rule id plus its source and its target. The core writes one `rp-dos` block
    for each place in the code and lists each rule that fails there. A block is the finding when
    it says `Violates <rule id>` (the whole id: `R-1` is not `R-10`) and names both the source and
    the target as whole names. A rule id alone is not enough: two plants can break the same rule.
    None when no block shows the finding.
    """
    if not page.is_file():
        return None
    text = page.read_text(encoding="utf-8")
    violates = re.compile(rf"Violates {re.escape(plant['rule'])}(?![\w-])")
    names = [_token(plant["source"]), _token(plant["target"])]
    for block in re.split(r'(?=<article class="rp-dos" id="x\d+">)', text):
        found = re.match(r'<article class="rp-dos" id="(x\d+)">', block)
        if not found:
            continue
        body = block.split("</article>", 1)[0]
        title = re.search(r'<h3 class="h3">(.*?)</h3>', body, re.DOTALL)
        shown = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))
        if title and violates.search(shown) and all(name.search(shown) for name in names):
            return {"id": found.group(1), "title": html.unescape(re.sub(r"<[^>]+>", "", title[1]))}
    return None


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


def system_badge(parts: Sequence[Part]) -> dict[str, Any]:
    """The one shields endpoint document of the system. Message and colour come from `system`, as
    the page does, so a FAIL of one part is never hidden by a part without a result."""
    label = "ArchKeel self-check"
    if not parts:
        return {"schemaVersion": 1, "label": label, "message": "no result", "color": "lightgrey"}
    verdict = system(parts)
    words = [f"{verdict.counts[name]} {name}" for name in STATUSES]
    missing = sum(1 for part in parts if not part.decided)
    if missing:
        words.append(f"{missing} no result")
    return {
        "schemaVersion": 1,
        "label": label,
        "message": " · ".join(words),
        "color": COLORS[verdict.status],
    }


def _topology_envelope(
    cli: Sequence[str], run: Mapping[str, Any], topology: bool = True
) -> tuple[dict[str, Any] | None, str]:
    """The envelope of a run, with the topology unless told otherwise. Its file is thrown away."""
    with tempfile.TemporaryDirectory() as folder:
        arguments = [*command(cli, run, Path(folder) / "t.json", "json"), "--json"]
        arguments += ["--topology"] if topology else []
        try:
            done = subprocess.run(
                arguments,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT,
                check=False,
            )
            return json.loads(done.stdout), ""
        except (OSError, subprocess.TimeoutExpired, ValueError) as err:
            return None, f"{type(err).__name__}: {err}"[:300]


def build_other(cli: Sequence[str], entry: Mapping[str, str]) -> Contract:
    """The line of one other contract. The CLI writes its file into a folder that is thrown away."""
    run = {"name": "other", "command": "report", "root_path": ".", "config": entry["config"]}
    envelope, problem = _topology_envelope(cli, run, topology=False)
    return contract_of(envelope, entry["title"], problem)


def nav(
    page: str,
    links: Sequence[tuple[str, str]],
    current: str = "",
    apart: tuple[str, str] | None = None,
) -> str:
    """The page with one visible navigation of its neighbour pages, first in its `<main>`.

    The link of the page that is open is marked with `aria-current="page"`; it is `current`. The
    `apart` link, another kind of page, comes last behind a thin divider.
    """

    def link(label: str, href: str) -> str:
        mark = ' aria-current="page"' if label == current else ""
        return f'<a href="{html.escape(href, quote=True)}"{mark}>{html.escape(label)}</a>'

    items = "".join(link(label, href) for label, href in links)
    if apart:
        items += '<span class="rp-pages__divider" aria-hidden="true"></span>' + link(*apart)
    bar = f'<nav class="rp-pages" aria-label="Report pages">{items}</nav>'
    # The bar sits first inside `<main>`, where the links have the style of the report.
    if not re.search(r"<main[^>]*>", page):
        return bar + page
    return re.sub(r"(<main[^>]*>)", lambda found: found.group(1) + bar, page, count=1)


def build_system(cli: Sequence[str], system: System, document: Path, out: Path) -> dict[str, Any]:
    """Write the report of the whole system, drawn by the core, at `self/system.{html,json}`.

    `self/index.html` and `index.html` are this page with a bar of links, and the page of each part
    links back to it. The page decides nothing: the core drew it from one system run.
    """
    folder = out / "self"
    folder.mkdir(exist_ok=True)
    try:
        config = str(document.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        config = str(document)
    run = {"name": "system", "command": "report", "root_path": ".", "config": config}
    row = _reports(cli, run, folder, "system", "self/")
    page = folder / "system.html"
    if not page.is_file():
        return row
    parts = [(part.title, f"{part.id}.html") for part in system.parts]
    text = page.read_text()
    shown = "System"
    siblings = [(shown, "index.html"), *parts]
    (folder / "index.html").write_text(
        nav(text, siblings, shown, ("Fixture reports", "../showcase/index.html"))
    )
    entry = [(label, f"self/{href}") for label, href in siblings]
    (out / "index.html").write_text(
        nav(text, entry, shown, ("Fixture reports", "showcase/index.html"))
    )
    for part in system.parts:
        each = folder / f"{part.id}.html"
        if each.is_file():
            each.write_text(
                nav(
                    each.read_text(),
                    siblings,
                    part.title,
                    ("Fixture reports", "../showcase/index.html"),
                )
            )
    return row


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
    page = folder / f"{entry['name']}.html"
    envelope, problem = (
        (None, row.get("error", "")) if "error" in row else _topology_envelope(cli, run)
    )
    if envelope is not None and not page.is_file():
        envelope, problem = None, "the CLI wrote no report"
    row["part"] = part_of(envelope, entry, f"self/{page.name}", problem)
    row["ids"] = (
        frozenset(re.findall(r'\sid="([^"]+)"', page.read_text()))
        if page.is_file()
        else frozenset()
    )
    return row


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
    parser.add_argument("--system", type=Path, default=DOCUMENT, help="the system document")
    parser.add_argument(
        "--source-cache",
        type=Path,
        default=None,
        help="where pinned sources are kept between builds",
    )
    parser.add_argument("--sha", default=None)
    parser.add_argument("--built-at", default=None)
    args = parser.parse_args(argv)
    if args.out.exists() and any(args.out.iterdir()):
        print(f"{args.out} is not empty; name a new directory.", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    cli = shlex.split(args.archkeel)
    sha = args.sha or _head_sha()
    system = load(args.system)
    self_rows = [build_self(cli, entry, args.out) for entry in self_runs(system)]
    rows = [build_run(cli, run, args.out, args.source_cache) for run in showcase_runs(args.matrix)]
    built_at = args.built_at or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    others = [build_other(cli, entry) for entry in OTHER_RUNS]
    parts: list[Part] = [row["part"] for row in self_rows]
    system_row = build_system(cli, system, args.system, args.out)
    (args.out / "self" / "badge.json").write_text(
        json.dumps(system_badge(parts), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.out / "showcase").mkdir()
    (args.out / "showcase" / "index.html").write_text(index(rows, sha, built_at, parts))
    failed = [row["run"]["name"] for row in [*self_rows, *rows] if "error" in row]
    failed += [part.key for part in parts if part.error and part.key not in failed]
    failed += [item.title for item in others if item.error]
    if "error" in system_row or not (args.out / "index.html").is_file():
        failed.append("system")
    if failed:
        print(f"No result for: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
