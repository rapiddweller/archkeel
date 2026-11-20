# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The gallery builder shows each matrix run and invents no link and no verdict (AD-462)."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tools import fixture_source, fixture_tree, report_gallery, report_gallery_page
from tools.report_product import Part


@contextmanager
def _fake_checkout(spec: dict, cache: Path | None = None) -> Iterator[Path]:
    """A checkout without the network: each folder that the fixture copies, with one file."""
    with tempfile.TemporaryDirectory() as folder:
        for item in spec["copy"]:
            target = Path(folder) / item["from"]
            target.mkdir(parents=True)
            (target / "upstream.txt").write_text("source\n")
        yield Path(folder)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test of the gallery fetches a pinned source: the real fetch is tested on a local repo."""
    monkeypatch.setattr(fixture_source, "checkout", _fake_checkout)


# A stand-in for the CLI. The root names the behavior: `served` writes both files and gives rule
# rows, `refused` gives a refusal and writes no file, `garbage` prints no envelope.
STUB = """
import json, sys
ROOT_PATH = %r
args = sys.argv[1:]
root = args[args.index("--root") + 1]
if "garbage" in root:
    print("not json")
    sys.exit(2)
if "refused" not in root:
    with open(args[args.index("--output") + 1], "w") as handle:
        handle.write(json.dumps({"root": ROOT_PATH}))
envelope = {"command": "report", "status": "UNKNOWN", "exit_code": 2, "gaps": []}
if "refused" in root:
    envelope["frame"] = {"rules": {}, "scope": "missing input"}
    envelope["refusal"] = {"kind": "collection_refused", "message": "<b>profile</b> refused"}
else:
    envelope["status"] = "UNKNOWN" if "unknown" in root else "FAIL"
    envelope["exit_code"] = 1
    envelope["frame"] = {"rules": {"A": ["x", "PASS"], "B": ["x", "FAIL"]}, "scope": "complete"}
