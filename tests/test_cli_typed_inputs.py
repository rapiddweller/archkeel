# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Closed CLI inputs are decoded before workflow or installer dispatch."""

from enum import StrEnum
from pathlib import Path

import pytest

from archkeel.cli import build_parser
from archkeel.cli.skill import install_skill


@pytest.mark.parametrize(
    ("argv", "field", "wire"),
    [
        (["report"], "command", "report"),
        (["validate"], "command", "validate"),
        (["init"], "command", "init"),
        (["skill", "install", "codex"], "command", "skill"),
        (["report", "--only", "violations"], "only", "violations"),
        (["report", "--only", "calls"], "only", "calls"),
        (["report", "--only", "architecture"], "only", "architecture"),
        (["skill", "install", "claude"], "action", "install"),
        (["skill", "install", "claude"], "agent", "claude"),
        (["skill", "install", "codex"], "agent", "codex"),
        (["init"], "language", "python"),
        (["init", "--language", "python"], "language", "python"),
        (["init", "--language", "dart"], "language", "dart"),
        (["init", "--language", "typescript"], "language", "typescript"),
    ],
)
def test_parser_returns_typed_closed_inputs(argv, field, wire):
    arguments = build_parser().parse_args(argv)
    value = getattr(arguments, field)
    assert isinstance(value, StrEnum), (field, value)
    assert str(value) == wire


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["report", "--only", "bogus"],
            "argument --only: invalid choice: 'bogus' "
            "(choose from 'violations', 'calls', 'architecture')",
        ),
        (
            ["init", "--language", "bogus"],
            "argument --language: invalid choice: 'bogus' "
            "(choose from 'python', 'dart', 'typescript')",
        ),
        (
            ["skill", "install", "bogus"],
            "argument agent: invalid choice: 'bogus' (choose from 'claude', 'codex')",
        ),
        (
            ["skill", "remove", "codex"],
            "argument action: invalid choice: 'remove' (choose from 'install')",
        ),
    ],
)
def test_invalid_choice_text_remains_compatible(argv, message):
    with pytest.raises(ValueError) as failure:
        build_parser().parse_args(argv)
    assert str(failure.value) == message


@pytest.mark.parametrize("agent", ["unknown", "Claude", ""])
def test_installer_rejects_an_invalid_agent_before_writing(tmp_path: Path, agent: str):
    with pytest.raises(ValueError):
        install_skill(tmp_path, agent)
    assert list(tmp_path.iterdir()) == []
