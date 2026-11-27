# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each command line of a shipped agent skill is accepted by the real parser of the shell (#880)."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from archkeel.cli.core_arguments import NotOnThisLine, parse

ROOT = Path(__file__).parents[1]
SKILLS = sorted(ROOT.glob("skills/*/SKILL.md"))


def _name(path: Path) -> str:
    return path.parent.name


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
