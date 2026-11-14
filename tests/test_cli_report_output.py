# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A report file keeps the verdict of the accepted core frame (AD-440)."""

from __future__ import annotations

import errno
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from core_support import run
from corpus_support import commit_tree
from frozen_native import frozen_root as frozen_root
from rust_repository import CRATE_RULES, GRAPH_PAGE, component, repository, rule

from archkeel.cli import core_only, core_output


def project(root: Path, binary: Path, profile: str, status: str) -> Path:
    parts = (component("base", "base_crate"), component("app", "app", ("base",)))
    if status == "FAIL":
        parts = (component("base", "base_crate"), component("app", "app"))
    rules = None
    if status == "UNKNOWN":
        rules = (rule("UNPORTED", "symbol_placement", source="native"),)
    # AD-466: the marked graph draws the observed edge also when no `requires` entry allows it.
    drawn = "    app --> base"
    root = repository(
        root, binary, components=parts, drawn=drawn, **({"rules": rules} if rules else {})
    )
    if profile == "typescript":
        (root / "docs/target.md").write_text(GRAPH_PAGE.format(edges="    app"))
        (root / "src").mkdir()
        (root / "src/index.ts").write_text("export const value = 1;\n")
        (root / "tsconfig.json").write_text(
            '{"compilerOptions": {"strict": true}, "include": ["src"]}'
        )
        part = component("app", "app" if status != "FAIL" else "absent")
        part["packages"] = ["app" if status != "FAIL" else "absent"]
        contract = {
            "schema_version": "2.1.0",
            "components": [part],
            "rules": list(rules or (rule("ASSIGNED", "complete_assignment", source="app"),)),
        }
        (root / "architecture-contract.json").write_text(json.dumps(contract))
        (root / "archkeel.toml").write_text(
            '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\n'
        )
    if status == "REFUSED":
        config = root / "archkeel.toml"
        config.write_text(
            config.read_text().replace(f'language = "{profile}"', 'language = "python"')
        )
    commit_tree(root)
    return root


@pytest.mark.parametrize("profile", ["rust", "typescript"])
@pytest.mark.parametrize("status", ["PASS", "FAIL", "UNKNOWN", "REFUSED"])
@pytest.mark.parametrize("form", ["json", "html"])
def test_files_keep_the_frame_and_exit(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    status: str,
    form: str,
) -> None:
    root = project(tmp_path / "project", release_core, profile, status)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / f"report.{form}"
    before_code, before = run("report", "--root", str(root))
    code, found = run("report", "--root", str(root), "--output", str(target), "--format", form)
    assert (code, found) == (before_code, before), found
    assert code == {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "REFUSED": 2}[status]
    assert target.is_file()
    if form == "json":
        assert json.loads(target.read_bytes()) == found["frame"]
    else:
        text = target.read_text()
        assert f"<h1>Verdict: {found['status']}</h1>" in text
        for heading in ("Counts", "Rules", "Gaps", "Unsupported", "Request identity", "Tool"):
            assert f"<h2>{heading}</h2>" in text
        # AD-496: one script (the theme switch, admitted by hash) and links inside the page only.
        assert text.count("<script>") == 1 and "src=" not in text
        assert not re.findall(r'href="(?!#)', text)
        for identifier, (_, verdict) in found["frame"]["rules"].items():
            assert f"<td>{identifier}</td>" in text and f"<td>{verdict}</td>" in text


def test_report_file_options_are_explicit_and_validate_stays_refused() -> None:
    options = core_only.parse(["report", "--output", "one.html"])
    assert options.format == "html"
    code, found = run("validate", "--output", "one.html")
    assert code == 2 and found["refusal"]["kind"] == "not_on_this_development_line"
    code, found = run("report", "--format", "html")
    assert code == 2 and found["refusal"]["kind"] == "invalid_input"


@pytest.mark.parametrize("plant", ["symlink", "directory", "missing-parent"])
@pytest.mark.parametrize("form", ["json", "html"])
def test_unsafe_paths_refuse_without_writes(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    plant: str,
    form: str,
) -> None:
    root = repository(tmp_path / "project", release_core)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    victim = tmp_path / "victim"
    victim.write_text("keep")
    target = tmp_path / "report"
    if plant == "symlink":
        target.symlink_to(victim)
    elif plant == "directory":
        target.mkdir()
    else:
        target = target / "missing"
    code, found = run("report", "--root", str(root), "--output", str(target), "--format", form)
    assert code == 2 and found["refusal"]["kind"] == "io_error"
    assert victim.read_text() == "keep"
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        ["project", "victim"] + ([] if plant == "missing-parent" else ["report"])
    )


