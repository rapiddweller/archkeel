# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A report file keeps the verdict of the accepted core frame (AD-440)."""

from __future__ import annotations

import errno
import html
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from core_support import run
from corpus_support import commit_tree
from rust_repository import component, repository, rule

from archkeel.cli import core_only, core_output


def project(root: Path, binary: Path, profile: str, status: str) -> Path:
    parts = (component("base", "base_crate"), component("app", "app", ("base",)))
    if status == "FAIL":
        parts = (component("base", "base_crate"), component("app", "app"))
    rules = None
    if status == "UNKNOWN":
        rules = (rule("UNPORTED", "symbol_placement", source="native"),)
    root = repository(root, binary, components=parts, **({"rules": rules} if rules else {}))
    if profile == "typescript":
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
        for heading in (
            "Counts",
            "Rules",
            "Violations",
            "Gaps",
            "Unsupported",
            "Request identity",
            "Tool",
        ):
            assert f"<h2>{heading}</h2>" in text
        assert "<script" not in text and "src=" not in text and "href=" not in text
        for identifier, (_, verdict) in found["frame"]["rules"].items():
            assert f"<td>{identifier}</td>" in text and f"<td>{verdict}</td>" in text


def test_report_file_options_are_explicit_and_validate_stays_refused() -> None:
    options = core_only.parse(["report", "--output", "one.html"])
    assert options.format == "html"
    code, found = run("validate", "--output", "one.html")
    assert code == 2 and found["refusal"]["kind"] == "not_on_this_development_line"
    code, found = run("report", "--format", "html")
    assert code == 2 and found["refusal"]["kind"] == "invalid_input"


@pytest.mark.parametrize("plant", ["symlink", "parent-symlink", "directory", "missing-parent"])
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
    elif plant == "parent-symlink":
        target.symlink_to(tmp_path, target_is_directory=True)
        target = target / "victim"
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
        rules=(rule(plant, "complete_assignment", source="native"),),
    )
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "report.html"
    code, found = run("report", "--root", str(root), "--output", str(target))
    assert code == 0, found
    document = target.read_text()
    assert html.escape(plant, quote=True).replace("&#x27;", "&#39;") in document
    assert "<script>" not in document


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
    assert "<script>" not in target.read_text()
