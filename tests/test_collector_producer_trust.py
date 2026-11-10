# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-344: only a producer that the host trusts can give PASS; a configured collector cannot."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from collector_pin import pin_of
from test_onboarding import _repository

from archkeel.analyzer.pin import PinError, pinned_path
from archkeel.analyzer.process import ProcessCollector
from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from archkeel.ir.model import RunResult
from archkeel.ir.state_facts import ProducerKind

ROOT = Path(__file__).parents[1]
ARGV = (sys.executable, "-I", "-B", "-m", "archkeel.analyzer.python.entry")
CAP = "An external collector cannot prove a rule."


def _configure(root: Path, argv: tuple[str, ...] | None) -> None:
    if argv is not None:
        with (root / "archkeel.toml").open("a") as stream:
            stream.write(f"collector_argv = {json.dumps(argv)}\n")


def _report(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, object]]:
    capsys.readouterr()
    code = main(["report", "--root", str(root), "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_the_bundled_python_collector_still_gives_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path, packages=("sample",))
    assert main(["init", "--root", str(root), "--json"]) == 0
    code, result = _report(root, capsys)
    assert (code, result["observation_complete"]) == (0, "PASS")


def test_a_configured_collector_gives_at_most_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path, packages=("sample",))
    assert main(["init", "--root", str(root), "--json"]) == 0
    _configure(root, ARGV)
    code, result = _report(root, capsys)
    assert code == 2
    assert result["declared_rules"] == "UNKNOWN"
    assert result["observation_complete"] == "UNKNOWN"
    claims = [item["unknown_claim"] for item in result["diagnostics"]]  # type: ignore[attr-defined]
    assert any(CAP in claim and "producer: external" in claim for claim in claims), claims
    remedies = [item["remedy"] for item in result["diagnostics"]]  # type: ignore[attr-defined]
    assert any("pin the external collector by digest" in remedy for remedy in remedies), remedies


def _pinned_report(root: Path, digest: str) -> RunResult:
    config = load_config(root)
    observer = observer_for(config.language, collector_argv=ARGV, pinned_digest=digest)
    assert observer.producer is ProducerKind.PINNED
    result, _ = run_report(root, config=config, analyzer=observer)
    return result


def test_a_pinned_collector_gives_pass(tmp_path: Path) -> None:
    root = _repository(tmp_path, packages=("sample",))
    assert main(["init", "--root", str(root), "--json"]) == 0
    result = _pinned_report(root, pin_of(sys.executable))
    assert (result.exit_code, str(result.observation_complete)) == (0, "PASS")


def test_a_pinned_collector_with_another_file_digest_is_refused(tmp_path: Path) -> None:
    root = _repository(tmp_path, packages=("sample",))
    assert main(["init", "--root", str(root), "--json"]) == 0
    result = _pinned_report(root, "sha256:" + "0" * 64)
    assert result.exit_code == 2
    assert str(result.observation_complete) != "PASS"
    assert any(
        "does not match the pinned digest" in item.unknown_claim for item in result.diagnostics
    )


def test_the_host_python_collector_and_a_configured_one_are_told_apart() -> None:
    assert observer_for("python").producer is ProducerKind.PYTHON
    assert observer_for("python", collector_argv=ARGV).producer is ProducerKind.EXTERNAL


@pytest.mark.parametrize("value", ["", "sha256:", "sha256:" + "A" * 64, "md5:" + "0" * 32])
def test_a_pin_must_be_sha256_and_64_lowercase_digits(value: str) -> None:
    with pytest.raises(ValueError, match="sha256"):
        ProcessCollector(ARGV, pinned_digest=value)


def test_an_external_collector_that_reports_a_violation_still_gives_fail(tmp_path: Path) -> None:
    """AD-344: the cap stops PASS. A reported violation is not hidden and is not UNKNOWN."""
    import false_pass_support as support

    root = support.copy_repository(ROOT / "fixtures/F-architecture", tmp_path)
    entities = root / "shop/model/entities.py"
    entities.write_text(
        "from shop.cli import main as _forbidden  # noqa: F401\n" + entities.read_text()
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "violate"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    config = load_config(root)
    for argv in (None, ARGV):
        observer = observer_for(config.language, collector_argv=argv)
        result, _ = run_report(root, config=config, analyzer=observer)
        assert str(result.declared_rules) == "FAIL", argv
        assert any(str(item.status) == "FAIL" for item in result.rule_assessments or ()), argv


def test_a_pinned_collector_is_resolved_once_and_never_taken_from_the_repository(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    outside = tmp_path / "bin"
    repository.mkdir()
    outside.mkdir()
    (repository / "tool").write_text("#!/bin/sh\necho planted\n")
    (outside / "tool").write_text("#!/bin/sh\necho trusted\n")
    for tool in (repository / "tool", outside / "tool"):
        tool.chmod(0o755)
    digest = pin_of(str(outside / "tool"))
    root = str(repository)
    # A bare name comes from the search path only: the planted file in the root is not used.
    assert pinned_path("tool", root, str(outside), digest) == str(outside / "tool")
    with pytest.raises(PinError, match="does not match the pinned digest"):
        pinned_path("tool", root, str(outside), pin_of(str(repository / "tool")))
    # A file inside the scanned repository is refused, even with its own digest.
    with pytest.raises(PinError, match="inside the scanned repository"):
        pinned_path("./tool", root, str(outside), pin_of(str(repository / "tool")))
    # A relative search path entry cannot say where the file is.
    with pytest.raises(PinError, match="could not execute"):
        pinned_path("tool", root, ".", digest)


def _saved_report(
    root: Path, snapshot: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    capsys.readouterr()
    code = main(["report", "--input", str(snapshot), "--json"])
    return code, json.loads(capsys.readouterr().out)["declared_rules"]


def test_a_saved_external_scan_cannot_be_laundered_into_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-344: report --input reads the producer kind that the host recorded."""
    root = _repository(tmp_path, packages=("sample",))
    assert main(["init", "--root", str(root), "--json"]) == 0
    snapshots = {}
    for name, argv in (("python", None), ("external", ARGV)):
        saved = tmp_path / f"{name}.json"
        with (root / "archkeel.toml").open() as stream:
            original = stream.read()
        _configure(root, argv)
        capsys.readouterr()
        main(["report", "--root", str(root), "--output", str(saved), "--json"])
        capsys.readouterr()
        (root / "archkeel.toml").write_text(original)
        snapshots[name] = saved
    recorded = {k: json.loads(v.read_bytes()).get("producer_kind") for k, v in snapshots.items()}
    assert recorded == {"python": "python", "external": "external"}
    assert json.loads(snapshots["external"].read_bytes())["schema_version"] == "2.10.0"
    _, python_rules = _saved_report(root, snapshots["python"], capsys)
    code, external_rules = _saved_report(root, snapshots["external"], capsys)
    assert python_rules != "UNKNOWN"
    assert (code, external_rules) == (2, "UNKNOWN")


def test_an_older_saved_scan_without_the_field_keeps_its_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path, packages=("sample",))
    assert main(["init", "--root", str(root), "--json"]) == 0
    saved = tmp_path / "now.json"
    capsys.readouterr()
    main(["report", "--root", str(root), "--output", str(saved), "--json"])
    capsys.readouterr()
    raw = json.loads(saved.read_bytes())
    del raw["producer_kind"]
    raw["schema_version"] = "2.9.0"
    old = tmp_path / "old.json"
    old.write_text(json.dumps(raw))
    now = _saved_report(root, saved, capsys)
    assert _saved_report(root, old, capsys) == now
    raw["producer_kind"] = "external"
    marked = tmp_path / "marked.json"
    marked.write_text(json.dumps(raw))
    assert _saved_report(root, marked, capsys) == (2, "UNKNOWN")
