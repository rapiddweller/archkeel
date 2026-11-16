# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shell loads no Python decision package: the three packages do not exist (AD-432)."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from archkeel.cli import core_arguments, core_only
from archkeel.cli.core_frame import RefusalKind, Status

ROOT = Path(__file__).resolve().parents[1]
GUARD = """
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "archkeel.ir" or fullname.startswith("archkeel.ir."):
            raise AssertionError("Python IR imported: " + fullname)
        if fullname == "archkeel.check" or fullname.startswith("archkeel.check."):
            raise AssertionError("Python checker imported: " + fullname)
        if fullname == "archkeel.analyzer" or fullname.startswith("archkeel.analyzer."):
            raise AssertionError("Python collector imported: " + fullname)
sys.meta_path.insert(0, Guard())
from archkeel.cli import main
code = main(sys.argv[1:])
for name in sys.modules:
    assert not any(name == package or name.startswith(package + ".")
                   for package in ("archkeel.ir", "archkeel.check", "archkeel.analyzer")), (
        "forbidden module after command: " + name)
raise SystemExit(code)
"""


REFUSED = ("check", "explore", "guide", "story", "view", "studio")


def shell(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", GUARD, *arguments],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("package", ["archkeel.ir", "archkeel.check", "archkeel.analyzer"])
def test_a_python_decision_package_cannot_be_imported(package: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(package)
    assert not (ROOT / "src" / package.replace(".", "/")).exists()


@pytest.mark.parametrize("switch", [(), ("--core-only",)], ids=["default", "core-only"])
@pytest.mark.parametrize("command", ["validate", "report", *REFUSED])
def test_no_command_imports_a_python_decision_package(
    command: str, switch: tuple[str, ...], tmp_path: Path
) -> None:
    done = shell(command, *switch, "--root", str(tmp_path), "--json")
    assert done.returncode == 2, done.stderr
    assert "Traceback" not in done.stderr
    assert '"status": "UNKNOWN"' in done.stdout


@pytest.mark.parametrize("value", ["1", "false"])
def test_a_switch_with_a_value_refuses_without_python_decision_imports(value: str) -> None:
    done = shell("validate", f"--core-only={value}", "--json")
    assert done.returncode == 2, done.stderr
    assert "Traceback" not in done.stderr
    assert '"kind": "invalid_input"' in done.stdout


@pytest.mark.parametrize("extra", [(), ("--help",), ("--output", "x.html"), ("--core-only",)])
@pytest.mark.parametrize("command", REFUSED)
def test_a_command_of_the_release_line_stays_registered_and_refuses_with_its_kind(
    command: str, extra: tuple[str, ...]
) -> None:
    """AD-432: the command is known, so the refusal is not `invalid_input`. It names the release
    that has the command, or states that no release has it, and the tracking issue. Nothing runs
    and nothing reports success."""
    done = shell(command, *extra, "--json")
    assert done.returncode == 2
    assert done.stderr == ""
    document = json.loads(done.stdout)
    assert document["status"] == "UNKNOWN" and document["exit_code"] == 2
    assert document["refusal"]["kind"] == "not_on_this_development_line"
    message = document["refusal"]["message"]
    assert message.startswith(f"{command} is not available on this development line")
    # Release 4.0.1 has only `check` of the refused commands.
    remedy = "use release 4.0.1" if command == "check" else "no release has it"
    assert remedy in message and "#880" in message
    assert ("use release" in message) == (command == "check")
    text = shell(command, *extra, "--text")
    assert text.returncode == 2 and text.stderr == ""
    assert text.stdout == f"REFUSED: not_on_this_development_line: {message}\n"


def test_check_names_each_check_that_is_not_ported() -> None:
    done = shell("check", "--json")
    message = json.loads(done.stdout)["refusal"]["message"]
    for name in ("ratchets", "guardrails", "selected changes", "Git order", "host publication"):
        assert name in message
    assert "#1103" in message


@pytest.mark.parametrize("kind", list(core_arguments.CheckKind))
@pytest.mark.parametrize(
    "flags",
    [
        [],
        [
            "--baseline",
            "b",
            "--expectation-commit",
            "e",
            "--head",
            "h",
            "--expected",
            "expectation.json",
            "--expected-digest",
            "digest",
            "--branch",
            "origin/feature",
            "--accepted-branch",
            "origin/main",
            "--host-records",
            "host.json",
        ],
    ],
)
def test_each_mandatory_merge_check_is_named_without_a_scan(
    kind: core_arguments.CheckKind,
    flags: list[str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_binary() -> Path:
        pytest.fail("a refused check must not start the core")

    monkeypatch.setattr(core_only, "locate_core", no_binary)
    assert core_only.run(["check", "--json", *flags]) == 2
    result = json.loads(capsys.readouterr().out)
    assert kind in result["refusal"]["message"] and "#1103" in result["refusal"]["message"]


@pytest.mark.parametrize(
    ("command", "option"),
    [
        (command, option)
        for command in ("validate", "report")
        for option in sorted(core_arguments.REMOVED_OPTIONS)
        if (command, option) != ("report", "--output")
    ],
)
def test_each_option_of_the_release_line_refuses_by_name(
    command: str,
    option: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_binary() -> Path:
        pytest.fail("a refused option must not start the core")

    monkeypatch.setattr(core_only, "locate_core", no_binary)
    for flags in ([option], [option, "value"], [f"{option}=value"]):
        assert core_only.run([command, "--json", *flags]) == 2
        refusal = json.loads(capsys.readouterr().out)["refusal"]
        assert refusal["kind"] == RefusalKind.NOT_ON_THIS_LINE
        assert f"{command} {option} is not available" in refusal["message"]
        released = option not in core_arguments.UNRELEASED_OPTIONS
        assert ("use release 4.0.1" in refusal["message"]) == released
        assert ("no release has it" in refusal["message"]) != released
        assert "#880" in refusal["message"]


@pytest.mark.parametrize(
    "arguments",
    [["nothing"], ["validate", "--unknown"], ["validate", "extra"], ["--json", "validate"]],
)
def test_an_unknown_command_or_argument_is_invalid_input(
    arguments: list[str], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_binary() -> Path:
        pytest.fail("an invalid command line must not start the core")

    monkeypatch.setattr(core_only, "locate_core", no_binary)
    assert core_only.run([*arguments, "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == Status.UNKNOWN
    assert result["refusal"]["kind"] == RefusalKind.INVALID_INPUT