def test_existing_file_is_replaced_atomically(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = repository(tmp_path / "project", release_core)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "report.html"
    target.write_text("old bytes")
    with target.open("rb") as previous:
        code, _ = run("report", "--root", str(root), "--output", str(target))
        assert code == 0
        assert previous.read() == b"old bytes"
    assert target.read_text().startswith("<!doctype html>")


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_a_failed_write_preserves_the_old_file_and_removes_the_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    target = tmp_path / "report.html"
    target.write_bytes(b"old")

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("planted failure")

    monkeypatch.setattr(core_output.os, failure, refuse)
    with pytest.raises(OSError, match="planted failure"):
        core_output.write_output(target, b"new")
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


def test_missing_directory_handles_refuse_instead_of_using_a_weaker_write(tmp_path: Path) -> None:
    target = tmp_path / "report.html"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_output.os, "name", "nt")
        with pytest.raises(OSError, match="directory handles"):
            core_output.write_output(target, b"never written")
    assert not target.exists()


@pytest.mark.parametrize(
    "part",
    [
        None,
        {},
        {"protocol": "old", "status": "PASS", "document": "x"},
        {"protocol": "archkeel-core-html-1", "status": "UNKNOWN", "document": "x"},
        {"protocol": "archkeel-core-html-1", "status": "PASS", "document": 42},
        {"protocol": "archkeel-core-html-1", "status": "PASS", "document": "x", "extra": True},
    ],
)
def test_old_or_forged_html_parts_refuse_before_any_file_write(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    part: object,
) -> None:
    root = repository(tmp_path / "project", release_core)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    _, real = run("report", "--root", str(root))
    frame = real["frame"]
    if part is not None:
        frame["html"] = part
    monkeypatch.setattr(core_only, "exchange", lambda *args: (json.dumps(frame).encode(), 0))
    target = tmp_path / "report.html"
    code, found = run("report", "--root", str(root), "--output", str(target))
    assert code == 2 and found["refusal"]["kind"] == "core_error"
    assert "no report file was written" in found["refusal"]["message"]
    assert not target.exists()


def test_escaping_reaches_the_release_core_and_default_cli(
    tmp_path: Path,
    release_core: Path,
) -> None:
    root = repository(tmp_path / '<script>"&project', release_core)
    target = tmp_path / "report.html"
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "archkeel.cli",
            "report",
            "--root",
            str(root),
            "--output",
            str(target),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    frame = json.loads(done.stdout)["frame"]
    document = target.read_text()
    assert html.escape(json.dumps(str(root)), quote=True) in document
    assert '<script>"&project' not in document
    assert f"<h1>Verdict: {frame['status']}</h1>" in document


def test_no_accepted_frame_means_no_file(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)

    def dead(*args: object) -> None:
        raise core_only.CoreError("the core did not answer")

    monkeypatch.setattr(core_only, "exchange", dead)
    target = tmp_path / "report.html"
    code, found = run("report", "--root", str(tmp_path), "--output", str(target))
    assert code == 2 and "no report file was written" in found["refusal"]["message"]
    assert not target.exists()


def test_a_long_hostile_rule_name_is_not_truncated_or_executed(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plant = "<script>\"'&\ufffd" + "x" * 100_000
    root = repository(
        tmp_path / "project",
        release_core,
        # AD-466: `complete_requires` decides each pair; without it the pairs stay open.
        rules=(rule(plant, "complete_assignment", source="native"), *CRATE_RULES[1:2]),
    )
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "report.html"
    code, found = run("report", "--root", str(root), "--output", str(target))
    assert code == 0, found
    document = target.read_text()
    assert html.escape(plant, quote=True).replace("&#x27;", "&#39;") in document
    # AD-496: the page has its one theme script; the planted text adds none.
    assert document.count("<script>") == 1 and '<script>"' not in document


def test_an_invalid_utf8_name_cannot_publish_a_success_page(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = repository(tmp_path / "project", release_core)
    try:
        descriptor = os.open(
            os.fsencode(root) + b"/crates/app/src/<script>\xff.rs", os.O_CREAT | os.O_WRONLY, 0o600
        )
    except OSError as error:
        if error.errno == errno.EILSEQ:
            pytest.skip("this filesystem refuses invalid UTF-8 file names")
        raise
    os.close(descriptor)
    commit_tree(root)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "report.html"
    code, found = run("report", "--root", str(root), "--output", str(target))
    assert code == 2, found
    assert "<h1>Verdict: UNKNOWN</h1>" in target.read_text()
    # AD-496: the page holds one script, the theme switch. The file name adds no second one.
    assert target.read_text().count("<script") == 1


@pytest.mark.parametrize(
    "document",
    [
        "<h1>Verdict: PASS</h1>",
        "<h1>Verdict: FAIL</h1><h1>Verdict: FAIL</h1>",
        '<h1>Verdict: FAIL</h1><h2 class="other">Verdict: PASS</h2>',
        "<h1>Verdict: FAIL</h1><H1>Verdict: PASS</H1>",
        "<h1>Verdict: FAIL </h1>",
    ],
)
def test_document_verdict_mismatch_refuses_before_writing(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    document: str,
) -> None:
    root = project(tmp_path / "project", release_core, "rust", "FAIL")
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    # AD-496: a page request also asks for the topology, so the frame that the core gives holds it.
    _, real = run("report", "--root", str(root), "--topology")
    frame = real["frame"]
    assert frame["status"] == "FAIL"
    frame["html"] = {"protocol": "archkeel-core-html-1", "status": "FAIL", "document": document}
    monkeypatch.setattr(core_only, "exchange", lambda *args: (json.dumps(frame).encode(), 0))
    target = tmp_path / "report.html"
    code, found = run("report", "--root", str(root), "--output", str(target))
    assert code == 2 and found["refusal"]["kind"] == "core_error"
    assert "verdict heading" in found["refusal"]["message"]
    assert not target.exists()


@pytest.mark.parametrize("form", ["html", "json"])
def test_parent_links_are_resolved_but_the_final_link_is_refused(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    form: str,
) -> None:
    root = repository(tmp_path / "project", release_core)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    parent = tmp_path / "real"
    parent.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(parent, target_is_directory=True)
    target = alias / f"report.{form}"
    code, found = run("report", "--root", str(root), "--output", str(target), "--format", form)
    assert code == 0 and found["status"] == "PASS", found
    assert (parent / target.name).is_file()
    victim = parent / "victim"
    victim.write_text("keep")
    final = alias / "final"
    final.symlink_to(victim)
    code, found = run("report", "--root", str(root), "--output", str(final), "--format", form)
    assert code == 2 and found["refusal"]["kind"] == "io_error"
    assert "regular file" in found["refusal"]["message"]
    assert victim.read_text() == "keep" and final.is_symlink()


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("", "must name a file"),
        (".", "must name a file"),
        ("-", "standard output is not a file target; omit --output"),
    ],
)
def test_non_file_targets_refuse_before_the_core_starts(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    message: str,
) -> None:
    def no_core() -> Path:
        pytest.fail("an invalid output target must refuse before binary lookup")

    monkeypatch.setattr(core_only, "locate_core", no_core)
    code, found = run("report", "--output", target)
    assert code == 2 and found["refusal"]["kind"] == "invalid_input"
    assert message in found["refusal"]["message"]


