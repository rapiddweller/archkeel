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

from archkeel.cli.core_arguments import NotOnThisLine, parse

ROOT = Path(__file__).parents[1]
SKILLS = sorted(ROOT.glob("skills/*/SKILL.md"))
SERVED = {"validate", "report", "init", "skill", "explore", "studio"}
REFUSED = {"check", "guide", "story", "view"}
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


def _problems(text: str) -> list[str]:
    """Each `archkeel ...` line of the text that the real parser of the shell does not accept.

    Optional parts in brackets are dropped and a placeholder gets the value `x`. A served command
    with an unknown option, a missing value or a refusal is a problem.
    """
    found = []
    for line in re.findall(r"`archkeel ([^`]+)`", text):
        argv = shlex.split(re.sub(r"<[^>]+>", "x", re.sub(r"\[[^\]]*\]", "", line)))
        try:
            parse(argv)
        except (NotOnThisLine, ValueError) as error:
            found.append(f"`archkeel {line}`: {error}")
    return found


@pytest.mark.parametrize("path", SKILLS, ids=_name)
def test_each_command_line_of_a_skill_is_accepted_by_the_real_parser(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert _problems(text) == []
    assert path.parent.name != "archkeel" or re.search(r"`archkeel report --output ", text)


def test_the_parser_check_fails_on_an_unknown_option_a_refusal_and_a_bad_form() -> None:
    assert _problems("`archkeel report --bogus`")
    assert _problems("`archkeel validate --root`")
    assert _problems("`archkeel view`")
    assert _problems("`archkeel studio <path>`") == []
    assert _problems("`archkeel report --output r.json --format yaml`")
    good = "`archkeel report --output r.json --format json` `archkeel validate [--root PATH]`"
    assert _problems(good) == []


@pytest.mark.parametrize("path", SKILLS, ids=_name)
def test_a_format_option_in_a_skill_always_comes_with_an_output(path: Path) -> None:
    for span in re.findall(r"`([^`]+)`", path.read_text(encoding="utf-8")):
        assert "--format" not in span or "--output" in span, f"{path.name}: `{span}`"


def test_the_skill_quotes_the_language_block_of_the_known_limits_unchanged() -> None:
    limits = (ROOT / "docs/known-limits.md").read_text(encoding="utf-8")
    block = limits.split("<!-- tiers:start -->\n")[1].split("<!-- tiers:end -->")[0]
    assert "interface_boundary" in block and block.strip()
    assert block in (ROOT / "skills/archkeel/SKILL.md").read_text(encoding="utf-8")


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
