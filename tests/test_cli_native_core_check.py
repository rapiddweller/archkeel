# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-399: `archkeel check --native-core` takes its rule verdicts from the Rust core, stage 1.

Each test builds the M -> B -> E -> H protocol of `check` on the Cargo workspace of
`rust_repository` with the bundled Rust collector and the core of one build (the fixtures of
`test_cli_native_core`). The core reads the candidate reply, the base reply and the contract at
the baseline commit; the shell compares the run status, the rule rows and the exit code.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import zlib
from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import rust_repository as rr
from graph_report_support import commit_tree
from test_cli_native_core import (
    PASSING,
    SUFFIX,
    _captured,
    built,
    core_notes,
    diagnostics,
    fake_core,
    frame,
    install,
    posix,
    repository,
)
from test_cli_native_core_trust import _script

from archkeel.cli import main, native_core
from archkeel.cli.config import parse_config
from archkeel.cli.core_frame import GapKind, gap_kind
from archkeel.ir.model import RunResult
from fixtures import demo_catalog_check
from fixtures.demo_catalog_support import CheckScenario

__all__ = ["built", "install"]  # the fixtures of the core and the Rust collector of one build

_COMMENT = {"crates/app/src/lib.rs": rr.APP_SOURCE + "// A comment changes no record.\n"}
_NO_REQUIRES = (rr.component("base", "base_crate"), rr.component("app", "app"))


def protocol(
    tmp_path: Path,
    install: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: CheckScenario = "empty_declaration",
    files: dict[str, str] = _COMMENT,
    **changes: Any,
) -> tuple[Path, list[str]]:
    """The root and the `check` arguments of one protocol run; the default candidate only adds a
    comment and declares no change."""
    source = repository(tmp_path / "source", install, **changes)
    shutil.rmtree(source / ".git")
    config = parse_config((source / "archkeel.toml").read_bytes())
    monkeypatch.setattr(demo_catalog_check, "FIXTURE_DIR", source)
    monkeypatch.setattr(demo_catalog_check, "CONFIG", config)
    work = tmp_path / "protocol"
    prepared = demo_catalog_check.build_and_run_check(work, files, scenario)
    provenance = prepared.provenance
    assert provenance is not None, prepared.diagnostics
    root = work / "root"
    arguments = ["check", "--root", str(root), "--baseline", provenance.baseline]
    arguments += ["--expectation-commit", provenance.expectation, "--head", provenance.head]
    arguments += ["--expected", "expectation.json", "--expected-digest"]
    arguments += [provenance.expected_digest, "--branch", "candidate", "--accepted-branch", "main"]
    arguments += ["--host-records", str(work / "host-records.json"), "--json"]
    return root, arguments


def check(arguments: list[str], *flags: str) -> tuple[int, dict[str, Any]]:
    with _captured() as output:
        code = main([*arguments, *flags])
    return code, json.loads(output.getvalue())


def without_notes(result: dict[str, Any]) -> dict[str, Any]:
    kept = {key: value for key, value in result.items() if key != "notes"}
    notes = [note for note in result.get("notes") or () if note["subject"] != "native_core"]
    return {**kept, "notes": notes} if notes else kept


