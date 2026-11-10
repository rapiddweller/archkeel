# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-344: only a producer that the host trusts can give PASS; a configured collector cannot."""

import json
import sys
from pathlib import Path

import pytest
from collector_pin import pin_of
from test_onboarding import _repository

from archkeel.analyzer.process import ProcessCollector
from archkeel.check.ports import ProducerKind
from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from archkeel.ir.model import RunResult

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
    assert any("does not match the pinned digest" in item.unknown_claim for item in result.diagnostics)


def test_the_host_python_collector_and_a_configured_one_are_told_apart() -> None:
    assert observer_for("python").producer is ProducerKind.PYTHON
    assert observer_for("python", collector_argv=ARGV).producer is ProducerKind.EXTERNAL


@pytest.mark.parametrize("value", ["", "sha256:", "sha256:" + "A" * 64, "md5:" + "0" * 32])
def test_a_pin_must_be_sha256_and_64_lowercase_digits(value: str) -> None:
    with pytest.raises(ValueError, match="sha256"):
        ProcessCollector(ARGV, pinned_digest=value)
