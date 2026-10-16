# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Decode the CLI's closed argument protocols before workflow dispatch."""

import argparse
from enum import StrEnum
from typing import NoReturn

from ..check.ports import Language
from .skill import InstallationAgent


class Command(StrEnum):
    REPORT = "report"
    VALIDATE = "validate"
    CHECK = "check"
    INIT = "init"
    SKILL = "skill"
    ARGUMENTS = "arguments"


class ReportMode(StrEnum):
    VIOLATIONS = "violations"
    CALLS = "calls"
    ARCHITECTURE = "architecture"


class SkillAction(StrEnum):
    INSTALL = "install"


class ConfigurationSource(StrEnum):
    DEFAULT = "default"
    CUSTOM = "custom"


class CLIArguments(argparse.Namespace):
    """Argparse owns data fields; these closed fields always have their declared types."""

    command: Command | None = None
    only: ReportMode | None = None
    action: SkillAction = SkillAction.INSTALL
    agent: InstallationAgent = InstallationAgent.CODEX
    language: Language = Language.PYTHON


def configuration_source(path: str | None, default: str) -> ConfigurationSource:
    """Classify the canonical config filename without changing arbitrary path data."""
    if path is None:
        return ConfigurationSource.DEFAULT
    return {default: ConfigurationSource.DEFAULT}.get(path, ConfigurationSource.CUSTOM)


def _invalid_choice(value: str, choices: tuple[str, ...]) -> NoReturn:
    names = ", ".join(repr(choice) for choice in choices)
    raise argparse.ArgumentTypeError(f"invalid choice: {value!r} (choose from {names})")


def report_mode(value: str) -> ReportMode:
    try:
        return ReportMode(value)
    except ValueError:
        _invalid_choice(value, tuple(item.value for item in ReportMode))


def source_language(value: str) -> Language:
    try:
        return Language(value)
    except ValueError:
        _invalid_choice(value, tuple(item.value for item in Language))


def installation_agent(value: str) -> InstallationAgent:
    try:
        return InstallationAgent(value)
    except ValueError:
        _invalid_choice(value, tuple(item.value for item in InstallationAgent))


def skill_action(value: str) -> SkillAction:
    try:
        return SkillAction(value)
    except ValueError:
        _invalid_choice(value, tuple(item.value for item in SkillAction))
