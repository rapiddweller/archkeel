# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The gallery builder shows each matrix run and invents no link and no verdict (AD-462)."""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

import pytest

from tools import report_gallery

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
    names = [run["name"] for run in report_gallery.load_runs()]
    assert code == 0
    assert all(f"<td>{name}</td>" in page for name in names)
    assert "abc123" in page
    assert "2026-11-14 02:17 UTC" in page
    assert "<script" not in page
    assert 'href="../index.html"' in page


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
    assert "href=" not in page.split("<tbody>")[1]
    assert not (out / "refused-one" / "report.html").exists()


def test_every_link_points_at_a_file_that_exists(tmp_path: Path) -> None:
    runs = [_run("served-a", "served-a"), _run("refused-b", "refused-b")]
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", runs))
    folder = out / "showcase"
    links = re.findall(r'href="([^"]+)"', (folder / "index.html").read_text())
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


def test_dynamic_text_is_escaped_in_the_index() -> None:
    row = {"run": {"name": "x<y", "language": "a&b"}, "links": [("HTML", 'p"q/report.html')]}
    row["error"] = "<script>alert(1)</script>"
    page = report_gallery.index([row], "sha<1>", "now&then")
    assert "<script>" not in page
    assert "x&lt;y" in page
    assert "a&amp;b" in page
    assert "sha&lt;1&gt;" in page
    assert 'href="../p&quot;q/report.html"' in page


@pytest.mark.parametrize("run", report_gallery.load_runs(), ids=lambda run: run["name"])
def test_each_matrix_run_names_a_folder_that_the_builder_can_make(run: dict) -> None:
    assert "/" not in run["name"]
    assert (report_gallery.ROOT / "fixtures" / run["root"]).is_dir()


def test_the_entry_is_the_product_page_and_the_self_reports_keep_their_paths(
    tmp_path: Path,
) -> None:
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", [_run("served-a", "served-a")]))
    page = (out / "index.html").read_text()
    assert code == 0
    assert "ArchKeel as a product: 2 parts, 2 runs, worst verdict FAIL" in page
    assert 'href="showcase/index.html"' in page
    assert "served-a" not in page
    for name in ("core", "shell"):
        for ext in ("html", "json"):
            assert f'href="self/{name}.{ext}"' in page or ext == "json"
            assert (out / "self" / f"{name}.{ext}").is_file()
        assert (out / "self" / f"{name}-badge.json").is_file()
    assert "Rust core" in page and "Python shell" in page


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