@pytest.mark.parametrize("status", ["PASS", "FAIL"])
def test_delivery_failure_keeps_the_verdict_but_replaces_the_exit(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = project(tmp_path / "project", release_core, "rust", status)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    code, found = run("report", "--root", str(root), "--output", str(tmp_path / "missing/report"))
    assert (code, found["exit_code"], found["status"], found["frame"]["status"]) == (
        2,
        2,
        status,
        status,
    )
    assert found["refusal"]["kind"] == "io_error"
    assert "report parent directory" in found["refusal"]["message"]
    text_code = core_only.run(
        ["report", "--root", str(root), "--output", str(tmp_path / "missing/report"), "--text"]
    )
    text = capsys.readouterr().out
    assert text_code == 2 and f"report: {status}" in text and "REFUSED: io_error:" in text


def test_compact_report_has_evidence_locations_and_an_honest_tool_identity(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = project(tmp_path / "project", release_core, "rust", "FAIL")
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "report.html"
    code, found = run("report", "--root", str(root), "--output", str(target))
    assert code == 1 and found["status"] == "FAIL"
    document = target.read_text()
    # AD-496: one block for each violated place, with the path down to its file and line.
    violations = document.split('id="violations">Violations</h2>', 1)[1].split(
        "<h2>Counts</h2>", 1
    )[0]
    assert "<pre>" not in violations and 'class="rp-dos"' in violations
    assert "crates/app/Cargo.toml" in violations and "Evidence path" in violations
    assert "Core code digest" in document and found["core"]["code_digest"] in document
    assert "&quot;version&quot;" not in document and "0.0.0" not in document


def test_a_real_rust_pass_writes_one_pass_heading_with_exit_zero(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = repository(tmp_path / "project", release_core)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "report.html"
    code, found = run("report", "--root", str(root), "--output", str(target))
    assert (code, found["status"], found["exit_code"]) == (0, "PASS", 0)
    assert target.read_text().count("<h1>Verdict: PASS</h1>") == 1
    assert all(row[1] == "PASS" for row in found["frame"]["rules"].values())


def test_native_static_page_stays_below_the_review_size_budget(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    frozen_root: Path,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "native.html"
    code, found = run(
        "report",
        "--root",
        str(frozen_root),
        "--config",
        "native/archkeel.toml",
        "--output",
        str(target),
    )
    assert code == 1 and found["status"] == "FAIL", found
    assert target.stat().st_size < 600_000


def test_tool_identity_does_not_claim_the_crate_version_is_the_package_version(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = repository(tmp_path / "project", release_core)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "report.html"
    code, found = run("report", "--root", str(root), "--output", str(target))
    assert code == 0
    tool = target.read_text().split("<h2>Tool</h2>", 1)[1]
    assert "version" not in tool and "0.0.0" not in tool
    assert "Core code digest" in tool and found["core"]["code_digest"] in tool