def _git(root: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", *arguments], cwd=root)


def _head_of(reply: dict[str, str]) -> str:
    """The commit that a collector reply of the request names."""
    facts = json.loads(zlib.decompress(bytes.fromhex(reply["hex"])))["facts"]
    return str(facts["source"]["git_head"])


# --- The switch -------------------------------------------------------------------------------


@posix
def test_the_switch_off_starts_no_core_and_changes_no_byte(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, arguments = protocol(tmp_path, install, monkeypatch)
    request = fake_core(install, frame(PASSING, "PASS"))
    code, result = check(arguments)
    monkeypatch.setenv(native_core.SWITCH_VARIABLE, "0")
    assert check(arguments) == (code, result)
    assert (code, result["declared_rules"]) == (0, "PASS")
    # The output of main: no rule rows and no core note; the core never started.
    assert result.get("rule_assessments") is None
    assert core_notes(result) == []
    assert not request.exists()


def test_another_value_of_the_variable_is_refused_by_check(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review N3 of #1094: before, `check` ignored the variable without a note."""
    _, arguments = protocol(tmp_path, install, monkeypatch)
    monkeypatch.setenv(native_core.SWITCH_VARIABLE, "yes")
    code, result = check(arguments)
    assert code == 2
    assert "ARCHKEEL_NATIVE_CORE must be 0 or 1" in diagnostics(result)


# --- The real core ------------------------------------------------------------------------------


def test_the_core_decides_a_pass_check(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, arguments = protocol(tmp_path, install, monkeypatch)
    off = check(arguments)
    code, result = check(arguments, "--native-core")
    assert (code, result["declared_rules"]) == (0, "PASS")
    assert result["rule_assessments"] is None  # the result of check has no rule rows
    [note] = core_notes(result)
    assert note.startswith("The core decides every rule of this run (archkeel-core ")
    assert "the Git order and the host order are the verdicts of the Python engine" in note
    assert without_notes(result) == without_notes(off[1])
    assert off[0] == code


def test_the_core_decides_a_fail_check_with_exit_1(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, arguments = protocol(tmp_path, install, monkeypatch, components=_NO_REQUIRES)
    off = check(arguments)
    code, result = check(arguments, "--native-core")
    assert (code, result["declared_rules"]) == (1, "FAIL")
    assert result["rule_assessments"] is None
    assert core_notes(result)[0].startswith("The core decides every rule")
    assert without_notes(result) == without_notes(off[1])
    assert off[0] == 1


def test_an_expectation_failure_keeps_exit_1_and_the_core_decides_the_rules(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The host published the expectation after the candidate: Python fails the run (exit 1)
    with each rule PASS. The exit code reads the failures of Python, never only the core."""
    _, arguments = protocol(tmp_path, install, monkeypatch, "published_after_candidate")
    off = check(arguments)
    code, result = check(arguments, "--native-core")
    assert (code, off[0], result["declared_rules"]) == (1, 1, "PASS")
    assert result["host_order"] == "FAIL"
    assert core_notes(result)[0].startswith("The core decides every rule")
    assert without_notes(result) == without_notes(off[1])


def test_the_core_decides_a_candidate_that_adds_a_violation(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rows are the rows of the candidate, not of the accepted commit: the candidate makes
    the base crate import the app crate."""
    cycle = {
        "crates/base/Cargo.toml": rr.BASE + '[dependencies]\napp = { path = "../app" }\n',
        "crates/base/src/lib.rs": "pub fn make() { app::run(); }\n",
    }
    _, arguments = protocol(tmp_path, install, monkeypatch, "ordered", cycle)
    off = check(arguments)
    code, result = check(arguments, "--native-core")
    assert (code, off[0], result["declared_rules"]) == (1, 1, "FAIL"), diagnostics(result)
    assert result["rule_assessments"] is None
    assert core_notes(result)[0].startswith("The core decides every rule")
    assert without_notes(result) == without_notes(off[1])


@posix
def test_the_request_carries_the_base_reply_and_the_contract_of_the_baseline_commit(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, arguments = protocol(tmp_path, install, monkeypatch)
    request = fake_core(install, frame(PASSING, "PASS"))
    check(arguments, "--native-core")
    sent = json.loads(request.read_bytes())
    assert sent["protocol"] == "archkeel-core-check-2"
    assert "baseline" not in sent
    baseline = arguments[arguments.index("--baseline") + 1]
    contract = _git(root, "show", f"{baseline}:architecture-contract.json")
    assert bytes.fromhex(sent["contract"]["hex"]) == contract
    # The base is the reply of the accepted commit, the reply is the reply of the candidate.
    head = arguments[arguments.index("--head") + 1]
    accepted = _git(root, "rev-parse", f"{baseline}^").decode().strip()
    assert (_head_of(sent["base"]["reply"]), _head_of(sent["reply"])) == (accepted, head)


def test_the_contract_of_the_working_tree_changes_nothing(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The core reads the contract at the baseline commit: a working-tree contract without the
    requires of `app` would make REQUIRES FAIL in the core and differ from Python (exit 2)."""
    root, arguments = protocol(tmp_path, install, monkeypatch)
    contract = json.loads((root / "architecture-contract.json").read_text())
    contract["components"] = list(_NO_REQUIRES)
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    code, result = check(arguments, "--native-core")
    assert (code, result["declared_rules"]) == (0, "PASS"), diagnostics(result)
    assert result["rule_assessments"] is None  # the result of check has no rule rows
    assert core_notes(result)[0].startswith("The core decides every rule")


@posix
def test_a_forged_base_reply_through_a_replaced_collector_is_a_named_error(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The collector is a script that prints a forged reply; its `.sha256` is stale. The base is
    the first reply of `check`: the shell refuses the script before it starts it."""
    _, arguments = protocol(tmp_path, install, monkeypatch)
    marker = tmp_path / "ran"
    forged = f"#!{{python}}\nopen({str(marker)!r}, 'a').write('ran')\nprint('forged')\n"
    _script(install / f"archkeel-rust-collector{SUFFIX}", forged)
    code, result = check(arguments, "--native-core")
    assert code == 2
    assert "a bundled collector is not verified" in diagnostics(result)
    assert result["declared_rules"] == "UNKNOWN"
    assert not marker.exists()


@pytest.mark.parametrize(
    ("change", "count"), [(list.pop, 1), (lambda found: found.append(found[0]), 3)]
)
def test_the_core_reads_exactly_two_replies(
    install: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: Callable[[list[bytes]], object],
    count: int,
) -> None:
    _, arguments = protocol(tmp_path, install, monkeypatch)
    original = native_core.NativeCore.decide_check

    def changed(self: native_core.NativeCore, *values: Any) -> RunResult:
        change(self.replies)
        return original(self, *values)

    off = check(arguments)
    monkeypatch.setattr(native_core.NativeCore, "decide_check", changed)
    code, result = check(arguments, "--native-core")
    assert code == off[0] == 0
    [note] = core_notes(result)
    assert f"the run has {count} collector replies, and the core reads 2" in note
    assert result.get("rule_assessments") is None
    assert without_notes(result) == without_notes(off[1])


def test_a_difference_in_the_exit_code_alone_is_a_named_error(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, arguments = protocol(tmp_path, install, monkeypatch)
    from archkeel.cli import legacy_bindings

    original = legacy_bindings.run_check

    def exits_one(*values: Any, **options: Any) -> RunResult:
        result = original(*values, **options)
        assert (result.exit_code, result.failures) == (0, ())
        return replace(result, exit_code=1)

    monkeypatch.setattr(legacy_bindings, "run_check", exits_one)
    code, result = check(arguments, "--native-core")
    assert code == 2
    assert "the exit code: core 0, Python 1" in diagnostics(result)


@posix
def test_a_verdict_difference_in_check_is_a_named_error(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, arguments = protocol(tmp_path, install, monkeypatch)
    fake_core(install, frame({**PASSING, "REQUIRES": "FAIL"}, "FAIL", violations={"REQUIRES": 1}))
    code, result = check(arguments, "--native-core")
    assert code == 2
    assert "the core and the Python engine differ" in diagnostics(result)


@posix
def test_a_frame_that_names_a_part_falls_back_without_rule_rows(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, arguments = protocol(tmp_path, install, monkeypatch)
    reason = "the base reply: producer not verified: a stale build"
    named = frame({}, "UNKNOWN", unsupported=reason)
    fake_core(install, named, exit_code=3)
    off = check(arguments)
    code, result = check(arguments, "--native-core")
    assert code == off[0] == 0
    [note] = core_notes(result)
    assert note.startswith("The core did not decide this run") and reason in note
    assert result.get("rule_assessments") is None
    assert without_notes(result) == without_notes(off[1])
    assert gap_kind(reason) is GapKind.BASE


def test_the_shell_reads_a_committed_contract_only_as_a_regular_blob(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.json").write_text("{}")
    os.symlink("a.json", root / "link.json")
    commit = commit_tree(root)
    assert native_core.read_committed(root, commit, "a.json", 10) == ("a.json", b"{}")
    assert native_core.read_committed(root, commit, "./a.json", 10) == ("a.json", b"{}")
    for path in ("link.json", "missing.json", "../a.json", "/a.json"):
        assert native_core.read_committed(root, commit, path, 10) is None, path
    with pytest.raises(native_core.OverBudget):
        native_core.read_committed(root, commit, "a.json", 1)


def test_the_check_parser_has_the_switch() -> None:
    output = io.StringIO()
    with pytest.raises(SystemExit), redirect_stdout(output):
        main(["check", "--help"])
    assert "--native-core" in output.getvalue()
