# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each command prints its own help (#1323), and no documented flag refuses (#1328)."""

import json
import re

import pytest

from archkeel.cli import core_arguments, core_exit, core_only
from archkeel.cli.core_frame import CoreCommand


@pytest.mark.parametrize("command", [command.value for command in CoreCommand])
def test_each_command_prints_its_own_help_as_text(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert core_only.run([command, "--help"]) == 0
    text = capsys.readouterr().out
    assert text.startswith(f"usage: archkeel {command}"), text
    assert not text.lstrip().startswith("{")


@pytest.mark.parametrize("command", ["validate", "report"])
def test_the_help_of_a_served_command_has_options_the_exit_table_and_two_examples(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    core_only.run([command, "--help"])
    text = capsys.readouterr().out
    for line in core_exit.table_lines():
        assert line in text
    assert text.count("\n  archkeel ") == {"validate": 3, "report": 2}[command]
    assert "examples:" in text
    assert "--all" in text and "--verbose" in text and "Output:" in text


def test_the_tool_help_lists_the_commands_and_the_exit_table(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert core_only.run(["--help"]) == 0
    text = capsys.readouterr().out
    assert all(f"  {name}" in text for name in ("validate", "report", "skill"))
    assert "  2  UNKNOWN" in text and "#" not in text


def test_the_help_documents_only_flags_that_work() -> None:
    """#1328: a flag in a help text is a flag that the parser accepts."""
    values = {
        "--root": "r", "--config": "c.toml", "--output": "o.html", "--format": "json",
        "--baseline": "b.json", "--write-baseline": "w.json", "--timings": "t.json",
    }  # fmt: skip
    for command in (CoreCommand.VALIDATE, CoreCommand.REPORT):
        text = core_only.help_for(command)
        documented = set(re.findall(r"^\s{2}(--[a-z-]+)", text, flags=re.M))
        assert documented and "--only" not in text and "--input" not in text
        for flag in documented:
            args = [command.value, flag, *([values[flag]] if flag in values else [])]
            if flag == "--format":
                args += ["--output", "o.json"]
            if flag == "--part-of":
                args += ["s.json", "--output", "o.html"]
            if flag == "--system-href":
                args += ["index.html", "--part-of", "s.json", "--output", "o.html"]
            core_arguments.parse(args)


def test_topology_help_says_what_it_changes() -> None:
    text = core_only.help_for(CoreCommand.REPORT)
    assert "printed result" in text and "HTML page always draws the architecture" in text


@pytest.mark.parametrize("flag", ["--only", "--input"])
def test_a_flag_that_does_not_exist_yet_refuses_in_plain_words(
    flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert core_only.run(["report", flag, "x", "--text"]) == 2
    text = capsys.readouterr().out
    assert f"report {flag} is not available in ArchKeel 5.0 yet" in text
    assert "development line" not in text
    problem = next(line for line in text.splitlines() if line.startswith("Problem: "))
    assert "use archkeel report --json" in problem and "release" not in problem
    assert "#" not in text


def test_skill_install_without_an_agent_names_the_fix(capsys: pytest.CaptureFixture[str]) -> None:
    assert core_only.run(["skill", "install", "--text"]) == 2
    text = capsys.readouterr().out
    assert "archkeel skill install claude" in text and "argument" in text
    assert "usage:" not in text and "Traceback" not in text
    assert json.dumps(text)  # plain text, not a machine line