print(json.dumps(envelope))
"""


def _run(name: str, root: str) -> dict:
    return {"name": name, "root": root, "command": "report", "contract": ["c.json"], "expect": {}}


def _matrix(path: Path, runs: list[dict]) -> Path:
    table = {run["name"]: {"language": "rust", "runs": [run]} for run in runs}
    path.write_text(json.dumps({"fixtures": table}))
    return path


def _stub(tmp_path: Path) -> str:
    script = tmp_path / "stub.py"
    script.write_text(STUB % str(report_gallery.ROOT))
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


def _build(tmp_path: Path, matrix: Path) -> tuple[int, Path]:
    out = tmp_path / "site"
    code = report_gallery.main(
        [
            "--out",
            str(out),
            "--matrix",
            str(matrix),
            "--archkeel",
            _stub(tmp_path),
            "--sha",
            "abc123",
            "--built-at",
            "2026-11-14 02:17 UTC",
        ]
    )
    return code, out


def test_the_showcase_lists_every_matrix_entry_with_commit_and_time(tmp_path: Path) -> None:
    code, out = _build(tmp_path, report_gallery.MATRIX)
    page = (out / "showcase" / "index.html").read_text()
    names = [run["name"] for run in report_gallery.showcase_runs()]
    assert code == 0
    assert all(f"<td>{name}</td>" in page for name in names)
    assert "abc123" in page
    assert "2026-11-14 02:17 UTC" in page
    assert page.count("<script>") == 1 and "src=" not in page
    assert 'data-ak-theme="light"' in page and "--surface-0" in page
    assert 'href="../index.html"' in page
    captions = re.findall(r'<p class="caption">(\d+) runs?</p>', page)
    # The self-check is one more card, the anchor of the real projects.
    assert sum(map(int, captions)) == len(names) + 1
    capabilities = (out / "capabilities.html").read_text()
    assert 'href="own/browser.html"' in capabilities
    assert (out / "own/browser.json").is_file()


def test_a_run_with_showcase_false_is_not_listed_but_stays_in_the_table(tmp_path: Path) -> None:
    hidden = {**_run("hidden-one", "served-h"), "showcase": False}
    matrix = _matrix(tmp_path / "m.json", [_run("shown-one", "served-s"), hidden])
    code, out = _build(tmp_path, matrix)
    page = (out / "showcase" / "index.html").read_text()
    assert code == 0
    assert "<td>shown-one</td>" in page and "hidden-one" not in page
    assert not (out / "hidden-one").exists()
    assert [run["name"] for run in report_gallery.load_runs(matrix)] == ["hidden-one", "shown-one"]


def test_runs_without_a_contract_rule_are_not_in_the_showcase() -> None:
    hidden = {"E-runtime", "F-typescript-story", "P-rust-story"}
    hidden |= {run["name"] for run in report_gallery.load_runs() if "golden-python" in run["name"]}
    shown = {run["name"] for run in report_gallery.showcase_runs()}
    assert len(hidden) == 9 and not hidden & shown
    assert hidden <= {run["name"] for run in report_gallery.load_runs()}


def test_a_served_row_shows_the_counts_and_links_to_both_reports(tmp_path: Path) -> None:
    matrix = _matrix(tmp_path / "m.json", [_run("served-one", "served-one")])
    code, out = _build(tmp_path, matrix)
    page = (out / "showcase" / "index.html").read_text()
    assert code == 0
    assert "<td>FAIL</td><td>1</td><td>1</td><td>0</td><td>none</td>" in page
    for form in ("html", "json"):
        assert f'href="../served-one/report.{form}"' in page
        assert (out / "served-one" / f"report.{form}").is_file()


def test_a_refused_row_has_its_reason_and_no_dead_link(tmp_path: Path) -> None:
    matrix = _matrix(tmp_path / "m.json", [_run("refused-one", "refused-one")])
    code, out = _build(tmp_path, matrix)
    page = (out / "showcase" / "index.html").read_text()
    assert code == 0
    assert "refused: &lt;b&gt;profile&lt;/b&gt; refused" in page
    assert "<b>" not in page
    assert "href=" not in page.split("<tbody>")[-1]
    assert not (out / "refused-one" / "report.html").exists()


def test_every_link_points_at_a_file_that_exists(tmp_path: Path) -> None:
    runs = [_run("served-a", "served-a"), _run("refused-b", "refused-b")]
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", runs))
    folder = out / "showcase"
    found = re.findall(r'href="([^"]+)"', (folder / "index.html").read_text())
    links = [link for link in found if not link.startswith("https://")]
    assert code == 0
    assert links
    assert all((folder / link).resolve().is_file() for link in links)


def test_a_run_without_an_envelope_gets_a_row_and_fails_the_build(tmp_path: Path) -> None:
    runs = [_run("garbage-one", "garbage-one"), _run("served-two", "served-two")]
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", runs))
    page = (out / "showcase" / "index.html").read_text()
    assert code == 1
    assert "no result: " in page
    assert "<td>garbage-one</td>" in page
    assert "<td>served-two</td>" in page


def test_the_builder_refuses_a_directory_that_holds_files(tmp_path: Path) -> None:
    out = tmp_path / "site"
    out.mkdir()
    (out / "keep.txt").write_text("keep")
    assert report_gallery.main(["--out", str(out)]) == 2
    assert (out / "keep.txt").read_text() == "keep"


def test_gallery_distinguishes_collection_gaps_from_rule_findings() -> None:
    frame = {
        "rules": {"A": ["rule", "UNKNOWN"]},
        "collection_gaps": [{"kind": "source_resolution_gap"}],
    }
    summary = report_gallery.summarize(
        {"exit_code": 2, "status": "UNKNOWN", "frame": frame, "gaps": []}
    )
    rendered = report_gallery_page._verdict({"frame": frame, "summary": summary})
    assert rendered.endswith("<td>1</td><td>none</td><td>1</td><td>unavailable</td>")


def test_dynamic_text_is_escaped_in_the_index() -> None:
    run = {"name": "x<y", "about": "a&b", "intent": "PASS", "blocked_by": [7]}
    row = {"run": run, "links": [("HTML", 'p"q/report.html')]}
    row["error"] = "<script>alert(1)</script>"
    page = report_gallery_page.index([row], "sha<1>", "now&then")
    assert "<script>alert" not in page and page.count("<script>") == 1
    assert "x&lt;y" in page
    assert "a&amp;b" in page
    assert "sha&lt;1&gt;" in page
    assert 'href="../p&quot;q/report.html"' in page


@pytest.mark.parametrize("run", report_gallery.load_runs(), ids=lambda run: run["name"])
def test_each_matrix_run_names_a_folder_that_the_builder_can_make(run: dict) -> None:
    assert "/" not in run["name"]
    assert (report_gallery.ROOT / "fixtures" / run["root"]).is_dir()


def test_the_entry_is_the_system_report_with_the_explorer_and_the_self_reports_keep_their_paths(
    tmp_path: Path,
) -> None:
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", [_run("served-a", "served-a")]))
    page = (out / "index.html").read_text()
    assert code == 0
    # One page for the whole system, drawn by the core from the system document (the stub writes
    # its root): a bar of links leads to the fixtures and to the page of each part.
    assert json.dumps({"root": "<repo>"}) in page
    assert "Fixture reports" in page
    assert 'href="showcase/index.html"' in page
    # The open page is marked in the navigation.
    assert 'href="self/index.html" aria-current="page">System</a>' in page
    assert "served-a" not in page
    for name in ("core", "shell", "studio"):
        assert f'href="self/{name}.html"' in page
        for ext in ("html", "json"):
            assert (out / "self" / f"{name}.{ext}").is_file()
        assert (out / "self" / f"{name}-badge.json").is_file()
        # The page of a part links back to the system page.
        part = (out / "self" / f"{name}.html").read_text()
        assert '<a href="index.html">System</a>' in part and 'aria-current="page"' in part


def test_a_self_badge_shows_the_counts_and_the_colour_of_the_status(tmp_path: Path) -> None:
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", [_run("served-a", "served-a")]))
    assert code == 0
    badge = json.loads((out / "self" / "core-badge.json").read_text())
    assert badge == {
        "schemaVersion": 1,
        "label": "core self-check",
        "message": "1 PASS · 1 FAIL · 0 UNKNOWN",
        "color": "f2606b",
    }
    assert (
        json.loads((out / "self" / "shell-badge.json").read_text())["label"] == "shell self-check"
    )


@pytest.mark.parametrize(
    ("status", "color"), [("PASS", "46bfd0"), ("FAIL", "f2606b"), ("UNKNOWN", "ecb64a")]
)
def test_the_badge_colour_follows_the_status(status: str, color: str) -> None:
    counts = {"PASS": 2, "FAIL": 0, "UNKNOWN": 1}
    row = {"summary": {"status": status, "counts": counts, "refusal": None}}
    made = report_gallery.badge(row, "x")
    assert made["color"] == color and made["message"] == "2 PASS · 0 FAIL · 1 UNKNOWN"


def test_a_self_run_without_a_result_gets_a_grey_badge_and_fails_the_build() -> None:
    assert report_gallery.badge({"error": "boom"}, "x")["color"] == "lightgrey"
    refused = {"summary": {"status": "UNKNOWN", "counts": {}, "refusal": {"message": "m"}}}
    assert report_gallery.badge(refused, "x")["message"] == "no result"


def test_a_written_report_does_not_name_the_path_of_the_runner(tmp_path: Path) -> None:
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", [_run("served-a", "served-a")]))
    assert code == 0
    for path in [out / "self" / "core.json", out / "served-a" / "report.json"]:
        text = path.read_text()
        assert str(report_gallery.ROOT) not in text and "<repo>" in text


def test_the_system_page_and_badge_sit_in_self_and_link_their_neighbours(tmp_path: Path) -> None:
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", [_run("served-a", "served-a")]))
    assert code == 0
    page = (out / "self" / "index.html").read_text()
    assert json.dumps({"root": "<repo>"}) in page
    links = re.findall(r'href="([^"#]+)', page)
    assert {"core.html", "shell.html", "studio.html"} <= set(links)
    assert all((out / "self" / link).resolve().is_file() for link in links)
    badge = json.loads((out / "self" / "badge.json").read_text())
    assert badge["label"] == "ArchKeel self-check" and badge["color"] == "f2606b"
    assert badge["message"] == "3 PASS · 3 FAIL · 0 UNKNOWN"


def test_the_badge_of_the_system_has_no_result_when_a_part_has_none() -> None:
    assert report_gallery.system_badge([])["message"] == "no result"


def _row(run: dict, status: str | None) -> dict:
    summary = None if status is None else {"status": status, "counts": dict.fromkeys(STATUSES, 0)}
    summary = summary and {**summary, "gaps": {}, "refusal": None}
    return {"run": {"name": "n", **run}, "links": [], **({"summary": summary} if summary else {})}


STATUSES = report_gallery_page.STATUSES


def _section(page: str, key: str) -> str:
    return page.split(f'id="sec-{key}"')[1].split("</section>")[0]


def test_the_page_has_four_sections_in_order_and_each_run_sits_in_its_own() -> None:
    rows = [
        _row({"name": "u", "section": "unknown", "intent": "UNKNOWN", "about": "au"}, "UNKNOWN"),
        _row({"name": "c", "section": "clean", "intent": "PASS", "about": "ac"}, "PASS"),
        _row({"name": "v", "section": "violation", "intent": "FAIL", "about": "av"}, "FAIL"),
        _row({"name": "r", "section": "real", "intent": "PASS", "about": "ar"}, "PASS"),
    ]
    page = report_gallery_page.index(rows, "sha", "now")
    titles = re.findall(r'<h2 class="h3" id="sec-(\w+)">([^<]+)</h2>', page)
    assert titles == [
        ("real", "Real projects (PASS earned)"),
        ("clean", "Clean scenarios (PASS on purpose)"),
        ("violation", "Violation scenarios (FAIL on purpose)"),
        ("unknown", "What UNKNOWN means"),
    ]
    for key, name in (("real", "r"), ("clean", "c"), ("violation", "v"), ("unknown", "u")):
        assert f"<td>{name}</td>" in _section(page, key)
        assert page.count(f"<td>{name}</td>") == 1


def test_an_empty_section_is_not_drawn() -> None:
    rows = [_row({"section": "clean", "intent": "PASS", "about": "a"}, "PASS")]
    page = report_gallery_page.index(rows, "sha", "now")
    assert 'id="sec-clean"' in page
    assert all(f'id="sec-{key}"' not in page for key in ("real", "violation", "unknown"))


def test_the_self_check_is_the_anchor_card_of_the_real_projects(tmp_path: Path) -> None:
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", [_run("served-a", "served-a")]))
    page = (out / "showcase" / "index.html").read_text()
    real = _section(page, "real")
    assert code == 0
    assert "<td>ArchKeel self-check</td>" in real
    assert 'href="../self/index.html"' in real
    # The stub gives a FAIL for each part: the card says so next to the intent.
    assert "expected PASS" in real and "FAIL today" in real


def test_a_run_that_meets_its_intent_says_so_without_a_blocker() -> None:
    assert "expected PASS</span> \u00b7 PASS" in report_gallery_page.intent_line(
        {"intent": "PASS"}, "PASS"
    )
    assert "expected FAIL</span> \u00b7 FAIL" in report_gallery_page.intent_line(
        {"intent": "FAIL"}, "FAIL"
    )
    line = report_gallery_page.intent_line({"intent": "UNKNOWN"}, "UNKNOWN")
    assert "UNKNOWN on purpose</span> \u00b7 UNKNOWN" in line
    assert "blocked" not in line and "not met" not in line


def test_a_run_that_differs_from_its_intent_names_the_difference_and_its_blocker() -> None:
    run = {"intent": "PASS", "blocked_by": [1534, 1533]}
    line = report_gallery_page.intent_line(run, "UNKNOWN")
    assert "expected PASS" in line and "UNKNOWN today" in line
    assert "blocked by" in line
    assert f'href="{report_gallery_page.REPOSITORY}/issues/1534">#1534</a>' in line
    assert "#1533" in line


def test_a_difference_without_a_blocker_is_a_scenario_not_met() -> None:
    line = report_gallery_page.intent_line({"intent": "FAIL"}, "PASS")
    assert "expected FAIL" in line and "PASS today" in line and "scenario not met" in line
    assert "ak-t-fail" in line
    assert "no result" in report_gallery_page.intent_line({"intent": "PASS"}, None)
    assert "no intent stated" in report_gallery_page.intent_line({}, "PASS")


def test_every_shown_matrix_run_states_a_section_an_intent_and_a_blocker_when_it_differs() -> None:
    known = {key for key, _, _ in report_gallery_page.SECTIONS}
    for run in report_gallery.showcase_runs():
        assert run.get("section") in known, run["name"]
        assert run.get("intent") in STATUSES, run["name"]
        assert run.get("about"), run["name"]
        pinned = run["expect"]["status"]
        # What the matrix pins today may differ from the intent only with a named issue.
        assert run["intent"] == pinned or run.get("blocked_by"), run["name"]


# A stand-in that writes what it saw below the root: the folder `node_modules` and the root itself.
PROBE = """
import json, os, sys
args = sys.argv[1:]
root = args[args.index("--root") + 1]
seen = {"root": root, "modules": os.path.isdir(os.path.join(root, "node_modules"))}
with open(args[args.index("--output") + 1], "w") as handle:
    handle.write(json.dumps(seen))
