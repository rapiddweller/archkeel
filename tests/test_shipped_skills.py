# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A shipped agent skill teaches only what this development line serves (#880).

The skills are text that an agent obeys. A skill that names a refused command as if it worked, or
a relative link that breaks outside the repository, sends the agent into an exit 2 or a dead end.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from archkeel.cli.core_only import NotOnThisLine, parse

ROOT = Path(__file__).parents[1]
SKILLS = sorted(ROOT.glob("skills/*/SKILL.md"))
SERVED = {"validate", "report", "skill"}
REFUSED = {"check", "init", "explore", "guide", "story", "view", "studio"}
SITE = "https://github.com/rapiddweller/archkeel/"
LINK = re.compile(r"\]\(([^)\s]+)\)")
COMMAND = re.compile(r"\barchkeel ([a-z][a-z-]*)")


def _name(path: Path) -> str:
    return path.parent.name


def test_the_shipped_skills_are_found() -> None:
    assert {_name(path) for path in SKILLS} == {"archkeel", "explore", "explain-flow"}


@pytest.mark.parametrize("path", SKILLS, ids=_name)
def test_a_skill_names_only_commands_that_the_shell_serves(path: Path) -> None:
    named = set(COMMAND.findall(path.read_text(encoding="utf-8")))
    assert named <= SERVED, f"{path.name} teaches {sorted(named - SERVED)} as if it worked"


@pytest.mark.parametrize("path", SKILLS, ids=_name)
def test_each_command_line_of_a_skill_is_accepted_by_the_shell(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = re.findall(r"`archkeel ([^`]+)`", text)
    assert lines or path.parent.name != "archkeel"
    for line in lines:
        argv = shlex.split(re.sub(r"<[^>]+>|\[[^\]]*\]|\{[^}]*\}", "x", line))
        try:
            parse(argv)
        except NotOnThisLine as error:
            pytest.fail(f"{path.name}: `archkeel {line}` is refused: {error}")
        except ValueError:
            # A prefix such as `skill install claude` needs its own arguments; none is unknown.
            assert argv[0] in SERVED, line


@pytest.mark.parametrize("path", SKILLS, ids=_name)
def test_each_link_of_a_skill_is_absolute_and_names_a_file_on_main(path: Path) -> None:
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        assert target.startswith(SITE), f"{path.name}: relative or foreign link {target}"
        kind, _, rest = target.removeprefix(SITE).partition("/")
        ref, _, name = rest.partition("/")
        if ref == "main":
            assert (ROOT / name.split("#")[0]).exists(), f"{path.name}: {target} is not on main"
        else:
            assert kind in {"blob", "tree"} and ref, target


def test_the_refused_commands_are_the_ones_of_the_shell() -> None:
    for name in sorted(REFUSED):
        with pytest.raises(NotOnThisLine):
            parse([name])
