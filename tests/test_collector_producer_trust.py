# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-344: only a producer that the host trusts can give PASS; a configured collector cannot."""

import json
import sys
from pathlib import Path

import pytest
from collector_pin import pin_of

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


def _pinned_report(root: Path, digest: str) -> RunResult:
    config = load_config(root)
    observer = observer_for(config.language, collector_argv=ARGV, pinned_digest=digest)
    assert observer.producer is ProducerKind.PINNED
    result, _ = run_report(root, config=config, analyzer=observer)
    return result


@pytest.mark.parametrize("value", ["", "sha256:", "sha256:" + "A" * 64, "md5:" + "0" * 32])
def test_a_pin_must_be_sha256_and_64_lowercase_digits(value: str) -> None:
    with pytest.raises(ValueError, match="sha256"):
        ProcessCollector(ARGV, pinned_digest=value)


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


def _saved_scan(root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict:
    capsys.readouterr()
    saved = tmp_path / "now.json"
    main(["report", "--root", str(root), "--output", str(saved), "--json"])
    capsys.readouterr()
    return json.loads(saved.read_bytes())


def _read_saved(raw: dict, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict:
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(raw))
    capsys.readouterr()
    code = main(["report", "--input", str(path), "--json"])
    result = json.loads(capsys.readouterr().out)
    assert code == 2, result
    return result


def test_the_native_self_check_names_no_collector() -> None:
    """AD-344: `make self-validate-native` runs the bundled lookup, never an external argv."""
    root = Path(__file__).resolve().parents[1]
    assert load_config(root, "native/archkeel.toml").collector_argv is None