print(json.dumps({"status": "UNKNOWN", "exit_code": 2, "gaps": [], "frame": {"rules": {}}}))
"""


def test_a_fixture_with_resolver_inputs_runs_in_a_copy_that_holds_node_modules(
    tmp_path: Path,
) -> None:
    script = tmp_path / "probe.py"
    script.write_text(PROBE)
    cli = [sys.executable, str(script)]
    run = {"name": "L-nest-realworld", "root": "L-nest-realworld", "command": "report"}
    row = report_gallery.build_run(cli, run, tmp_path)
    seen = json.loads((tmp_path / "L-nest-realworld" / "report.json").read_text())
    assert "error" not in row
    assert seen["modules"] is True
    # The source stays as it is, and the report names the fixture, not the temporary copy.
    assert not (report_gallery.ROOT / "fixtures" / "L-nest-realworld" / "node_modules").exists()
    assert seen["root"] == "<repo>/fixtures/L-nest-realworld"


def test_a_fixture_without_resolver_inputs_runs_in_place(tmp_path: Path) -> None:
    script = tmp_path / "probe.py"
    script.write_text(PROBE)
    run = {"name": "M-review-workflow", "root": "M-review-workflow", "command": "report"}
    report_gallery.build_run([sys.executable, str(script)], run, tmp_path)
    seen = json.loads((tmp_path / "M-review-workflow" / "report.json").read_text())
    assert seen["root"] == "fixtures/M-review-workflow" and seen["modules"] is False


def test_the_copy_commits_the_resolver_inputs_and_an_overlay_as_tracked_files(
    tmp_path: Path,
) -> None:
    source = report_gallery.ROOT / "fixtures" / "L-nest-realworld"
    assert fixture_tree.needs_copy(source)
    assert not fixture_tree.needs_copy(report_gallery.ROOT / "fixtures" / "M-review-workflow")
    with fixture_tree.fixture_tree(
        source, [{"path": "src/planted.ts", "append": "export const x = 1;\n"}]
    ) as tree:
        done = subprocess.run(
            ["git", "ls-files"], cwd=tree, capture_output=True, text=True, check=True
        )
        tracked = done.stdout.splitlines()
        assert any(name.startswith("node_modules/@nestjs/") for name in tracked)
        assert "src/planted.ts" in tracked
        assert (tree / "node_modules").is_dir()
    assert not tree.exists()


def test_the_page_navigation_lists_the_system_and_its_parts_first_and_the_fixtures_apart() -> None:
    page = report_gallery.nav(
        "<main></main>",
        [("System", "index.html"), ("Part A", "a.html")],
        "Part A",
        ("Fixture reports", "../showcase/index.html"),
    )
    labels = re.findall(r">([^<]+)</a>", page)
    assert labels == ["System", "Part A", "Fixture reports"]
    # A thin divider sets the other kind of page apart; the open page is marked.
    assert page.index("rp-pages__divider") < page.index("Fixture reports")
    assert page.index("rp-pages__divider") > page.index("Part A")
    assert 'href="a.html" aria-current="page">Part A</a>' in page


def _part(title: str, gaps: int) -> Part:
    counts = {"PASS": 5, "FAIL": 0, "UNKNOWN": 0}
    return Part("k", title, "rust", "s", "r.html", status="PASS", counts=counts, gaps=gaps)


def test_the_self_check_row_shows_the_real_gap_count_of_all_parts() -> None:
    clean = report_gallery_page.index([], "sha", "now", [_part("Core", 0), _part("Shell", 0)])
    assert "<td>none</td>" in clean
    page = report_gallery_page.index([], "sha", "now", [_part("Core", 3), _part("Shell", 2)])
    assert "<td>5 collection gaps (Core 3, Shell 2)</td>" in page
    one = report_gallery_page.index([], "sha", "now", [_part("Core", 0), _part("Shell", 1)])
    assert "<td>1 collection gap (Shell 1)</td>" in one
